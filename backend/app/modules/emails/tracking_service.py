from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import logging
import secrets
from typing import Optional, Tuple, Union
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.emails.models import (
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)

logger = logging.getLogger(__name__)


class EmailTrackingService:
    """Secure token lifecycle and event tracking service.
    
    Implements cryptographic opaque token generation (using secrets.token_urlsafe),
    one-way SHA-256 hash persistence, constant-time validation, and append-only
    interaction event logging without exposing sensitive data.
    """

    @staticmethod
    def generate_raw_token(nbytes: int = 32) -> str:
        """Generate a cryptographically secure, high-entropy opaque token.
        
        Uses secrets.token_urlsafe to prevent enumeration, sequential attacks,
        and predictable URL parameters.
        """
        return secrets.token_urlsafe(nbytes)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Derive the deterministic SHA-256 hex digest of a raw token.
        
        Only this 64-character hash is ever stored in the database or indexed.
        """
        if not raw_token or not isinstance(raw_token, str):
            raise ValueError("Token must be a non-empty string")
        return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def derive_idempotent_raw_token(
        idempotency_key: str,
        company_id: int,
        email_id: int,
        internal_secret: Optional[str] = None,
    ) -> str:
        """Derive a deterministic, high-entropy raw token for idempotent requests.
        
        Ensures retried requests yield the identical raw token without persisting
        the raw token in the database.
        """
        key = (internal_secret or "pulsemail-idempotent-default").encode("utf-8")
        msg = f"{idempotency_key.strip()}:{company_id}:{email_id}".encode("utf-8")
        digest = hmac.new(key, msg, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    @classmethod
    async def create_tracking_token(
        cls,
        db: AsyncSession,
        company_id: int,
        email_id: int,
        token_type: Union[TrackingTokenType, str],
        destination_url: Optional[str] = None,
        campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        delivery_id: Optional[int] = None,
        expires_in: Optional[timedelta] = None,
        expires_at: Optional[datetime] = None,
        idempotency_key: Optional[str] = None,
        internal_secret: Optional[str] = None,
    ) -> Tuple[EmailTrackingToken, str]:
        """Create and persist a tracking token record, returning the record and raw token.
        
        The raw token is returned to the immediate caller solely for constructing
        a future outbound tracking URL (pixel or redirect). Only the SHA-256 hash
        is written to the database. If an idempotency_key is provided and a token
        already exists, returns the existing record and its derived raw token.
        """
        # Validate purpose
        type_str = token_type.value if hasattr(token_type, "value") else str(token_type).strip().upper()
        valid_types = {t.value for t in TrackingTokenType}
        if type_str not in valid_types:
            raise ValueError(f"Invalid token purpose '{token_type}'. Must be one of: {', '.join(valid_types)}")

        # Destination URL is required for click tracking tokens
        if type_str == TrackingTokenType.CLICK.value and not destination_url:
            raise ValueError("destination_url is required when creating a CLICK tracking token")

        clean_idempotency_key = idempotency_key.strip() if idempotency_key else None

        # Check for existing token with same idempotency key
        if clean_idempotency_key:
            stmt = select(EmailTrackingToken).where(
                EmailTrackingToken.idempotency_key == clean_idempotency_key
            )
            result = await db.execute(stmt)
            existing = result.scalars().first()
            if existing is not None:
                clean_dest = destination_url.strip() if destination_url else None
                if existing.destination_url != clean_dest or existing.token_type != type_str:
                    raise ValueError(
                        f"Idempotency conflict: Key '{clean_idempotency_key}' was already registered with different parameters"
                    )
                raw_token = cls.derive_idempotent_raw_token(
                    clean_idempotency_key,
                    existing.company_id,
                    existing.email_id,
                    internal_secret,
                )
                logger.debug(
                    "Idempotent hit for token id=%d idempotency_key=%s",
                    existing.id,
                    clean_idempotency_key,
                )
                return existing, raw_token

        # Expiration calculation
        computed_expires_at: Optional[datetime] = None
        if expires_at is not None:
            computed_expires_at = expires_at
        elif expires_in is not None:
            computed_expires_at = datetime.now(timezone.utc) + expires_in

        if clean_idempotency_key:
            raw_token = cls.derive_idempotent_raw_token(
                clean_idempotency_key,
                company_id,
                email_id,
                internal_secret,
            )
        else:
            raw_token = cls.generate_raw_token()

        token_hash = cls.hash_token(raw_token)

        token_record = EmailTrackingToken(
            company_id=company_id,
            email_id=email_id,
            campaign_id=campaign_id,
            recipient_id=recipient_id,
            delivery_id=delivery_id,
            token_hash=token_hash,
            token_type=type_str,
            destination_url=destination_url.strip() if destination_url else None,
            idempotency_key=clean_idempotency_key,
            is_revoked=False,
            expires_at=computed_expires_at,
        )

        db.add(token_record)
        try:
            await db.flush()
        except IntegrityError:
            if clean_idempotency_key:
                stmt = select(EmailTrackingToken).where(
                    EmailTrackingToken.idempotency_key == clean_idempotency_key
                )
                result = await db.execute(stmt)
                existing = result.scalars().first()
                if existing is not None:
                    clean_dest = destination_url.strip() if destination_url else None
                    if existing.destination_url != clean_dest or existing.token_type != type_str:
                        raise ValueError(
                            f"Idempotency conflict: Key '{clean_idempotency_key}' was already registered with different parameters"
                        )
                    raw_token = cls.derive_idempotent_raw_token(
                        clean_idempotency_key,
                        existing.company_id,
                        existing.email_id,
                        internal_secret,
                    )
                    return existing, raw_token
            raise

        logger.debug(
            "Created tracking token id=%d type=%s for email_id=%d company_id=%d",
            token_record.id,
            type_str,
            email_id,
            company_id,
        )
        return token_record, raw_token

    @classmethod
    async def resolve_and_validate_token(
        cls,
        db: AsyncSession,
        raw_token: str,
        expected_type: Optional[Union[TrackingTokenType, str]] = None,
        expected_company_id: Optional[int] = None,
        expected_email_id: Optional[int] = None,
    ) -> Optional[EmailTrackingToken]:
        """Resolve a raw token against its stored SHA-256 hash and validate state.
        
        Fails safely and returns None if the token is:
        - Malformed or blank
        - Not found in the database
        - Revoked (is_revoked == True)
        - Expired (expires_at in the past)
        - Purpose-mismatched (different from expected_type)
        - Context-mismatched (different company_id or email_id if provided)
        """
        if not raw_token or not isinstance(raw_token, str) or not raw_token.strip():
            return None

        token_hash = cls.hash_token(raw_token)

        stmt = select(EmailTrackingToken).where(EmailTrackingToken.token_hash == token_hash)
        result = await db.execute(stmt)
        token_record = result.scalars().first()

        if token_record is None:
            return None

        # Check revocation
        if token_record.is_revoked:
            logger.debug("Token id=%d is revoked", token_record.id)
            return None

        # Check expiration
        if token_record.expires_at is not None:
            now = datetime.now(timezone.utc)
            exp = token_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                logger.debug("Token id=%d expired at %s", token_record.id, exp)
                return None

        # Check purpose binding
        if expected_type is not None:
            exp_type_str = expected_type.value if hasattr(expected_type, "value") else str(expected_type).strip().upper()
            if token_record.token_type != exp_type_str:
                logger.debug("Token id=%d purpose mismatch: got %s, expected %s", token_record.id, token_record.token_type, exp_type_str)
                return None

        # Check tenant context
        if expected_company_id is not None and token_record.company_id != expected_company_id:
            logger.debug("Token id=%d tenant mismatch: got %d, expected %d", token_record.id, token_record.company_id, expected_company_id)
            return None

        # Check email context
        if expected_email_id is not None and token_record.email_id != expected_email_id:
            logger.debug("Token id=%d email mismatch: got %d, expected %d", token_record.id, token_record.email_id, expected_email_id)
            return None

        return token_record

    @classmethod
    async def revoke_token(
        cls,
        db: AsyncSession,
        token: EmailTrackingToken,
    ) -> EmailTrackingToken:
        """Revoke a tracking token, preventing future interaction validation."""
        token.is_revoked = True
        await db.flush()
        logger.debug("Revoked tracking token id=%d", token.id)
        return token

    @classmethod
    async def record_tracking_event(
        cls,
        db: AsyncSession,
        token: EmailTrackingToken,
        event_type: Union[TrackingEventType, str],
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        is_bot: Optional[bool] = None,
        bot_reason: Optional[str] = None,
        bot_confidence: Optional[float] = None,
        occurred_at: Optional[datetime] = None,
    ) -> EmailTrackingEvent:
        """Append an interaction telemetry event linked to the validated token.
        
        Preserves strict tenant and message scoping derived directly from
        the authoritative EmailTrackingToken record.
        """
        evt_type_str = event_type.value if hasattr(event_type, "value") else str(event_type).strip().upper()
        valid_types = {t.value for t in TrackingEventType}
        if evt_type_str not in valid_types:
            raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {', '.join(valid_types)}")

        event = EmailTrackingEvent(
            company_id=token.company_id,
            token_id=token.id,
            email_id=token.email_id,
            campaign_id=token.campaign_id,
            recipient_id=token.recipient_id,
            delivery_id=token.delivery_id,
            event_type=evt_type_str,
            user_agent=user_agent[:1000] if user_agent else None,
            ip_address=ip_address.strip() if ip_address else None,
            is_bot=is_bot,
            bot_reason=bot_reason[:100] if bot_reason else None,
            bot_confidence=bot_confidence,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

        db.add(event)
        await db.flush()
        return event

