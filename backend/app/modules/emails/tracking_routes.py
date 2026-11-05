from datetime import timedelta
import logging
import secrets
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.emails.models import TrackingTokenType, TrackingEventType
from app.modules.emails.tracking_schemas import (
    TrackingTokenIssueRequest,
    TrackingTokenIssueResponse,
)
from app.modules.emails.tracking_service import EmailTrackingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Internal Tracking"])
public_tracking_router = APIRouter(tags=["Public Tracking"])


def verify_tracking_internal_secret(
    x_tracking_internal_secret: Optional[str] = Header(None, alias="X-Tracking-Internal-Secret"),
    authorization: Optional[str] = Header(None),
) -> str:
    """Validate server-to-server authentication using constant-time comparison.
    
    Accepts the secret via either 'X-Tracking-Internal-Secret' header
    or 'Authorization: Bearer <secret>' header.
    Never logs secrets or exposes details to unauthorized callers.
    """
    expected_secret = (settings.TRACKING_INTERNAL_SECRET or "").strip()
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal tracking service authentication is not configured on the server",
        )

    provided = None
    if x_tracking_internal_secret and x_tracking_internal_secret.strip():
        provided = x_tracking_internal_secret.strip()
    elif authorization and authorization.strip().startswith("Bearer "):
        provided = authorization.strip()[7:].strip()

    if not provided or not secrets.compare_digest(provided, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing tracking internal secret",
        )

    return provided


@router.post(
    "/internal/tracking/tokens",
    response_model=TrackingTokenIssueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue secure tracking token (server-to-server internal API)",
    dependencies=[Depends(verify_tracking_internal_secret)],
)
async def issue_tracking_token(
    payload: TrackingTokenIssueRequest,
    db: AsyncSession = Depends(get_db),
) -> TrackingTokenIssueResponse:
    """Issue a high-entropy tracking token and return the public tracking URL.
    
    Accessible exclusively to authenticated server-to-server callers.
    Guarantees:
    - Opaque token generation and SHA-256 hash persistence.
    - Idempotency support: Repeated requests with identical idempotency_key
      yield the same raw token and tracking URL without creating duplicate records.
    - Rejects idempotency key re-use with different destination or parameters (409 Conflict).
    - Server-side destination URL validation.
    """
    if payload.token_type == "CLICK" and not payload.destination_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="destination_url is required when creating a CLICK tracking token",
        )

    expires_in = timedelta(seconds=payload.expires_in_seconds) if payload.expires_in_seconds else None

    try:
        token_rec, raw_token = await EmailTrackingService.create_tracking_token(
            db=db,
            company_id=payload.company_id,
            email_id=payload.email_id,
            token_type=payload.token_type,
            destination_url=payload.destination_url,
            campaign_id=payload.campaign_id,
            recipient_id=payload.recipient_id,
            delivery_id=payload.delivery_id,
            expires_in=expires_in,
            idempotency_key=payload.idempotency_key,
            internal_secret=settings.TRACKING_INTERNAL_SECRET,
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    base_url = settings.get_tracking_base_url()
    prefix = "c" if payload.token_type == "CLICK" else ("o" if payload.token_type == "OPEN" else "u")
    tracking_url = f"{base_url}/t/{prefix}/{raw_token}"

    return TrackingTokenIssueResponse(
        token_id=token_rec.id,
        raw_token=raw_token,
        token_type=token_rec.token_type,
        tracking_url=tracking_url,
        destination_url=token_rec.destination_url,
        expires_at=token_rec.expires_at,
        created_at=token_rec.created_at,
    )


@public_tracking_router.get(
    "/t/c/{token}",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Track email link click and redirect to destination",
)
async def track_click_and_redirect(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public click tracking redirect endpoint.
    
    Validates token from server-side database, records unclassified click event,
    and redirects (HTTP 302) to the pre-configured destination URL.
    
    Security & Reliability Rules:
    - Token validated strictly against stored hash; revoked or expired tokens return 404.
    - Destination URL resolved solely from server record. Query overrides are ignored.
    - Fails closed: if click event cannot be recorded/committed, returns 500 without redirect.
    - Emits Cache-Control: no-store headers to prevent intermediate/client caching.
    """
    token_record = await EmailTrackingService.resolve_and_validate_token(
        db=db,
        raw_token=token,
        expected_type=TrackingTokenType.CLICK,
    )
    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracking link is invalid, expired, or has been disabled",
        )

    destination = token_record.destination_url
    if not destination:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No destination configured for this tracking link",
        )

    parsed = urlparse(destination)
    if parsed.scheme.lower() not in ("http", "https"):
        logger.warning(
            "Blocked redirect to unsafe scheme '%s' for token id=%d",
            parsed.scheme,
            token_record.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect destination scheme",
        )

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    token_id = token_record.id

    try:
        await EmailTrackingService.record_tracking_event(
            db=db,
            token=token_record,
            event_type=TrackingEventType.CLICK,
            ip_address=client_ip,
            user_agent=user_agent,
            is_bot=None,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Failed to record click event for token id=%d: %s",
            token_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record tracking event",
        )

    response = RedirectResponse(
        url=destination,
        status_code=status.HTTP_302_FOUND,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
