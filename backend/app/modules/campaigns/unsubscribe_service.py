"""Secure unsubscribe service implementing RFC 8058 one-click unsubscription,
opaque token resolution, company suppression recording, and follow-up cancellation.
"""
from datetime import datetime, timezone
import logging
import secrets
from typing import Optional, Union
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import build_unsubscribe_url, decode_unsubscribe_token
from app.modules.companies.models import Company
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import normalize_and_validate_email
from app.modules.emails.models import (
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.tracking_service import EmailTrackingService

logger = logging.getLogger(__name__)


def _extract_ip(request: Request) -> Optional[str]:
    """Safely resolve client IP without introducing circular imports."""
    try:
        from app.modules.emails.tracking_routes import extract_client_ip
        return extract_client_ip(request)
    except Exception:
        return request.client.host if request.client else None


UNSUBSCRIBE_CONFIRMATION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Confirm Unsubscribe</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
    .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 40px 32px; max-width: 480px; width: 100%; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05); text-align: center; }
    .icon { width: 56px; height: 56px; background: #fef3c7; color: #d97706; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 26px; font-weight: bold; }
    h1 { font-size: 22px; font-weight: 700; color: #0f172a; margin: 0 0 10px; }
    p { font-size: 14px; color: #64748b; line-height: 1.6; margin: 0 0 24px; }
    .btn { display: inline-block; background-color: #ef4444; color: #ffffff; border: none; border-radius: 8px; padding: 12px 28px; font-size: 15px; font-weight: 600; cursor: pointer; text-decoration: none; transition: background-color 0.15s ease; width: 100%; box-sizing: border-box; }
    .btn:hover { background-color: #dc2626; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">!</div>
    <h1>Unsubscribe Confirmation</h1>
    <p>Please confirm that you want to unsubscribe from future email communications from this organization.</p>
    <form method="POST">
      <button type="submit" class="btn">Confirm Unsubscribe</button>
    </form>
  </div>
</body>
</html>"""

UNSUBSCRIBE_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribed Successfully</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
    .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 40px 32px; max-width: 480px; width: 100%; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05); text-align: center; }
    .icon { width: 56px; height: 56px; background: #ecfdf5; color: #059669; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 28px; font-weight: bold; }
    h1 { font-size: 22px; font-weight: 700; color: #0f172a; margin: 0 0 10px; }
    p { font-size: 14px; color: #64748b; line-height: 1.6; margin: 0 0 24px; }
    .email-badge { display: inline-block; background: #f1f5f9; color: #334155; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; font-family: monospace; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10003;</div>
    <h1>You're Unsubscribed</h1>
    <p>Your email address <span class="email-badge">{email}</span> has been removed from future mailings from this organization.</p>
  </div>
</body>
</html>"""


class UnsubscribeSyncLock:
    """Distributed lock preventing overlapping unsubscribe sync executions."""
    LOCK_KEY = "lock:unsubscribe_sync"
    RELEASE_SCRIPT = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
    """

    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self.token = secrets.token_hex(16)
        self.acquired = False

    async def acquire(self) -> bool:
        try:
            from app.core.redis import get_redis_client
            redis = get_redis_client()
            res = await redis.set(self.LOCK_KEY, self.token, nx=True, ex=self.ttl)
            self.acquired = bool(res)
            return self.acquired
        except Exception as exc:
            logger.debug("Redis lock unavailable, allowing sync to proceed: %s", exc)
            self.acquired = True
            return True

    async def release(self) -> None:
        if not self.acquired:
            return
        try:
            from app.core.redis import get_redis_client
            redis = get_redis_client()
            await redis.eval(self.RELEASE_SCRIPT, 1, self.LOCK_KEY, self.token)
        except Exception as exc:
            logger.debug("Redis lock release failed: %s", exc)


class UnsubscribeService:
    """Unified service for secure RFC 8058 unsubscription, token lifecycle, and local suppression synchronization."""

    CURSOR_REDIS_KEY = "tracking:unsubscribe_sync:cursor"
    _fallback_cursor: int = 0

    @classmethod
    async def get_sync_cursor(cls) -> int:
        """Retrieve persistent high-water-mark event cursor."""
        try:
            from app.core.redis import get_redis_client
            redis = get_redis_client()
            val = await redis.get(cls.CURSOR_REDIS_KEY)
            if val is not None:
                return int(val)
        except Exception as exc:
            logger.debug("Redis error retrieving sync cursor: %s", exc)
        return cls._fallback_cursor

    @classmethod
    async def set_sync_cursor(cls, cursor: int) -> None:
        """Persist high-water-mark event cursor after transaction commit."""
        cls._fallback_cursor = cursor
        try:
            from app.core.redis import get_redis_client
            redis = get_redis_client()
            await redis.set(cls.CURSOR_REDIS_KEY, str(cursor))
        except Exception as exc:
            logger.warning("Redis error persisting sync cursor: %s", exc)

    @classmethod
    async def resolve_token(cls, token: str, db: AsyncSession) -> dict:
        """Resolve and validate an unsubscribe token against opaque token storage or signed JWT.
        
        Security Rules:
        - Validates purpose strictly (must be UNSUBSCRIBE).
        - Rejects expired or revoked tokens with HTTP 400.
        - Rejects tampered, malformed, or blank tokens with HTTP 400.
        - Returns bound company_id, campaign_id, recipient_id, and email.
        """
        if not token or not isinstance(token, str) or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or empty unsubscribe token.",
            )

        clean_token = token.strip()

        # 1. Inspect opaque token hash in email_tracking_tokens
        token_hash = EmailTrackingService.hash_token(clean_token)
        stmt = select(EmailTrackingToken).where(EmailTrackingToken.token_hash == token_hash)
        res = await db.execute(stmt)
        tracking_token = res.scalars().first()

        if tracking_token:
            # Check purpose binding
            if tracking_token.token_type != TrackingTokenType.UNSUBSCRIBE.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Token purpose mismatch: expected UNSUBSCRIBE, got {tracking_token.token_type}",
                )

            # Check revocation
            if tracking_token.is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The unsubscribe link has been revoked or disabled.",
                )

            # Check expiration
            if tracking_token.expires_at is not None:
                now = datetime.now(timezone.utc)
                exp = tracking_token.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The unsubscribe link has expired.",
                    )

            # Resolve email from recipient if present
            email: Optional[str] = None
            if tracking_token.recipient_id:
                recip = await db.get(CampaignRecipient, tracking_token.recipient_id)
                if recip:
                    email = recip.email

            return {
                "token_type": "opaque",
                "tracking_token": tracking_token,
                "company_id": tracking_token.company_id,
                "campaign_id": tracking_token.campaign_id,
                "recipient_id": tracking_token.recipient_id,
                "delivery_id": tracking_token.delivery_id,
                "email": email,
            }

        # 2. Fallback to signed JWT token for backward compatibility
        try:
            payload = decode_unsubscribe_token(clean_token)
            return {
                "token_type": "jwt",
                "tracking_token": None,
                "company_id": payload["company_id"],
                "campaign_id": payload.get("campaign_id"),
                "recipient_id": payload.get("recipient_id"),
                "delivery_id": payload.get("delivery_id"),
                "email": payload["email"],
            }
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The unsubscribe link has expired.",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or tampered unsubscribe token.",
            )

    @classmethod
    async def handle_get(cls, token: str, request: Request, db: AsyncSession) -> Response:
        """Handle GET unsubscribe request safely without modifying any database state.
        
        Security Guarantees:
        - Validates the token exists and is valid.
        - Never unsubscribes, never modifies recipient, and never creates suppression records.
        - Safe against automated email scanners, security prefetchers, and client crawlers.
        """
        token_data = await cls.resolve_token(token=token, db=db)
        accept_header = request.headers.get("accept", "").lower()

        # JSON response for programmatic API checks
        if "application/json" in accept_header and "text/html" not in accept_header:
            return JSONResponse(
                {
                    "status": "pending_confirmation",
                    "message": "Unsubscribe requires confirmation. Submit a POST request to this URL.",
                    "company_id": token_data.get("company_id"),
                },
                status_code=status.HTTP_200_OK,
            )

        # Standard HTML confirmation page
        return HTMLResponse(content=UNSUBSCRIBE_CONFIRMATION_HTML, status_code=status.HTTP_200_OK)

    @classmethod
    async def handle_post(cls, token: str, request: Request, db: AsyncSession) -> Response:
        """Handle RFC 8058 One-Click POST request to execute unsubscription idempotently.
        
        Cross-Backend Safe:
        - Standalone Render tracking backend (no companies):
          Durably records the UNSUBSCRIBE event into email_tracking_events and creates
          an opaque tracking token placeholder if a fallback JWT arrived. Never attempts
          to create records in company/suppression tables on Render PostgreSQL.
        - Local application backend (companies present):
          Directly inserts into suppression_list, marks CampaignRecipient records SUPPRESSED,
          and cancels pending sequence follow-ups.
        """
        token_data = await cls.resolve_token(token=token, db=db)
        company_id = token_data["company_id"]
        email = token_data.get("email")
        campaign_id = token_data.get("campaign_id")
        recipient_id = token_data.get("recipient_id")
        delivery_id = token_data.get("delivery_id")

        accept_header = request.headers.get("accept", "").lower()
        is_rfc_8058 = (
            "one-click" in request.headers.get("list-unsubscribe", "").lower()
            or "one-click" in request.headers.get("list-unsubscribe-post", "").lower()
        )
        is_browser = "text/html" in accept_header and not is_rfc_8058 and "application/json" not in accept_header

        # Check whether company records exist in the current database (Local vs Render)
        company_exists = False
        try:
            company_exists = (await db.get(Company, company_id)) is not None
        except Exception:
            company_exists = False

        # ---------------------------------------------------------------------
        # 1. Standalone Render Tracking Backend Path (No local companies in DB)
        # ---------------------------------------------------------------------
        if not company_exists:
            tracking_tok = token_data.get("tracking_token")
            if not tracking_tok:
                # Fallback JWT request hitting Render: Create an EmailTrackingToken so event can be linked
                clean_token = token.strip()
                tok_hash = EmailTrackingService.hash_token(clean_token)
                tracking_tok = await db.scalar(
                    select(EmailTrackingToken).where(EmailTrackingToken.token_hash == tok_hash)
                )
                if not tracking_tok:
                    dest = f"email:{email}" if email else None
                    tracking_tok = EmailTrackingToken(
                        company_id=company_id,
                        email_id=delivery_id or 0,
                        campaign_id=campaign_id,
                        recipient_id=recipient_id,
                        delivery_id=delivery_id,
                        destination_url=dest,
                        token_hash=tok_hash,
                        token_type=TrackingTokenType.UNSUBSCRIBE.value,
                        is_revoked=False,
                    )
                    db.add(tracking_tok)
                    await db.flush()

            await EmailTrackingService.record_tracking_event(
                db=db,
                token=tracking_tok,
                event_type=TrackingEventType.UNSUBSCRIBE,
                ip_address=_extract_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
            await db.commit()

            if is_browser:
                html = UNSUBSCRIBE_SUCCESS_HTML.replace("{email}", email or "your email address")
                return HTMLResponse(content=html, status_code=status.HTTP_200_OK)

            return JSONResponse(
                {"status": "unsubscribed", "company_id": company_id},
                status_code=status.HTTP_200_OK,
            )

        # ---------------------------------------------------------------------
        # 2. Local Application Backend Path (Company exists in local DB)
        # ---------------------------------------------------------------------
        if not email and recipient_id:
            recip_obj = await db.get(CampaignRecipient, recipient_id)
            if recip_obj:
                email = recip_obj.email

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipient email could not be resolved from token.",
            )

        try:
            norm_email = normalize_and_validate_email(email)
        except Exception:
            norm_email = email.strip().lower()

        # Idempotently add to company suppression list
        existing_supp = await db.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.company_id == company_id,
                SuppressionEntry.email == norm_email,
            )
        )
        if not existing_supp.scalar_one_or_none():
            entry = SuppressionEntry(
                company_id=company_id,
                email=norm_email,
                reason=SuppressionReason.UNSUBSCRIBE.value,
            )
            db.add(entry)

        # Stop all active/pending recipients for this company and email, and cancel follow-ups
        recip_stmt = (
            select(CampaignRecipient)
            .join(Campaign, CampaignRecipient.campaign_id == Campaign.id)
            .where(
                Campaign.company_id == company_id,
                CampaignRecipient.email == norm_email,
            )
        )
        recip_res = await db.execute(recip_stmt)
        for r in recip_res.scalars().all():
            r.status = CampaignRecipientStatus.SUPPRESSED.value
            r.stopped_reason = CampaignRecipientStopReason.UNSUBSCRIBED.value
            r.next_step_due_at = None

        # If tracking token present, record tracking event
        if token_data.get("tracking_token"):
            await EmailTrackingService.record_tracking_event(
                db=db,
                token=token_data["tracking_token"],
                event_type=TrackingEventType.UNSUBSCRIBE,
                ip_address=_extract_ip(request),
                user_agent=request.headers.get("user-agent"),
            )

        await db.commit()

        if is_browser:
            html = UNSUBSCRIBE_SUCCESS_HTML.replace("{email}", norm_email)
            return HTMLResponse(content=html, status_code=status.HTTP_200_OK)

        return JSONResponse(
            {"status": "unsubscribed", "email": norm_email, "company_id": company_id},
            status_code=status.HTTP_200_OK,
        )

    @classmethod
    async def build_campaign_unsubscribe_url(
        cls,
        company_id: int,
        recipient_id: Optional[int] = None,
        delivery_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
        recipient_email: Optional[str] = None,
        tracking_client: Optional[TrackingServiceClient] = None,
    ) -> str:
        """Construct a secure, opaque RFC 8058 unsubscribe URL for a campaign delivery.
        
        Prefers remote opaque tracking token issued via TrackingServiceClient.
        Falls back to signed JWT URL if tracking is unconfigured or unavailable.
        """
        client = tracking_client or TrackingServiceClient()
        if client.is_configured and delivery_id is not None:
            try:
                idempotency_key = f"unsub_{campaign_id}_{recipient_id}_{delivery_id}"
                token_resp = await client.issue_token(
                    company_id=company_id,
                    email_id=delivery_id,
                    token_type=TrackingTokenType.UNSUBSCRIBE,
                    campaign_id=campaign_id,
                    recipient_id=recipient_id,
                    delivery_id=delivery_id,
                    idempotency_key=idempotency_key,
                )
                if token_resp and token_resp.tracking_url:
                    return token_resp.tracking_url
            except Exception as exc:
                logger.warning("Failed to issue remote unsubscribe token: %s", exc)

        # Fallback to signed JWT unsubscribe URL with opaque IDs and encrypted email
        return build_unsubscribe_url(
            company_id=company_id,
            email=recipient_email or "",
            campaign_id=campaign_id,
            recipient_id=recipient_id,
            delivery_id=delivery_id,
        )

    @classmethod
    async def sync_remote_unsubscribes(
        cls,
        db: AsyncSession,
        tracking_client: Optional[TrackingServiceClient] = None,
    ) -> int:
        """Synchronize recorded unsubscriptions from the Render public tracking backend into local suppression.
        
        Reliability Guarantees:
        - Uses persistent cursor (high-water-mark) in Redis to avoid re-syncing or missing events.
        - Paginates in batches until all available pages are fetched.
        - Commits each batch to local PostgreSQL before advancing cursor.
        - Safe against concurrent sync tasks via UnsubscribeSyncLock.
        - Safe and idempotent across duplicate deliveries and retries.
        """
        client = tracking_client or TrackingServiceClient()
        if not client.is_configured:
            return 0

        lock = UnsubscribeSyncLock(ttl_seconds=60)
        if not await lock.acquire():
            logger.info("Unsubscribe sync lock held by another worker. Skipping overlapping execution.")
            return 0

        try:
            cursor = await cls.get_sync_cursor()
            total_synced = 0
            limit = 100

            while True:
                events = await client.get_unsubscribes(since_id=cursor, limit=limit)
                if not events:
                    break

                max_batch_id = cursor

                for ev in events:
                    ev_id = ev.get("event_id") or ev.get("id") or 0
                    if ev_id > max_batch_id:
                        max_batch_id = ev_id

                    company_id = ev.get("company_id")
                    recipient_id = ev.get("recipient_id")
                    email = ev.get("email")

                    if not company_id:
                        continue

                    # If recipient_id is present, resolve email and update recipient record
                    if recipient_id:
                        recip = await db.get(CampaignRecipient, recipient_id)
                        if recip:
                            if not email:
                                email = recip.email
                            recip.status = CampaignRecipientStatus.SUPPRESSED.value
                            recip.stopped_reason = CampaignRecipientStopReason.UNSUBSCRIBED.value
                            recip.next_step_due_at = None

                    if not email:
                        continue

                    try:
                        norm_email = normalize_and_validate_email(email)
                    except Exception:
                        norm_email = email.strip().lower()

                    # Idempotent suppression entry
                    existing = await db.execute(
                        select(SuppressionEntry).where(
                            SuppressionEntry.company_id == company_id,
                            SuppressionEntry.email == norm_email,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        db.add(
                            SuppressionEntry(
                                company_id=company_id,
                                email=norm_email,
                                reason=SuppressionReason.UNSUBSCRIBE.value,
                            )
                        )

                    # Stop all active/pending recipients for this company and email, and cancel follow-ups
                    all_recips = await db.execute(
                        select(CampaignRecipient)
                        .join(Campaign, CampaignRecipient.campaign_id == Campaign.id)
                        .where(
                            Campaign.company_id == company_id,
                            CampaignRecipient.email == norm_email,
                            CampaignRecipient.status.in_([
                                CampaignRecipientStatus.PENDING.value,
                                CampaignRecipientStatus.ACTIVE.value,
                                CampaignRecipientStatus.SENT.value,
                            ]),
                        )
                    )
                    for r in all_recips.scalars().all():
                        r.status = CampaignRecipientStatus.SUPPRESSED.value
                        r.stopped_reason = CampaignRecipientStopReason.UNSUBSCRIBED.value
                        r.next_step_due_at = None

                    total_synced += 1

                # Commit local suppression records for this batch
                await db.commit()

                # Advance cursor only after durable commit
                cursor = max_batch_id
                await cls.set_sync_cursor(cursor)

                # Stop pagination if we retrieved fewer than batch limit
                if len(events) < limit:
                    break

            return total_synced
        except Exception as exc:
            logger.warning("Error synchronizing remote unsubscribes: %s", exc)
            return 0
        finally:
            await lock.release()
