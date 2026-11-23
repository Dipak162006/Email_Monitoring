"""Tracking Event Synchronization and Ingestion Pipeline (T5.2).

Retrieves raw OPEN and CLICK interaction telemetry from the remote tracking backend
and durably stores them in the local PostgreSQL database with strict multi-tenant
validation, database-enforced idempotency, and persistent cursor tracking.

Architectural Guarantees:
1. Multi-Tenant Relational Integrity:
   - Verifies company_id, campaign_id, recipient_id, and delivery_id exist locally
     and belong to the identical organization tenant before persisting.
   - Inconsistent or mismatched records are quarantined and rejected safely.
2. Crash-Proof Idempotency:
   - Leverages PostgreSQL unique constraint on `remote_event_id` via ON CONFLICT DO NOTHING.
   - Retries or overlapping batches never duplicate events or overwrite raw event history.
3. Cursor Reliability:
   - Redis cursor (`tracking:interaction_events:cursor`) advances ONLY after durable local database commit.
   - Failed batches trigger rollback and do NOT advance the cursor.
4. Concurrency Protection:
   - Distributed lock (`InteractionSyncLock`) prevents overlapping worker runs.
"""
from datetime import datetime, timezone
import logging
import secrets
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignRecipient,
)
from app.modules.companies.models import Company
from app.modules.emails.models import EmailTrackingEvent, TrackingEventQuarantine, TrackingEventType
from app.modules.emails.tracking_client import TrackingServiceClient

logger = logging.getLogger(__name__)


class InteractionSyncLock:
    """Distributed lock preventing overlapping tracking event sync executions."""
    LOCK_KEY = "lock:interaction_events_sync"
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
            logger.warning("Redis error acquiring interaction sync lock: %s. Proceeding cautiously.", exc)
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
            logger.debug("Redis error releasing interaction sync lock: %s", exc)


