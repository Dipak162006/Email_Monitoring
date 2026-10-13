from datetime import datetime, timezone
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus
from app.services.imap.parser import ParsedEmail

logger = logging.getLogger(__name__)


class EmailMonitoringService:
    """Dedicated monitoring service handling bounce detection, matching,
    diagnostic storage, outgoing email status updates to BOUNCED,
    and automatic reply filtering.
    """

    @classmethod
    async def match_and_process_bounce(
        cls,
        db: AsyncSession,
        account: EmailAccount,
        parsed: ParsedEmail,
    ) -> Optional[Email]:
        """Match an incoming bounce notification to its original outgoing email
        within the same company and account, and update its status to BOUNCED.

        Matching Priority:
        1. Original Message-ID extracted from embedded headers (bounce_original_message_id)
        2. Fallback to clean in_reply_to header
        
        Strict tenant & account isolation:
        - Only matches emails where company_id == account.company_id
        - Only matches emails where email_account_id == account.id
        - Only matches emails where direction == OUTGOING

        Returns:
            Matched and updated Email model, or None if no safe match found.
        """
        if not parsed.is_bounce:
            return None

        # 1. Determine target message-id to search
        candidate_ids = []
        if parsed.bounce_original_message_id:
            candidate_ids.append(parsed.bounce_original_message_id.strip())
        if parsed.in_reply_to:
            clean_in_reply = parsed.in_reply_to.strip()
            if clean_in_reply not in candidate_ids:
                candidate_ids.append(clean_in_reply)

        matched_email: Optional[Email] = None

        for cand_id in candidate_ids:
            # Query scoped to company, account, and OUTGOING direction
            stmt = select(Email).where(
                Email.company_id == account.company_id,
                Email.email_account_id == account.id,
                Email.direction == EmailDirection.OUTGOING.value,
                Email.message_id == cand_id,
            )
            result = await db.execute(stmt)
            found = result.scalars().first()
            if found:
                matched_email = found
                break

        if not matched_email:
            logger.info(
                "Unmatched bounce received for account %s (candidates: %s). Skipping status transition.",
                account.id,
                candidate_ids,
            )
            return None

        # 2. Build diagnostic message
        diagnostic_parts = []
        if parsed.bounce_status:
            diagnostic_parts.append(f"Status: {parsed.bounce_status}")
        if parsed.bounce_diagnostic:
            diagnostic_parts.append(f"Diagnostic: {parsed.bounce_diagnostic}")
        elif parsed.bounce_action:
            diagnostic_parts.append(f"Action: {parsed.bounce_action}")
        
        diagnostic_text = " | ".join(diagnostic_parts) if diagnostic_parts else "Delivery failed: Bounce notification received"

        # 3. Update original outgoing email status to BOUNCED safely and idempotently
        matched_email.status = EmailStatus.BOUNCED.value
        matched_email.error_message = diagnostic_text

        logger.info(
            "Successfully marked outgoing email %d as BOUNCED for account %d (message_id: %s)",
            matched_email.id,
            account.id,
            matched_email.message_id,
        )

        # 4. Correlate with CampaignDelivery within the same company tenant if applicable
        from app.modules.campaigns.models import (
            Campaign,
            CampaignDelivery,
            CampaignDeliveryStatus,
            CampaignRecipient,
            CampaignRecipientStatus,
        )
        from app.modules.campaigns.suppression_service import SuppressionService

        deliv_stmt = (
            select(CampaignDelivery)
            .join(Campaign, CampaignDelivery.campaign_id == Campaign.id)
            .where(
                Campaign.company_id == account.company_id,
                (CampaignDelivery.email_id == matched_email.id)
                | (CampaignDelivery.message_id == matched_email.message_id),
            )
        )
        deliv_res = await db.execute(deliv_stmt)
        campaign_delivery = deliv_res.scalars().first()

        if campaign_delivery:
            campaign_delivery.status = CampaignDeliveryStatus.BOUNCED.value
            campaign_delivery.bounced_at = datetime.now(timezone.utc)
            campaign_delivery.error_message = diagnostic_text

            # Identify the recipient email for company suppression and update recipient status
            recip_stmt = select(CampaignRecipient).where(CampaignRecipient.id == campaign_delivery.recipient_id)
            recip_res = await db.execute(recip_stmt)
            recipient = recip_res.scalar_one_or_none()

            if recipient:
                recipient.status = CampaignRecipientStatus.BOUNCED.value

            recipient_email = recipient.email if recipient else (
                matched_email.recipients[0] if (matched_email.recipients and len(matched_email.recipients) > 0) else None
            )

            if recipient_email:
                await SuppressionService.record_bounce_suppression(
                    db=db,
                    company_id=account.company_id,
                    email=recipient_email,
                )
                logger.info(
                    "Recorded bounce suppression for campaign %d delivery %d recipient %s",
                    campaign_delivery.campaign_id,
                    campaign_delivery.id,
                    recipient_email,
                )

        return matched_email

    @classmethod
    async def record_bounce_event(
        cls,
        db: AsyncSession,
        account: EmailAccount,
        parsed: ParsedEmail,
    ) -> Optional[Email]:
        """Record an incoming bounce event for an account (alias for match_and_process_bounce)."""
        return await cls.match_and_process_bounce(db=db, account=account, parsed=parsed)

    @staticmethod
    def is_genuine_reply(parsed: ParsedEmail) -> bool:
        """Evaluate whether an incoming email represents a genuine customer reply.
        
        Bounces and recognized auto-replies (out-of-office, vacation, auto-submitted)
        are filtered out and will not mark thread.has_reply = True.
        """
        if parsed.is_bounce:
            return False
        if parsed.is_auto_reply:
            return False
        return True
