"""Public unauthenticated routes for campaigns and RFC 8058 one-click unsubscribe."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.core.database import get_db
from app.core.security import decode_unsubscribe_token
from app.modules.campaigns.models import (
    CampaignRecipient,
    CampaignRecipientStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import normalize_and_validate_email

public_router = APIRouter(prefix="/public", tags=["Public"])

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


async def _handle_unsubscribe(token: str, db: AsyncSession) -> dict:
    try:
        payload = decode_unsubscribe_token(token)
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

    company_id = payload["company_id"]
    email = payload["email"]
    campaign_id = payload.get("campaign_id")

    try:
        norm_email = normalize_and_validate_email(email)
    except Exception:
        norm_email = email.strip().lower()

    # 1. Idempotently add to company suppression list
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

    # 2. If campaign_id provided, mark any PENDING recipient as SUPPRESSED
    if campaign_id:
        recip_stmt = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.email == norm_email,
            CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
        )
        recip_res = await db.execute(recip_stmt)
        for r in recip_res.scalars().all():
            r.status = CampaignRecipientStatus.SUPPRESSED.value

    await db.commit()
    return {"status": "unsubscribed", "email": norm_email, "company_id": company_id}


@public_router.get(
    "/unsubscribe/{token}",
    summary="Public link to unsubscribe an email recipient",
)
@public_router.get(
    "/unsubscribe/{token}/",
    include_in_schema=False,
)
async def unsubscribe_get(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public GET endpoint for email recipients clicking an unsubscribe link in an email."""
    result = await _handle_unsubscribe(token, db)
    accept_header = request.headers.get("accept", "").lower()
    if "application/json" in accept_header and "text/html" not in accept_header:
        return JSONResponse(result, status_code=status.HTTP_200_OK)

    html = UNSUBSCRIBE_SUCCESS_HTML.replace("{email}", result["email"])
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK)


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
    db: AsyncSession = Depends(get_db),
):
    """RFC 8058 One-Click POST endpoint used by automated email clients (Gmail, Yahoo)."""
    result = await _handle_unsubscribe(token, db)
    return JSONResponse(result, status_code=status.HTTP_200_OK)
