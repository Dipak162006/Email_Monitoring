from datetime import timedelta
import ipaddress
import logging
import secrets
from typing import List, Optional, Union
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
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


@router.get(
    "/unsubscribes",
    summary="Retrieve recorded unsubscribe events for synchronization with local suppression",
)
async def list_internal_unsubscribes(
    since_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    internal_auth: None = Depends(verify_tracking_internal_secret),
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for local application to synchronize remote unsubscribe events."""
    from app.modules.emails.models import EmailTrackingEvent
    stmt = (
        select(EmailTrackingEvent)
        .options(selectinload(EmailTrackingEvent.token))
        .where(
            EmailTrackingEvent.event_type == TrackingEventType.UNSUBSCRIBE.value,
            EmailTrackingEvent.id > since_id,
        )
        .order_by(EmailTrackingEvent.id.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "event_id": e.id,
            "token_id": e.token_id,
            "company_id": e.company_id,
            "campaign_id": e.campaign_id,
            "recipient_id": e.recipient_id,
            "delivery_id": e.delivery_id,
            "email": (
                e.token.destination_url.replace("email:", "")
                if e.token and e.token.destination_url and e.token.destination_url.startswith("email:")
                else None
            ),
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
        }
        for e in events
    ]



def get_trusted_proxy_networks() -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """Parse configured trusted proxy networks from application settings.
    
    Security Rules:
    - If TRUSTED_PROXIES is configured, it defines the explicit trust boundary.
    - In local development/testing (APP_ENV != 'production'), loopback (127.0.0.1/32, ::1/128)
      is trusted by default to support local testing, unless TRUSTED_PROXIES is explicitly set empty.
    - In production (APP_ENV == 'production'), trusted proxies is empty by default unless explicitly configured.
    """
    raw = getattr(settings, "TRUSTED_PROXIES", None)
    if raw is not None:
        if not raw.strip():
            return []
        items = raw.split(",")
    else:
        is_prod = (getattr(settings, "APP_ENV", "") or "").strip().lower() in ("production", "prod")
        if is_prod:
            return []
        items = ["127.0.0.1", "::1"]

    networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for item in items:
        clean = item.strip()
        if not clean:
            continue
        try:
            if "/" in clean:
                networks.append(ipaddress.ip_network(clean, strict=False))
            else:
                networks.append(ipaddress.ip_network(f"{clean}/32" if ":" not in clean else f"{clean}/128", strict=False))
        except ValueError:
            logger.warning("Invalid trusted proxy IP/network '%s' ignored", clean)
    return networks


def extract_client_ip(request: Request) -> Optional[str]:
    """Extract client IP address strictly respecting the trusted proxy boundary.
    
    Security & Privacy Rules:
    - Never trust arbitrary X-Forwarded-For or CF-Connecting-IP headers from the public internet.
    - If trusted proxy configuration is not established (no TRUSTED_PROXIES configured or
      immediate peer request.client.host is not within a trusted proxy network),
      forwarding headers are considered untrusted/spoofable.
    - When untrusted, returns None (stores NULL in the database) to prevent spoofed IP injection.
    - When the immediate peer IS an established trusted proxy:
      1. Inspects CF-Connecting-IP (if configured behind Cloudflare) and validates it is a valid IP.
      2. Or inspects the rightmost untrusted IP in X-Forwarded-For (walking back past internal/private proxy hops).
      3. Validates and returns normalized IP string (max 45 chars).
    - If no forwarding headers are provided by the trusted proxy, returns None.
    """
    trusted_networks = get_trusted_proxy_networks()
    if not trusted_networks:
        return None

    client_host = request.client.host if request.client else None
    if not client_host:
        return None

    try:
        peer_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return None

    is_trusted_peer = any(peer_ip in net for net in trusted_networks)
    if not is_trusted_peer:
        return None

    # Immediate peer IS trusted; check headers passed by the trusted proxy
    cf_connecting = request.headers.get("cf-connecting-ip")
    if cf_connecting:
        clean_cf = cf_connecting.strip()
        try:
            ipaddress.ip_address(clean_cf)
            return clean_cf[:45]
        except ValueError:
            pass

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        for candidate in reversed(parts):
            try:
                c_ip = ipaddress.ip_address(candidate)
                if any(c_ip in net for net in trusted_networks) or c_ip.is_private:
                    continue
                return str(c_ip)[:45]
            except ValueError:
                continue
        if parts:
            try:
                ipaddress.ip_address(parts[0])
                return parts[0][:45]
            except ValueError:
                pass

    return None


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

    client_ip = extract_client_ip(request)
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


# RFC-compliant 43-byte transparent 1x1 GIF89a pixel
TRANSPARENT_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
    b"\x00\x00\x02\x02D\x01\x00;"
)


@public_tracking_router.get(
    "/t/o/{token}",
    summary="Track email open via transparent 1x1 pixel",
)
async def track_open_pixel(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public open tracking pixel endpoint.
    
    Validates token from server-side database, records unclassified open event,
    and returns a transparent 1x1 GIF with strict no-cache headers.
    
    Security & Reliability Rules:
    - Token validated strictly against stored SHA-256 hash; revoked, expired,
      invalid, or non-OPEN tokens return HTTP 404.
    - Records an OPEN event with is_bot = None (unclassified raw open).
    - Fails closed: if the event cannot be recorded/committed, returns HTTP 500 without returning image.
    - Emits strict no-cache headers to prevent proxy or client caching.
    - Never redirects.
    - Does not expose database errors or token details.
    """
    token_record = await EmailTrackingService.resolve_and_validate_token(
        db=db,
        raw_token=token,
        expected_type=TrackingTokenType.OPEN,
    )
    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracking pixel is invalid, expired, or has been disabled",
        )

    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent")
    token_id = token_record.id

    try:
        await EmailTrackingService.record_tracking_event(
            db=db,
            token=token_record,
            event_type=TrackingEventType.OPEN,
            ip_address=client_ip,
            user_agent=user_agent,
            is_bot=None,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Failed to record open event for token id=%d: %s",
            token_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record tracking event",
        )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return Response(
        content=TRANSPARENT_PIXEL_GIF,
        media_type="image/gif",
        status_code=status.HTTP_200_OK,
        headers=headers,
    )


@public_tracking_router.get(
    "/t/u/{token}",
    summary="Public confirmation page for email unsubscription",
)
@public_tracking_router.get(
    "/t/u/{token}/",
    include_in_schema=False,
)
async def track_unsubscribe_get(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public GET endpoint for opaque tracking unsubscribe URLs."""
    from app.modules.campaigns.unsubscribe_service import UnsubscribeService
    return await UnsubscribeService.handle_get(token=token, request=request, db=db)


@public_tracking_router.post(
    "/t/u/{token}",
    summary="Public RFC 8058 one-click unsubscribe endpoint",
)
@public_tracking_router.post(
    "/t/u/{token}/",
    include_in_schema=False,
)
async def track_unsubscribe_post(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public RFC 8058 One-Click POST endpoint for opaque tracking unsubscribe URLs."""
    from app.modules.campaigns.unsubscribe_service import UnsubscribeService
    return await UnsubscribeService.handle_post(token=token, request=request, db=db)