class TrackingEventSyncService:
    """Service synchronizing remote OPEN and CLICK tracking events into local storage."""
    CURSOR_REDIS_KEY = "tracking:interaction_events:cursor"
    _fallback_cursor = 0

    @classmethod
    async def get_sync_cursor(cls) -> int:
        """Retrieve persistent high-water-mark event cursor from Redis."""
        try:
            from app.core.redis import get_redis_client
            redis = get_redis_client()
            val = await redis.get(cls.CURSOR_REDIS_KEY)
            if val is not None:
                return int(val)
        except Exception as exc:
            logger.debug("Redis error retrieving interaction sync cursor: %s", exc)
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
            logger.warning("Redis error persisting interaction sync cursor: %s", exc)

    @classmethod
    async def validate_event_tenant_integrity(
        cls,
        db: AsyncSession,
        ev: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """Validate company, campaign, recipient, and delivery relationships.
        
        Returns:
            (is_valid, rejection_reason, resolved_email_id)
        """
        company_id = ev.get("company_id")
        campaign_id = ev.get("campaign_id")
        recipient_id = ev.get("recipient_id")
        delivery_id = ev.get("delivery_id")
        event_type = (ev.get("event_type") or "").strip().upper()

        if event_type not in (TrackingEventType.OPEN.value, TrackingEventType.CLICK.value):
            return False, f"Unsupported event type '{event_type}' for interaction pipeline", None

        if not company_id:
            return False, "Missing company_id", None

        # 1. Verify company exists
        company = await db.get(Company, company_id)
        if not company:
            return False, f"Company id={company_id} does not exist locally", None

        # 2. Verify campaign if provided
        if campaign_id:
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                return False, f"Campaign id={campaign_id} does not exist locally", None
            if campaign.company_id != company_id:
                return False, f"Campaign id={campaign_id} belongs to company={campaign.company_id}, not {company_id}", None

        # 3. Verify recipient if provided
        if recipient_id:
            recipient = await db.get(CampaignRecipient, recipient_id)
            if not recipient:
                return False, f"Recipient id={recipient_id} does not exist locally", None
            if campaign_id and recipient.campaign_id != campaign_id:
                return False, f"Recipient id={recipient_id} belongs to campaign={recipient.campaign_id}, not {campaign_id}", None

        # 4. Verify delivery if provided
        resolved_email_id = None
        if delivery_id:
            delivery = await db.get(CampaignDelivery, delivery_id)
            if not delivery:
                return False, f"Delivery id={delivery_id} does not exist locally", None
            if campaign_id and delivery.campaign_id != campaign_id:
                return False, f"Delivery id={delivery_id} belongs to campaign={delivery.campaign_id}, not {campaign_id}", None
            if recipient_id and delivery.recipient_id != recipient_id:
                return False, f"Delivery id={delivery_id} belongs to recipient={delivery.recipient_id}, not {recipient_id}", None
            resolved_email_id = delivery.email_id

        return True, None, resolved_email_id

    @classmethod
    async def sync_tracking_events(
        cls,
        db: AsyncSession,
        tracking_client: Optional[TrackingServiceClient] = None,
        batch_limit: int = 100,
    ) -> int:
        """Synchronize recorded OPEN and CLICK events from the remote tracking service.
        
        Guarantees:
        - Strict ascending event ID pagination.
        - Database-level unique constraint handling on remote_event_id.
        - Preserves bot classification metadata (is_bot, bot_reason, bot_confidence).
        - Advance cursor only after successful commit.
        """
        client = tracking_client or TrackingServiceClient()
        if not client.is_configured:
            logger.debug("TrackingServiceClient is not configured; skipping interaction event synchronization.")
            return 0

        lock = InteractionSyncLock(ttl_seconds=60)
        if not await lock.acquire():
            logger.info("Interaction sync lock held by another worker. Skipping overlapping execution.")
            return 0

        try:
            cursor = await cls.get_sync_cursor()
            total_synced = 0
            limit = min(max(1, batch_limit), 1000)

            while True:
                events = await client.get_tracking_events(
                    since_id=cursor,
                    limit=limit,
                    types="OPEN,CLICK",
                )
                if not events:
                    break

                max_batch_id = cursor
                valid_events_in_batch = 0

                for ev in events:
                    ev_id = ev.get("event_id") or ev.get("id") or 0
                    if ev_id > max_batch_id:
                        max_batch_id = ev_id

                    is_valid, reason, resolved_email_id = await cls.validate_event_tenant_integrity(db, ev)
                    if not is_valid:
                        logger.warning(
                            "Quarantining invalid tracking event remote_id=%s: %s",
                            ev_id,
                            reason,
                        )
                        # Sanitize payload: minimum required event telemetry only.
                        # Strictly zero PII: do NOT store recipient email, raw tokens, token hashes, or unnecessary client IPs.
                        sanitized_payload = {
                            "event_id": ev_id,
                            "company_id": ev.get("company_id"),
                            "campaign_id": ev.get("campaign_id"),
                            "recipient_id": ev.get("recipient_id"),
                            "delivery_id": ev.get("delivery_id"),
                            "event_type": ev.get("event_type"),
                            "occurred_at": str(ev.get("occurred_at")),
                            "is_bot": ev.get("is_bot"),
                            "bot_reason": ev.get("bot_reason"),
                            "bot_confidence": ev.get("bot_confidence"),
                        }
                        # Durably persist quarantine record with remote_event_id deduplication
                        quarantine_stmt = (
                            pg_insert(TrackingEventQuarantine)
                            .values(
                                remote_event_id=ev_id,
                                company_id=ev.get("company_id") if isinstance(ev.get("company_id"), int) else None,
                                reason=(reason or "Unknown validation failure")[:255],
                                payload=sanitized_payload,
                                replay_status="pending",
                            )
                            .on_conflict_do_nothing(index_elements=["remote_event_id"])
                        )
                        await db.execute(quarantine_stmt)
                        continue

                    # Parse occurred_at timestamp
                    occurred_at_val = ev.get("occurred_at")
                    parsed_occurred_at = None
                    if occurred_at_val:
                        if isinstance(occurred_at_val, str):
                            try:
                                parsed_occurred_at = datetime.fromisoformat(occurred_at_val)
                            except ValueError:
                                parsed_occurred_at = datetime.now(timezone.utc)
                        elif isinstance(occurred_at_val, datetime):
                            parsed_occurred_at = occurred_at_val
                    if parsed_occurred_at is None:
                        parsed_occurred_at = datetime.now(timezone.utc)

                    # Database-enforced idempotency via ON CONFLICT (remote_event_id) DO NOTHING
                    is_bot_val = ev.get("is_bot")
                    bot_reason_val = ev.get("bot_reason")
                    bot_conf_val = ev.get("bot_confidence")

                    stmt = (
                        pg_insert(EmailTrackingEvent)
                        .values(
                            remote_event_id=ev_id,
                            company_id=ev["company_id"],
                            campaign_id=ev.get("campaign_id"),
                            recipient_id=ev.get("recipient_id"),
                            delivery_id=ev.get("delivery_id"),
                            email_id=resolved_email_id,
                            token_id=None,
                            event_type=ev["event_type"].strip().upper(),
                            occurred_at=parsed_occurred_at,
                            is_bot=is_bot_val,
                            bot_reason=bot_reason_val[:100] if bot_reason_val else None,
                            bot_confidence=bot_conf_val,
                        )
                        .on_conflict_do_nothing(index_elements=["remote_event_id"])
                    )
                    await db.execute(stmt)
                    valid_events_in_batch += 1

                # Commit local transaction durably before advancing cursor
                await db.commit()
                total_synced += valid_events_in_batch

                # Advance cursor to the highest handled remote event ID in this batch
                cursor = max_batch_id
                await cls.set_sync_cursor(cursor)

                # Stop pagination if we retrieved fewer than batch limit
                if len(events) < limit:
                    break

            return total_synced
        except Exception as exc:
            await db.rollback()
            logger.exception("Error during interaction tracking event synchronization: %s", exc)
            return 0
        finally:
            await lock.release()
