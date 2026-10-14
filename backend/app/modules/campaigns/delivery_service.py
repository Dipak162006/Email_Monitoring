from datetime import datetime, timezone, timedelta
from html import escape
import logging
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.sanitizer import sanitize_html
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.core.config import settings
from app.core.security import build_unsubscribe_url
from app.modules.campaigns.service import CampaignService
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.emails.models import Email
from app.modules.emails.schemas import EmailSendRequest
from app.modules.emails.service import EmailService

logger = logging.getLogger(__name__)


def render_content_for_recipient(
    template: Optional[str],
    recipient: CampaignRecipient,
    is_html: bool = False,
    context_vars: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Replace approved merge tags and custom recipient variables in template.
    
    Safe empty-value replacement applies when fields are None or omitted.
    Handles optional whitespace inside braces, e.g. {{ first_name }}.
    Escapes HTML entities and performs URL safety sanitization when rendering HTML content
    to prevent HTML injection and malicious script execution in href/src attributes.
    """
    if template is None:
        return None

    ctx = context_vars or {}

    first_name = (recipient.first_name or "").strip()
    last_name = (getattr(recipient, "last_name", None) or "").strip()
    full_name = " ".join(filter(None, [first_name, last_name])).strip()
    customer_name = full_name if full_name else first_name
    email = (recipient.email or "").strip()

    resolved: Dict[str, str] = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "customer_name": customer_name,
        "customer_email": email,
        "email": email,
        "company_name": str(ctx.get("company_name", "") or "").strip(),
        "sender_name": str(ctx.get("sender_name", "") or "").strip(),
        "sender_email": str(ctx.get("sender_email", "") or "").strip(),
        "login_url": str(ctx.get("login_url", "") or "").strip(),
        "unsubscribe_url": str(ctx.get("unsubscribe_url", "") or "").strip(),
        "ticket_id": str(ctx.get("ticket_id", recipient.id if getattr(recipient, "id", None) is not None else "") or "").strip(),
    }

    # Overlay any keys from recipient.custom_variables (case-insensitive keys)
    custom_vars = getattr(recipient, "custom_variables", None)
    if isinstance(custom_vars, dict):
        for k, v in custom_vars.items():
            if k is not None and v is not None:
                clean_k = str(k).strip().lower()
                resolved[clean_k] = str(v)

    STANDARD_TAGS = {
        "first_name",
        "last_name",
        "full_name",
        "customer_name",
        "customer_email",
        "email",
        "company_name",
        "sender_name",
        "sender_email",
        "login_url",
        "unsubscribe_url",
        "ticket_id",
    }

    def replacer(match: re.Match) -> str:
        tag_key = match.group(1).lower()
        if tag_key in resolved:
            val = resolved[tag_key]
            # Special preservation: if unsubscribe_url was not provided in context,
            # leave placeholder intact (e.g. for preview or tests asserting '{{unsubscribe_url}}')
            if tag_key == "unsubscribe_url" and not val:
                return match.group(0)
            if is_html:
                return escape(val, quote=True)
            return val
        elif tag_key in STANDARD_TAGS:
            if tag_key == "unsubscribe_url":
                return match.group(0)
            return ""
        return match.group(0)

    rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replacer, template)
    if is_html and rendered:
        return sanitize_html(rendered)
    return rendered


def is_retryable_delivery_error(exc: Optional[Exception]) -> bool:
    """Classify whether a delivery exception is retryable based on the existing
    SMTP and EmailTransport exception taxonomy.
    
    Retryable:
    - TransportConnectionError / SMTPConnectionError (connection refused, timeouts)
    - TransportSendError / SMTPSendError (transient drops mid-transfer)
    - EmailTransportException with is_retryable == True
    - Socket, OS, and network timeouts
    
    Non-retryable:
    - TransportConfigurationError / SMTPConfigurationError
    - TransportAuthenticationError / SMTPAuthenticationError
    - TransportRecipientRejectedError / SMTPRecipientRejectedError
    - EmailTransportException with is_retryable == False
    - Generic permanent client errors
    """
    if not exc:
        return False

    # Unpack original exception from HTTPException wrapper if attached
    orig = getattr(exc, "original_exception", None)
    if orig and orig is not exc and is_retryable_delivery_error(orig):
        return True

    # Check explicit transport exception is_retryable flag
    if hasattr(exc, "is_retryable"):
        return bool(exc.is_retryable)

    from app.services.smtp.exceptions import (
        SMTPAuthenticationError,
        SMTPConfigurationError,
        SMTPConnectionError,
        SMTPRecipientRejectedError,
        SMTPSendError,
    )
    from app.services.transport.exceptions import (
        TransportAuthenticationError,
        TransportConfigurationError,
        TransportConnectionError,
        TransportRecipientRejectedError,
        TransportSendError,
    )

    # Check known permanent/fatal failure types first
    if isinstance(exc, (
        TransportConfigurationError,
        SMTPConfigurationError,
        TransportAuthenticationError,
        SMTPAuthenticationError,
        TransportRecipientRejectedError,
        SMTPRecipientRejectedError,
    )):
        return False

    # Check known retryable transport/SMTP failure types
    if isinstance(exc, (
        TransportConnectionError,
        SMTPConnectionError,
        TransportSendError,
        SMTPSendError,
    )):
        return True

    # Check socket, OS, and timeout errors
    if isinstance(exc, (TimeoutError, ConnectionRefusedError, ConnectionResetError, OSError)):
        return True

    return False


class CampaignDeliveryService:
    """Service layer orchestrating recipient iteration, content rendering,
    EmailService transmission, CampaignDelivery tracking, and Campaign finalization.
    """

    @classmethod
    async def execute_campaign(
        cls,
        campaign_id: int,
        company_id: int,
        db_factory=None,
        email_service: Optional[EmailService] = None,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Execute delivery for an authorized QUEUED campaign.
        
        Guarantees:
        - Short transaction boundaries (no DB locks held across SMTP network calls)
        - Strict tenant isolation
        - Reuses existing EmailService, EmailTransport, and SMTP infrastructure
        - Independent recipient error isolation (one failure does not halt the campaign)
        - Single CampaignDelivery record per recipient linked to Email and thread
        - Atomically finalizes Campaign state via centralized state machine
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db
        if email_service is None:
            email_service = EmailService()

        # ---------------------------------------------------------------------
        # Phase 1: Verify Campaign & Transition QUEUED -> RUNNING
        # ---------------------------------------------------------------------
        async with db_factory() as db:
            stmt = (
                select(Campaign)
                .options(
                    selectinload(Campaign.email_account),
                    selectinload(Campaign.company),
                )
                .where(
                    Campaign.id == campaign_id,
                    Campaign.company_id == company_id,
                )
                .with_for_update()
            )
            result = await db.execute(stmt)
            campaign = result.scalar_one_or_none()

            if not campaign:
                logger.warning("Campaign %d for company %d not found in delivery engine.", campaign_id, company_id)
                return {
                    "status": "NOT_FOUND",
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "error": "Campaign not found or tenant mismatch.",
                }

            if campaign.status not in (CampaignStatus.QUEUED.value, CampaignStatus.RUNNING.value):
                logger.warning(
                    "Campaign %d has status '%s' (expected QUEUED or RUNNING). Skipping execution.",
                    campaign_id,
                    campaign.status,
                )
                return {
                    "status": "SKIPPED",
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "current_status": campaign.status,
                    "reason": f"Expected QUEUED or RUNNING status, found '{campaign.status}'.",
                }

            if not campaign.email_account or campaign.email_account.company_id != company_id:
                logger.error("Sender email account for campaign %d does not belong to company %d.", campaign_id, company_id)
                await CampaignService.transition_state(
                    db=db,
                    company_id=company_id,
                    campaign_id=campaign_id,
                    target_status=CampaignStatus.FAILED,
                )
                return {
                    "status": "FAILED",
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "error": "Sender email account mismatch.",
                }

            # Transition QUEUED -> RUNNING if initial launch; if already RUNNING (resumed), keep RUNNING
            if campaign.status == CampaignStatus.QUEUED.value:
                campaign = await CampaignService.transition_state(
                    db=db,
                    company_id=company_id,
                    campaign_id=campaign_id,
                    target_status=CampaignStatus.RUNNING,
                )

            # Check pacing delay if send_interval_seconds > 0
            current_time = now_utc or datetime.now(timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)

            send_interval_sec = getattr(campaign, "send_interval_seconds", 0) or 0
            if send_interval_sec > 0 and campaign.next_send_at is not None:
                sched_due = campaign.next_send_at
                if sched_due.tzinfo is None:
                    sched_due = sched_due.replace(tzinfo=timezone.utc)
                if sched_due > current_time:
                    delay_sec = (sched_due - current_time).total_seconds()
                    if delay_sec > 0:
                        logger.info(
                            "Campaign %d pacing interval has not elapsed yet. Next send at %s (in %ds). Rescheduling task.",
                            campaign_id,
                            sched_due,
                            int(delay_sec),
                        )
                        from app.workers.campaign_tasks import dispatch_campaign_task
                        try:
                            dispatch_campaign_task.apply_async(
                                args=[campaign_id, company_id],
                                countdown=max(1, int(delay_sec)),
                            )
                        except Exception as async_err:
                            logger.warning("Could not schedule future task for campaign %d: %s", campaign_id, async_err)

                        return {
                            "status": "WAITING_INTERVAL",
                            "campaign_id": campaign_id,
                            "company_id": company_id,
                            "next_send_at": sched_due.isoformat(),
                            "delay_seconds": int(delay_sec),
                        }

        # ---------------------------------------------------------------------
        # Phase 2: Identify Eligible Recipients & Suppressions
        # ---------------------------------------------------------------------
        async with db_factory() as db:
            recip_stmt = (
                select(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
                )
                .order_by(CampaignRecipient.id.asc())
            )
            recip_res = await db.execute(recip_stmt)
            pending_recipients = list(recip_res.scalars().all())

            recipient_emails = {r.email for r in pending_recipients}
            suppressed_emails = await SuppressionService.get_suppressed_emails(
                db=db,
                company_id=company_id,
                emails=recipient_emails,
            )

            # Discover all existing deliveries for this campaign to prevent duplicating
            # already SENT, BOUNCED, FAILED, or in-flight SENDING deliveries on resume
            deliv_stmt = select(CampaignDelivery.recipient_id, CampaignDelivery.status).where(
                CampaignDelivery.campaign_id == campaign_id,
            )
            deliv_res = await db.execute(deliv_stmt)
            existing_deliveries = {row[0]: row[1] for row in deliv_res.all()}

            eligible_recipient_ids = []
            suppressed_count = 0
            for r in pending_recipients:
                norm_email = r.email.strip().lower()
                if norm_email in suppressed_emails:
                    logger.info("Recipient %d (%s) is suppressed. Skipping delivery.", r.id, norm_email)
                    r.status = CampaignRecipientStatus.SUPPRESSED.value
                    suppressed_count += 1
                    continue

                existing_status = existing_deliveries.get(r.id)
                if existing_status == CampaignDeliveryStatus.SENT.value:
                    logger.info("Recipient %d (%s) already has a SENT delivery. Skipping.", r.id, norm_email)
                    if r.status != CampaignRecipientStatus.SENT.value:
                        r.status = CampaignRecipientStatus.SENT.value
                        suppressed_count += 1
                    continue
                if existing_status == CampaignDeliveryStatus.BOUNCED.value:
                    logger.info("Recipient %d (%s) already has a BOUNCED delivery. Skipping.", r.id, norm_email)
                    if r.status != CampaignRecipientStatus.BOUNCED.value:
                        r.status = CampaignRecipientStatus.BOUNCED.value
                        suppressed_count += 1
                    continue
                if existing_status == CampaignDeliveryStatus.FAILED.value:
                    logger.info("Recipient %d (%s) already has a FAILED delivery. Retries handled by retry worker. Skipping.", r.id, norm_email)
                    continue
                if existing_status == CampaignDeliveryStatus.SENDING.value:
                    logger.info("Recipient %d (%s) is currently in-progress SENDING. Skipping.", r.id, norm_email)
                    continue

                eligible_recipient_ids.append(r.id)

            if suppressed_count > 0:
                await db.commit()
                logger.info(
                    "Updated %d recipients with SUPPRESSED/persisted status for campaign %d",
                    suppressed_count,
                    campaign_id,
                )

        # ---------------------------------------------------------------------
        # Phase 3: Per-Recipient Processing Loop (Short Independent Transactions)
        # ---------------------------------------------------------------------
        sent_count = 0
        failed_count = 0
        skipped_count = len(pending_recipients) - len(eligible_recipient_ids)

        # For paced delivery (send_interval_seconds > 0), process only ONE recipient per task execution
        target_recipient_ids = (
            eligible_recipient_ids[:1]
            if send_interval_sec > 0
            else eligible_recipient_ids
        )

        for recip_id in target_recipient_ids:
            # 3a. Prepare delivery record in SENDING status under short transaction
            delivery_id: Optional[int] = None
            recipient_email: str = ""
            camp_subject: str = ""
            camp_body_text: Optional[str] = None
            camp_body_html: Optional[str] = None
            camp_company_name: str = ""
            sender_account = None
            recipient_obj = None

            async with db_factory() as db:
                recip_stmt = select(CampaignRecipient).where(CampaignRecipient.id == recip_id)
                recip_res = await db.execute(recip_stmt)
                recipient = recip_res.scalar_one_or_none()

                camp_stmt = (
                    select(Campaign)
                    .options(
                        selectinload(Campaign.email_account),
                        selectinload(Campaign.company),
                        selectinload(Campaign.attachments),
                    )
                    .where(Campaign.id == campaign_id)
                )
                camp_res = await db.execute(camp_stmt)
                campaign = camp_res.scalar_one_or_none()

                if not recipient or not campaign:
                    continue

                # Worker enforcement: Stop if campaign is PAUSED, CANCELLED, or no longer RUNNING
                if campaign.status != CampaignStatus.RUNNING.value:
                    logger.info(
                        "Campaign %d has status '%s' (not RUNNING). Stopping recipient delivery loop.",
                        campaign_id,
                        campaign.status,
                    )
                    break

                recipient_obj = recipient
                recipient_email = recipient.email
                camp_subject = campaign.subject
                camp_body_text = campaign.body_text
                camp_body_html = campaign.body_html
                sender_account = campaign.email_account
                camp_company_name = (campaign.company.name if campaign.company and campaign.company.name else "") or (sender_account.name if sender_account and sender_account.name else "")
                camp_attachment_ids = [att.id for att in campaign.attachments]

                # Check or create CampaignDelivery under row-level lock
                deliv_stmt = select(CampaignDelivery).where(
                    CampaignDelivery.campaign_id == campaign_id,
                    CampaignDelivery.recipient_id == recipient.id,
                ).with_for_update()
                deliv_res = await db.execute(deliv_stmt)
                delivery = deliv_res.scalar_one_or_none()

                current_attempt_time = now_utc or datetime.now(timezone.utc)
                if current_attempt_time.tzinfo is None:
                    current_attempt_time = current_attempt_time.replace(tzinfo=timezone.utc)

                if send_interval_sec > 0:
                    campaign.next_send_at = current_attempt_time + timedelta(seconds=send_interval_sec)

                if not delivery:
                    delivery = CampaignDelivery(
                        campaign_id=campaign.id,
                        recipient_id=recipient.id,
                        status=CampaignDeliveryStatus.SENDING.value,
                        attempt_count=1,
                        last_attempt_at=current_attempt_time,
                    )
                    db.add(delivery)
                else:
                    if delivery.status in (
                        CampaignDeliveryStatus.SENT.value,
                        CampaignDeliveryStatus.BOUNCED.value,
                        CampaignDeliveryStatus.FAILED.value,
                        CampaignDeliveryStatus.SENDING.value,
                    ):
                        skipped_count += 1
                        continue
                    delivery.status = CampaignDeliveryStatus.SENDING.value
                    delivery.attempt_count += 1
                    delivery.last_attempt_at = current_attempt_time

                try:
                    await db.commit()
                    await db.refresh(delivery)
                    delivery_id = delivery.id
                except IntegrityError:
                    await db.rollback()
                    logger.info("Delivery for recipient %d already created concurrently. Skipping.", recipient.id)
                    skipped_count += 1
                    continue

            if delivery_id is None or recipient_obj is None:
                continue

            # 3b. Render recipient-specific content with full template variables
            sender_name = sender_account.name or sender_account.email_address
            sender_email = sender_account.email_address
            unsub_url = build_unsubscribe_url(company_id=company_id, email=recipient_email, campaign_id=campaign_id)
            login_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")

            context_vars = {
                "company_name": camp_company_name,
                "sender_name": sender_name,
                "sender_email": sender_email,
                "unsubscribe_url": unsub_url,
                "login_url": login_url,
            }

            rendered_subject = render_content_for_recipient(camp_subject, recipient_obj, context_vars=context_vars) or ""
            rendered_body_text = render_content_for_recipient(camp_body_text, recipient_obj, context_vars=context_vars)
            rendered_body_html = render_content_for_recipient(camp_body_html, recipient_obj, is_html=True, context_vars=context_vars)

            send_req = EmailSendRequest(
                email_account_id=sender_account.id,
                to=[recipient_email],
                subject=rendered_subject,
                body_text=rendered_body_text,
                body_html=rendered_body_html,
                campaign_attachment_ids=camp_attachment_ids if camp_attachment_ids else None,
                unsubscribe_url=unsub_url,
            )

            # 3c. Transmit via EmailService (NO DB locks held during transport I/O)
            send_success = False
            sent_email_record: Optional[Email] = None
            failed_email_record: Optional[Email] = None
            error_detail: Optional[str] = None
            caught_exc: Optional[Exception] = None

            async with db_factory() as db:
                try:
                    sent_email_record = await email_service.send_email(
                        db=db,
                        account=sender_account,
                        current_user=None,
                        send_req=send_req,
                    )
                    send_success = True
                except Exception as exc:
                    send_success = False
                    caught_exc = exc
                    error_detail = getattr(exc, "detail", str(exc))
                    failed_email_record = getattr(exc, "email_record", None)
                    logger.warning(
                        "Delivery failure for campaign %d recipient %s: %s",
                        campaign_id,
                        recipient_email,
                        error_detail,
                    )

            # 3d. Update delivery outcome under short transaction
            async with db_factory() as db:
                deliv_stmt = select(CampaignDelivery).where(CampaignDelivery.id == delivery_id)
                deliv_res = await db.execute(deliv_stmt)
                delivery = deliv_res.scalar_one_or_none()

                recip_stmt = select(CampaignRecipient).where(CampaignRecipient.id == recip_id)
                recip_res = await db.execute(recip_stmt)
                recipient = recip_res.scalar_one_or_none()

                if delivery and recipient:
                    if send_success and sent_email_record:
                        delivery.status = CampaignDeliveryStatus.SENT.value
                        delivery.sent_at = datetime.now(timezone.utc)
                        delivery.email_id = sent_email_record.id
                        delivery.thread_id = sent_email_record.thread_id
                        delivery.message_id = sent_email_record.message_id
                        delivery.error_message = None

                        recipient.status = CampaignRecipientStatus.SENT.value
                        sent_count += 1
                    else:
                        delivery.status = CampaignDeliveryStatus.FAILED.value
                        delivery.error_message = str(error_detail or "Unknown delivery error")
                        if failed_email_record:
                            delivery.email_id = failed_email_record.id
                            delivery.thread_id = failed_email_record.thread_id
                            delivery.message_id = failed_email_record.message_id

                        recipient.status = CampaignRecipientStatus.FAILED.value
                        failed_count += 1

                        # Schedule retry if error is retryable and attempt_count < max_retries
                        max_retries = getattr(settings, "MAX_CAMPAIGN_DELIVERY_RETRIES", 3)
                        if is_retryable_delivery_error(caught_exc) and delivery.attempt_count < max_retries:
                            try:
                                cls.schedule_delivery_retry(
                                    delivery_id=delivery.id,
                                    company_id=company_id,
                                    attempt_count=delivery.attempt_count,
                                    min_countdown=send_interval_sec,
                                )
                            except Exception as sched_err:
                                logger.warning("Could not schedule retry for delivery %d: %s", delivery.id, sched_err)

                    await db.commit()

        # If paced delivery (send_interval_seconds > 0) and more pending recipients remain:
        # Schedule the next recipient task via Celery without blocking the worker
        if send_interval_sec > 0:
            async with db_factory() as db:
                rem_stmt = select(func.count(CampaignRecipient.id)).where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
                )
                remaining_pending = await db.scalar(rem_stmt) or 0

                camp_stmt = select(Campaign).where(Campaign.id == campaign_id)
                camp_res = await db.execute(camp_stmt)
                active_camp = camp_res.scalar_one_or_none()

            if remaining_pending > 0 and active_camp and active_camp.status == CampaignStatus.RUNNING.value:
                now_check = datetime.now(timezone.utc)
                due_time = active_camp.next_send_at or (now_check + timedelta(seconds=send_interval_sec))
                if due_time.tzinfo is None:
                    due_time = due_time.replace(tzinfo=timezone.utc)
                delay_sec = max(1, int((due_time - now_check).total_seconds()))

                from app.workers.campaign_tasks import dispatch_campaign_task
                try:
                    dispatch_campaign_task.apply_async(
                        args=[campaign_id, company_id],
                        countdown=delay_sec,
                    )
                except Exception as sched_err:
                    logger.warning("Could not enqueue next paced dispatch for campaign %d: %s", campaign_id, sched_err)

                return {
                    "status": "RUNNING",
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "total_recipients": len(pending_recipients),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count,
                    "remaining_pending": remaining_pending,
                    "next_send_at": due_time.isoformat(),
                }

        # ---------------------------------------------------------------------
        # Phase 4: Finalize Campaign Lifecycle State
        # ---------------------------------------------------------------------
        async with db_factory() as db:
            camp_stmt = select(Campaign).where(Campaign.id == campaign_id)
            camp_res = await db.execute(camp_stmt)
            campaign = camp_res.scalar_one_or_none()

            if not campaign:
                return {
                    "status": "NOT_FOUND",
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "error": "Campaign not found during finalization.",
                }

            # If stopped due to PAUSED or CANCELLED, preserve status and do not overwrite with COMPLETED
            if campaign.status in (CampaignStatus.PAUSED.value, CampaignStatus.CANCELLED.value):
                logger.info(
                    "Campaign %d stopped in status '%s'. Preserving state without marking COMPLETED/FAILED.",
                    campaign_id,
                    campaign.status,
                )
                return {
                    "status": campaign.status,
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "total_recipients": len(pending_recipients),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count,
                }

            # If there are still pending recipients (e.g. campaign was paused during loop and resumed),
            # preserve status and do not mark COMPLETED/FAILED.
            remaining_pending = await db.scalar(
                select(func.count(CampaignRecipient.id)).where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
                )
            ) or 0
            if remaining_pending > 0:
                logger.info(
                    "Campaign %d has %d remaining pending recipients. Preserving status '%s' without marking COMPLETED/FAILED.",
                    campaign_id,
                    remaining_pending,
                    campaign.status,
                )
                return {
                    "status": campaign.status,
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "total_recipients": len(pending_recipients),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count,
                    "remaining_pending": remaining_pending,
                }

            # If there are active deliveries in SENDING status (concurrent send or in-flight),
            # preserve status and do not mark terminal yet.
            active_sending = await db.scalar(
                select(func.count(CampaignDelivery.id)).where(
                    CampaignDelivery.campaign_id == campaign_id,
                    CampaignDelivery.status == CampaignDeliveryStatus.SENDING.value,
                )
            ) or 0
            if active_sending > 0:
                logger.info(
                    "Campaign %d has %d active SENDING deliveries. Preserving status '%s' without marking COMPLETED/FAILED.",
                    campaign_id,
                    active_sending,
                    campaign.status,
                )
                return {
                    "status": campaign.status,
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "total_recipients": len(pending_recipients),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count,
                    "active_sending": active_sending,
                }

            total_sent = await db.scalar(
                select(func.count(CampaignDelivery.id)).where(
                    CampaignDelivery.campaign_id == campaign_id,
                    CampaignDelivery.status == CampaignDeliveryStatus.SENT.value,
                )
            ) or 0

            # If at least one delivery was sent, or if all completed with zero failures
            if total_sent > 0 or (sent_count == 0 and failed_count == 0):
                target_status = CampaignStatus.COMPLETED
            else:
                target_status = CampaignStatus.FAILED

            campaign = await CampaignService.transition_state(
                db=db,
                company_id=company_id,
                campaign_id=campaign_id,
                target_status=target_status,
            )
            final_status = campaign.status
            await db.commit()

            logger.info(
                "Campaign %d finalized in status %s (sent: %d, failed: %d, skipped: %d)",
                campaign_id,
                final_status,
                sent_count,
                failed_count,
                skipped_count,
            )

        return {
            "status": final_status,
            "campaign_id": campaign_id,
            "company_id": company_id,
            "total_recipients": len(pending_recipients),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }

    @classmethod
    def schedule_delivery_retry(
        cls,
        delivery_id: int,
        company_id: int,
        attempt_count: int,
        countdown: Optional[int] = None,
        min_countdown: int = 0,
    ) -> Any:
        """Schedule an asynchronous Celery task to retry the failed delivery with exponential backoff."""
        from app.core.config import settings
        max_retries = getattr(settings, "MAX_CAMPAIGN_DELIVERY_RETRIES", 3)
        if attempt_count >= max_retries:
            logger.info("Delivery %d has reached max retries (%d). Skipping retry schedule.", delivery_id, max_retries)
            return None

        if countdown is None:
            base_backoff = getattr(settings, "CAMPAIGN_RETRY_BACKOFF_SECONDS", 60)
            countdown = int(base_backoff * (2 ** max(0, attempt_count - 1)))

        if min_countdown > 0:
            countdown = max(countdown, min_countdown)

        from app.workers.campaign_tasks import retry_campaign_delivery_task
        logger.info(
            "Scheduling retry for delivery %d (company %d, attempt %d/%d) in %ds",
            delivery_id,
            company_id,
            attempt_count + 1,
            max_retries,
            countdown,
        )
        return retry_campaign_delivery_task.apply_async(
            kwargs={"delivery_id": delivery_id, "company_id": company_id},
            countdown=countdown,
        )

    @classmethod
    async def has_active_campaign_worker(cls, db: AsyncSession, campaign_id: int) -> bool:
        """Check if an active C8 campaign execution worker is currently mid-send.

        Distinguishes active C8 campaign execution from C9 retry execution:
        - C8 campaign worker: delivery in SENDING status with attempt_count == 1
          and recipient.status == PENDING.
        - C9 retry worker: delivery in SENDING status with attempt_count > 1
          and recipient.status == FAILED.
        """
        stmt = (
            select(func.count(CampaignDelivery.id))
            .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
            .where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.status == CampaignDeliveryStatus.SENDING.value,
                CampaignDelivery.attempt_count == 1,
                CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
            )
        )
        count = await db.scalar(stmt) or 0
        return count > 0

    @classmethod
    async def retry_delivery(
        cls,
        delivery_id: int,
        company_id: int,
        db_factory=None,
        email_service: Optional[EmailService] = None,
    ) -> Dict[str, Any]:
        """Asynchronously execute a retry attempt for an eligible failed CampaignDelivery.
        
        Enforces:
        - Strict tenant and company isolation
        - Finite retry policy: stops after MAX_CAMPAIGN_DELIVERY_RETRIES
        - Never retries already SENT or BOUNCED deliveries
        - Prevents concurrent duplicate execution via row-level locking
        - Refuses execution if campaign is PAUSED, CANCELLED, or DRAFT
        - Verifies company suppression list before re-sending
        - Short transaction boundaries (no DB locks held across SMTP network calls)
        - Preserves full auditability by linking latest Email record and Message-ID
        - Never mutates CampaignRecipient.status
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db

        if email_service is None:
            email_service = EmailService()

        max_retries = getattr(settings, "MAX_CAMPAIGN_DELIVERY_RETRIES", 3)

        # ---------------------------------------------------------------------
        # Step 1: Validate Eligibility, Lock Row, Check Terminal States
        # ---------------------------------------------------------------------
        async with db_factory() as db:
            stmt = (
                select(CampaignDelivery)
                .options(
                    selectinload(CampaignDelivery.campaign).selectinload(Campaign.email_account),
                    selectinload(CampaignDelivery.campaign).selectinload(Campaign.company),
                    selectinload(CampaignDelivery.campaign).selectinload(Campaign.attachments),
                    selectinload(CampaignDelivery.recipient),
                )
                .where(CampaignDelivery.id == delivery_id)
                .with_for_update(skip_locked=True)
            )
            res = await db.execute(stmt)
            delivery = res.scalar_one_or_none()

            if not delivery:
                # Check if delivery exists without lock to distinguish locked vs missing
                check_stmt = select(CampaignDelivery).where(CampaignDelivery.id == delivery_id)
                check_res = await db.execute(check_stmt)
                exists = check_res.scalar_one_or_none()
                if exists:
                    logger.warning("Delivery %d is currently locked by another worker. Skipping.", delivery_id)
                    return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": "Concurrent retry already in progress"}
                return {"status": "NOT_FOUND", "delivery_id": delivery_id, "error": "Delivery not found"}

            campaign = delivery.campaign
            recipient = delivery.recipient

            # Tenant validation
            if not campaign or campaign.company_id != company_id:
                logger.error("Tenant mismatch for delivery %d (expected company %d)", delivery_id, company_id)
                return {"status": "NOT_FOUND", "delivery_id": delivery_id, "error": "Tenant mismatch"}

            # In-progress and terminal delivery state checks: retry worker must only
            # begin a new outbound attempt when delivery is in an actually retryable state (FAILED)
            if delivery.status == CampaignDeliveryStatus.SENDING.value:
                logger.info("Delivery %d is currently SENDING (in progress). Skipping concurrent retry.", delivery_id)
                return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": "Delivery already SENDING"}

            if delivery.status == CampaignDeliveryStatus.SENT.value:
                logger.info("Delivery %d is already SENT. Skipping retry.", delivery_id)
                return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": "Delivery already SENT"}

            if delivery.status == CampaignDeliveryStatus.BOUNCED.value:
                logger.info("Delivery %d is already BOUNCED. Skipping retry.", delivery_id)
                return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": "Delivery already BOUNCED"}

            if delivery.status != CampaignDeliveryStatus.FAILED.value:
                logger.info("Delivery %d has non-retryable status '%s'. Skipping retry.", delivery_id, delivery.status)
                return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": f"Delivery in non-retryable state '{delivery.status}'"}

            # Campaign state check: retries prohibited if campaign is PAUSED, CANCELLED, DRAFT, or SCHEDULED
            if campaign.status in (
                CampaignStatus.PAUSED.value,
                CampaignStatus.CANCELLED.value,
                CampaignStatus.DRAFT.value,
                CampaignStatus.SCHEDULED.value,
            ):
                logger.warning("Campaign %d has status '%s'. Retries prohibited.", campaign.id, campaign.status)
                return {"status": "SKIPPED", "delivery_id": delivery_id, "reason": f"Campaign is in '{campaign.status}' state"}

            # Maximum attempts check
            if delivery.attempt_count >= max_retries:
                logger.warning("Delivery %d reached max retries (%d). Aborting retry.", delivery_id, max_retries)
                return {
                    "status": "EXCEEDED_MAX_RETRIES",
                    "delivery_id": delivery_id,
                    "attempt_count": delivery.attempt_count,
                    "reason": f"Maximum retry attempts ({max_retries}) reached",
                }

            # Recipient suppression check
            if not recipient:
                return {"status": "FAILED", "delivery_id": delivery_id, "error": "Recipient record not found"}

            if await SuppressionService.is_suppressed(db, company_id, recipient.email):
                logger.warning("Recipient %s is suppressed for company %d. Aborting retry.", recipient.email, company_id)
                delivery.status = CampaignDeliveryStatus.FAILED.value
                delivery.error_message = f"Recipient '{recipient.email}' is suppressed."
                await db.commit()
                return {"status": "SUPPRESSED", "delivery_id": delivery_id, "reason": "Recipient is suppressed"}

            # Sender account check
            sender_account = campaign.email_account
            if not sender_account or sender_account.company_id != company_id:
                return {"status": "FAILED", "delivery_id": delivery_id, "error": "Sender email account mismatch"}

            # Safe to retry: transition to SENDING and increment attempt_count
            delivery.status = CampaignDeliveryStatus.SENDING.value
            delivery.attempt_count += 1
            delivery.last_attempt_at = datetime.now(timezone.utc)
            await db.commit()

            # Prepare send data
            camp_subject = campaign.subject
            camp_body_text = campaign.body_text
            camp_body_html = campaign.body_html
            camp_attachment_ids = [att.id for att in campaign.attachments]
            recip_email = recipient.email
            attempt_number = delivery.attempt_count
            camp_company_name = (campaign.company.name if campaign.company and campaign.company.name else "") or (sender_account.name if sender_account and sender_account.name else "")

        # ---------------------------------------------------------------------
        # Step 2: Render Content & Transmit (NO DB LOCK HELD)
        # ---------------------------------------------------------------------
        sender_name = sender_account.name or sender_account.email_address
        sender_email = sender_account.email_address
        unsub_url = build_unsubscribe_url(company_id=company_id, email=recip_email, campaign_id=campaign.id)
        login_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")

        context_vars = {
            "company_name": camp_company_name,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "unsubscribe_url": unsub_url,
            "login_url": login_url,
        }

        rendered_subject = render_content_for_recipient(camp_subject, recipient, context_vars=context_vars) or ""
        rendered_body_text = render_content_for_recipient(camp_body_text, recipient, context_vars=context_vars)
        rendered_body_html = render_content_for_recipient(camp_body_html, recipient, is_html=True, context_vars=context_vars)

        send_req = EmailSendRequest(
            email_account_id=sender_account.id,
            to=[recip_email],
            subject=rendered_subject,
            body_text=rendered_body_text,
            body_html=rendered_body_html,
            campaign_attachment_ids=camp_attachment_ids if camp_attachment_ids else None,
            unsubscribe_url=unsub_url,
        )

        send_success = False
        sent_email_record: Optional[Email] = None
        failed_email_record: Optional[Email] = None
        error_detail: Optional[str] = None
        caught_exc: Optional[Exception] = None

        async with db_factory() as db:
            try:
                sent_email_record = await email_service.send_email(
                    db=db,
                    account=sender_account,
                    current_user=None,
                    send_req=send_req,
                )
                send_success = True
            except Exception as exc:
                send_success = False
                caught_exc = exc
                error_detail = getattr(exc, "detail", str(exc))
                failed_email_record = getattr(exc, "email_record", None)
                logger.warning("Retry send failure for delivery %d: %s", delivery_id, error_detail)

        # ---------------------------------------------------------------------
        # Step 3: Update Delivery State under Short Transaction
        # ---------------------------------------------------------------------
        async with db_factory() as db:
            stmt = select(CampaignDelivery).where(CampaignDelivery.id == delivery_id).with_for_update()
            res = await db.execute(stmt)
            delivery = res.scalar_one_or_none()

            if not delivery:
                return {"status": "NOT_FOUND", "delivery_id": delivery_id}

            # Step 12: Race condition safety — never overwrite a newer BOUNCED state!
            if delivery.status == CampaignDeliveryStatus.BOUNCED.value:
                logger.warning("Delivery %d became BOUNCED during retry execution. Retaining terminal BOUNCED state.", delivery_id)
                return {"status": "BOUNCED", "delivery_id": delivery_id}

            if send_success and sent_email_record:
                delivery.status = CampaignDeliveryStatus.SENT.value
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.email_id = sent_email_record.id
                delivery.thread_id = sent_email_record.thread_id
                delivery.message_id = sent_email_record.message_id
                delivery.error_message = None
                await db.commit()

                logger.info("Successfully retried delivery %d (attempt %d).", delivery_id, attempt_number)
                return {
                    "status": "SENT",
                    "delivery_id": delivery_id,
                    "email_id": sent_email_record.id,
                    "message_id": sent_email_record.message_id,
                    "attempt_count": delivery.attempt_count,
                }
            else:
                delivery.status = CampaignDeliveryStatus.FAILED.value
                delivery.error_message = str(error_detail or "Unknown retry failure")
                if failed_email_record:
                    delivery.email_id = failed_email_record.id
                    delivery.thread_id = failed_email_record.thread_id
                    delivery.message_id = failed_email_record.message_id
                await db.commit()

                # If still retryable and below max attempts, schedule subsequent retry
                if is_retryable_delivery_error(caught_exc) and delivery.attempt_count < max_retries:
                    try:
                        cls.schedule_delivery_retry(
                            delivery_id=delivery_id,
                            company_id=company_id,
                            attempt_count=delivery.attempt_count,
                        )
                    except Exception as sched_err:
                        logger.warning("Failed to schedule subsequent retry: %s", sched_err)

                return {
                    "status": "FAILED",
                    "delivery_id": delivery_id,
                    "error": delivery.error_message,
                    "attempt_count": delivery.attempt_count,
                }

    @classmethod
    async def record_bounce_event(
        cls,
        db: AsyncSession,
        company_id: int,
        delivery_id: int,
        diagnostic_text: Optional[str] = None,
    ) -> Optional[CampaignDelivery]:
        """Idempotently record a confirmed bounce on a delivery and its recipient.
        
        Updates delivery status and recipient status to BOUNCED, sets bounced_at,
        and records suppression for the recipient email address.
        Preserves company isolation.
        """
        stmt = (
            select(CampaignDelivery)
            .join(Campaign, CampaignDelivery.campaign_id == Campaign.id)
            .where(
                Campaign.company_id == company_id,
                CampaignDelivery.id == delivery_id,
            )
        )
        res = await db.execute(stmt)
        delivery = res.scalars().first()
        if not delivery:
            return None

        delivery.status = CampaignDeliveryStatus.BOUNCED.value
        delivery.bounced_at = datetime.now(timezone.utc)
        delivery.error_message = diagnostic_text

        recip_stmt = select(CampaignRecipient).where(CampaignRecipient.id == delivery.recipient_id)
        recip_res = await db.execute(recip_stmt)
        recipient = recip_res.scalar_one_or_none()
        if recipient:
            recipient.status = CampaignRecipientStatus.BOUNCED.value
            await SuppressionService.record_bounce_suppression(
                db=db,
                company_id=company_id,
                email=recipient.email,
            )
        return delivery


