"""Public unauthenticated routes for campaigns and RFC 8058 one-click unsubscribe."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.campaigns.unsubscribe_service import (
    UNSUBSCRIBE_CONFIRMATION_HTML,
    UNSUBSCRIBE_SUCCESS_HTML,
    UnsubscribeService,
)

public_router = APIRouter(prefix="/public", tags=["Public"])


@public_router.get(
    "/unsubscribe/{token}",
    summary="Public confirmation page for email unsubscription",
)
@public_router.get(
    "/unsubscribe/{token}/",
    include_in_schema=False,
)
async def unsubscribe_get(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public GET endpoint: Displays a confirmation page. Does NOT unsubscribe the user.
    
    Safe against automated email scanners, security prefetchers, and preview crawlers.
    """
    return await UnsubscribeService.handle_get(token=token, request=request, db=db)


@public_router.post(
    "/unsubscribe/{token}",
    summary="RFC 8058 One-Click Unsubscribe Endpoint",
)
@public_router.post(
    "/unsubscribe/{token}/",
    include_in_schema=False,
)
async def unsubscribe_post(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """RFC 8058 One-Click POST endpoint used by automated email clients (Gmail, Yahoo)
    and user confirmation form submissions to execute unsubscription idempotently.
    """
    return await UnsubscribeService.handle_post(token=token, request=request, db=db)

