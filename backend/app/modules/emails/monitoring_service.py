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
        from app.modules.campaigns.models import CampaignDelivery
        from app.modules.campaigns.delivery_service import CampaignDeliveryService

        deliv_stmt = select(CampaignDelivery).where(
            (CampaignDelivery.email_id == matched_email.id)
            | (
                (CampaignDelivery.message_id.is_not(None))
                & (CampaignDelivery.message_id == matched_email.message_id)
            )
        )
        deliv_res = await db.execute(deliv_stmt)
        matched_delivery = deliv_res.scalars().first()
        if matched_delivery:
            await CampaignDeliveryService.record_bounce_event(
                db=db,
                company_id=account.company_id,
                delivery_id=matched_delivery.id,
                diagnostic_text=diagnostic_text,
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

    @classmethod
    async def match_and_process_campaign_reply(
        cls,
        db: AsyncSession,
        account: EmailAccount,
        parsed: ParsedEmail,
        thread_id: Optional[int],
        is_reply_to_outgoing: bool,
    ) -> int:
        """Match an incoming genuine reply to an active campaign recipient and auto-stop follow-up sequence.

        Tenant-isolated to account.company_id.
        Only runs when cls.is_genuine_reply(parsed) is True.
        
        Matching criteria:
        1. CampaignDelivery.message_id is in parsed in_reply_to or references headers, OR
        2. is_reply_to_outgoing is True, thread_id == delivery.thread_id, and recipient.email == sender.
        
        Actions on match:
        - recipient.replied_at = parsed.date or now_utc
        - recipient.stopped_reason = 'REPLIED'
        - recipient.next_step_due_at = None
        - If recipient.status == 'ACTIVE', transition to 'STOPPED'
        """
        if not cls.is_genuine_reply(parsed):
            return 0

        from email.utils import parseaddr
        from sqlalchemy import or_, func
        from app.modules.campaigns.models import (
            Campaign,
            CampaignDelivery,
            CampaignRecipient,
            CampaignRecipientStatus,
            CampaignRecipientStopReason,
        )
        from app.modules.emails.thread_service import EmailThreadService

        candidate_ids = []
        if parsed.in_reply_to:
            candidate_ids.extend(EmailThreadService.extract_message_ids(parsed.in_reply_to))
            clean_in_reply = parsed.in_reply_to.strip()
            if clean_in_reply and clean_in_reply not in candidate_ids:
                candidate_ids.append(clean_in_reply)
        if parsed.references_header:
            candidate_ids.extend(EmailThreadService.extract_message_ids(parsed.references_header))
            clean_ref = parsed.references_header.strip()
            if clean_ref and clean_ref not in candidate_ids:
                candidate_ids.append(clean_ref)

        sender_email = parseaddr(parsed.sender)[1].strip().lower() if parsed.sender else ""
        if not sender_email:
            return 0

        # An incoming email originating from the company's own mailbox or campaign sender cannot be a recipient reply
        acc_email = (account.email_address or "").strip().lower()
        if sender_email == acc_email:
            return 0

        conditions = []
        if candidate_ids:
            conditions.append(CampaignDelivery.message_id.in_(candidate_ids))
        if is_reply_to_outgoing and thread_id is not None:
            conditions.append(CampaignDelivery.thread_id == thread_id)

        if not conditions:
            return 0

        from app.modules.email_accounts.models import EmailAccount
        stmt = (
            select(CampaignRecipient, CampaignDelivery)
            .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
            .join(Campaign, CampaignDelivery.campaign_id == Campaign.id)
            .join(EmailAccount, Campaign.email_account_id == EmailAccount.id)
            .where(
                Campaign.company_id == account.company_id,
                func.lower(CampaignRecipient.email) == sender_email,
                func.lower(EmailAccount.email_address) != sender_email,
                or_(*conditions),
            )
        )
        res = await db.execute(stmt)
        rows = res.all()

        matched_count = 0
        processed_recipient_ids = set()
        reply_ts = parsed.date or datetime.now(timezone.utc)
        if reply_ts.tzinfo is None:
            reply_ts = reply_ts.replace(tzinfo=timezone.utc)

        for recipient, delivery in rows:
            if recipient.id in processed_recipient_ids:
                continue
            processed_recipient_ids.add(recipient.id)

            if not recipient.replied_at:
                recipient.replied_at = reply_ts
            recipient.stopped_reason = CampaignRecipientStopReason.REPLIED.value
            recipient.next_step_due_at = None
            if recipient.status in (CampaignRecipientStatus.ACTIVE.value, CampaignRecipientStatus.SENT.value):
                recipient.status = CampaignRecipientStatus.STOPPED.value
            matched_count += 1
            logger.info(
                "Matched genuine campaign reply for recipient %d (%s) in campaign %d. Follow-ups auto-stopped.",
                recipient.id,
                recipient.email,
                recipient.campaign_id,
            )

        if matched_count > 0:
            await db.flush()
            from app.modules.campaigns.delivery_service import CampaignDeliveryService
            camp_ids = {recipient.campaign_id for recipient, _ in rows}
            for c_id in camp_ids:
                try:
                    await CampaignDeliveryService.check_and_finalize_campaign_completion(c_id, db=db)
                except Exception as comp_err:
                    logger.warning("Error checking completion for campaign %d on reply match: %s", c_id, comp_err)

        return matched_count

