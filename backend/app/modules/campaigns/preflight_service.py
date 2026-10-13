from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.modules.campaigns.schemas import (
    CampaignPreflightResponse,
    PreflightIssue,
)
from app.modules.campaigns.service import CampaignService, TERMINAL_STATES
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.companies.service import CompanyService
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService


class CampaignPreflightService:
    """Service orchestrating read-only campaign preflight eligibility evaluation.
    
    Inspects:
    1. Campaign existence and tenant isolation
    2. Campaign lifecycle state
    3. Campaign content requirements (subject, body text/HTML)
    4. Sender EmailAccount status, tenant ownership, and user authorization
    5. Sender Domain DNS verification status (SPF, DKIM, DMARC, MX)
    6. CampaignRecipient counts and suppression evaluation
    
    Guarantees:
    - 100% read-only (zero database mutations, commits, or flushes)
    - Zero email sending or Celery task dispatching
    - Zero CampaignDelivery creation
    - Deterministic evaluation from persisted state
    """

    @staticmethod
    async def validate_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        current_user: Optional[User] = None,
        user_role: Optional[str] = None,
    ) -> CampaignPreflightResponse:
        """Evaluate whether a campaign and its recipients are eligible for delivery.
        
        Returns a structured preflight report distinguishing blocking issues and warnings.
        Raises HTTPException(404) if campaign does not exist or belongs to another company (anti-enumeration).
        """
        # 1. Tenant-isolated campaign retrieval
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        issues: List[PreflightIssue] = []

        # 2. Campaign state validation
        if campaign.status in TERMINAL_STATES:
            issues.append(
                PreflightIssue(
                    code="CAMPAIGN_STATE_TERMINAL",
                    message=f"Campaign is in terminal state '{campaign.status}' and cannot proceed to execution.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )
        elif campaign.status == CampaignStatus.RUNNING.value:
            issues.append(
                PreflightIssue(
                    code="CAMPAIGN_ALREADY_RUNNING",
                    message="Campaign is currently running and cannot be preflighted for new execution.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )
        elif campaign.status not in {
            CampaignStatus.DRAFT.value,
            CampaignStatus.SCHEDULED.value,
            CampaignStatus.PAUSED.value,
        }:
            issues.append(
                PreflightIssue(
                    code="CAMPAIGN_STATE_INVALID",
                    message=f"Campaign state '{campaign.status}' is not eligible for execution.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )

        # 3. Campaign content validation
        if not campaign.subject or not campaign.subject.strip():
            issues.append(
                PreflightIssue(
                    code="MISSING_SUBJECT",
                    message="Campaign subject line is required.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )

        has_text = bool(campaign.body_text and campaign.body_text.strip())
        has_html = bool(campaign.body_html and campaign.body_html.strip())
        if not has_text and not has_html:
            issues.append(
                PreflightIssue(
                    code="MISSING_CONTENT",
                    message="Campaign must have either plain text or HTML body content.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )

        # 4. Sender EmailAccount validation
        sender_account: Optional[EmailAccount] = None
        if not campaign.email_account_id:
            issues.append(
                PreflightIssue(
                    code="SENDER_ACCOUNT_MISSING",
                    message="Campaign does not have an assigned sender email account.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )
        else:
            acc_result = await db.execute(
                select(EmailAccount).where(EmailAccount.id == campaign.email_account_id)
            )
            sender_account = acc_result.scalar_one_or_none()
            if not sender_account:
                issues.append(
                    PreflightIssue(
                        code="SENDER_ACCOUNT_NOT_FOUND",
                        message="Configured sender email account was not found.",
                        severity="BLOCKING",
                        blocking=True,
                    )
                )
            elif sender_account.company_id != company_id:
                issues.append(
                    PreflightIssue(
                        code="SENDER_ACCOUNT_WRONG_COMPANY",
                        message="Sender email account does not belong to the campaign company.",
                        severity="BLOCKING",
                        blocking=True,
                    )
                )
                sender_account = None
            else:
                if not sender_account.is_active:
                    issues.append(
                        PreflightIssue(
                            code="SENDER_ACCOUNT_INACTIVE",
                            message="Sender email account is inactive and cannot be used for delivery.",
                            severity="BLOCKING",
                            blocking=True,
                        )
                    )

                if not sender_account.email_address or "@" not in sender_account.email_address:
                    issues.append(
                        PreflightIssue(
                            code="SENDER_ACCOUNT_INVALID_EMAIL",
                            message="Sender email account does not have a valid email address.",
                            severity="BLOCKING",
                            blocking=True,
                        )
                    )

                if current_user is not None:
                    effective_role = user_role
                    if effective_role is None:
                        membership = await CompanyService.get_user_membership(
                            db=db,
                            company_id=company_id,
                            user_id=current_user.id,
                        )
                        effective_role = membership.role if membership else None

                    if effective_role is not None:
                        has_access = await EmailAccountService.check_user_access(
                            db=db,
                            account=sender_account,
                            user_id=current_user.id,
                            user_role=effective_role,
                        )
                        if not has_access:
                            issues.append(
                                PreflightIssue(
                                    code="SENDER_ACCOUNT_UNAUTHORIZED",
                                    message="Current user does not have permission to send from this email account.",
                                    severity="BLOCKING",
                                    blocking=True,
                                )
                            )

        # 5. Domain validation
        if sender_account and sender_account.company_id == company_id:
            if sender_account.domain_id is not None:
                dom_result = await db.execute(
                    select(Domain).where(
                        Domain.id == sender_account.domain_id,
                        Domain.company_id == company_id,
                    )
                )
                domain = dom_result.scalar_one_or_none()
                if not domain:
                    issues.append(
                        PreflightIssue(
                            code="DOMAIN_NOT_FOUND",
                            message="Assigned domain not found in company.",
                            severity="BLOCKING",
                            blocking=True,
                        )
                    )
                else:
                    sender_domain = (
                        sender_account.email_address.split("@", 1)[1].strip().lower()
                        if "@" in sender_account.email_address
                        else ""
                    )
                    configured_domain = domain.domain_name.strip().lower()
                    if sender_domain != configured_domain:
                        issues.append(
                            PreflightIssue(
                                code="DOMAIN_MISMATCH",
                                message=f"Sender email address domain '{sender_domain}' does not match assigned domain '{configured_domain}'.",
                                severity="BLOCKING",
                                blocking=True,
                            )
                        )

                    # Inspect verification status
                    v_status = domain.verification_status
                    if v_status == DomainVerificationStatus.FAILED.value:
                        issues.append(
                            PreflightIssue(
                                code="DOMAIN_VERIFICATION_FAILED",
                                message="Domain DNS verification status is FAILED.",
                                severity="BLOCKING",
                                blocking=True,
                            )
                        )
                    elif v_status == DomainVerificationStatus.PENDING.value:
                        issues.append(
                            PreflightIssue(
                                code="DOMAIN_VERIFICATION_PENDING",
                                message="Domain DNS verification status is PENDING.",
                                severity="WARNING",
                                blocking=False,
                            )
                        )
                    elif v_status == DomainVerificationStatus.WARNING.value:
                        issues.append(
                            PreflightIssue(
                                code="DOMAIN_VERIFICATION_WARNING",
                                message="Domain DNS verification status has warnings.",
                                severity="WARNING",
                                blocking=False,
                            )
                        )
                    elif v_status == DomainVerificationStatus.VERIFIED.value:
                        pass
            else:
                issues.append(
                    PreflightIssue(
                        code="DOMAIN_NOT_CONFIGURED",
                        message="Sender email account has no associated domain configuration for authentication verification.",
                        severity="WARNING",
                        blocking=False,
                    )
                )

        # 6. Recipient and Suppression validation
        recip_result = await db.execute(
            select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
        )
        recipients = list(recip_result.scalars().all())
        total_recipients = len(recipients)

        eligible_recipient_count = 0
        suppressed_recipient_count = 0

        if total_recipients == 0:
            issues.append(
                PreflightIssue(
                    code="NO_RECIPIENTS",
                    message="Campaign has no recipients configured.",
                    severity="BLOCKING",
                    blocking=True,
                )
            )
        else:
            recipient_emails = {r.email for r in recipients}
            suppressed_set = await SuppressionService.get_suppressed_emails(
                db=db,
                company_id=company_id,
                emails=recipient_emails,
            )

            for r in recipients:
                norm_email = r.email.strip().lower()
                if norm_email in suppressed_set or r.status == CampaignRecipientStatus.SUPPRESSED.value:
                    suppressed_recipient_count += 1
                elif r.status != CampaignRecipientStatus.PENDING.value:
                    # Non-pending recipients (e.g. SENT, FAILED, BOUNCED) are excluded from eligibility
                    pass
                else:
                    eligible_recipient_count += 1

            if eligible_recipient_count == 0:
                issues.append(
                    PreflightIssue(
                        code="NO_ELIGIBLE_RECIPIENTS",
                        message="Campaign has no eligible recipients remaining for delivery.",
                        severity="BLOCKING",
                        blocking=True,
                    )
                )
            elif suppressed_recipient_count > 0:
                issues.append(
                    PreflightIssue(
                        code="RECIPIENTS_SUPPRESSED",
                        message=f"{suppressed_recipient_count} recipient(s) are suppressed and will be excluded from delivery.",
                        severity="WARNING",
                        blocking=False,
                    )
                )

        # 7. Overall eligibility evaluation
        has_blocking = any(issue.blocking for issue in issues)
        return CampaignPreflightResponse(
            eligible=not has_blocking,
            campaign_id=campaign.id,
            recipient_count=total_recipients,
            eligible_recipient_count=eligible_recipient_count,
            suppressed_recipient_count=suppressed_recipient_count,
            issues=issues,
        )
