from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrackingTokenIssueRequest(BaseModel):
    """Payload for server-to-server tracking token issuance request."""
    model_config = ConfigDict(extra="forbid")

    company_id: int = Field(..., description="Multi-tenant company identifier")
    email_id: int = Field(..., description="Outbound email record identifier")
    token_type: str = Field(..., description="Purpose: CLICK, OPEN, or UNSUBSCRIBE")
    destination_url: Optional[str] = Field(None, description="Required target redirect destination for CLICK tokens")
    campaign_id: Optional[int] = Field(None, description="Optional associated campaign ID")
    recipient_id: Optional[int] = Field(None, description="Optional associated campaign recipient ID")
    delivery_id: Optional[int] = Field(None, description="Optional associated campaign delivery ID")
    expires_in_seconds: Optional[int] = Field(None, ge=1, le=31536000, description="Optional token validity in seconds")
    idempotency_key: Optional[str] = Field(None, max_length=64, description="Optional caller idempotency key to prevent duplicates")

    @field_validator("token_type")
    @classmethod
    def validate_token_type(cls, v: str) -> str:
        clean = (v or "").strip().upper()
        if clean not in {"CLICK", "OPEN", "UNSUBSCRIBE"}:
            raise ValueError(f"Invalid token_type '{v}'. Must be one of: CLICK, OPEN, UNSUBSCRIBE")
        return clean

    @field_validator("destination_url")
    @classmethod
    def validate_destination_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            parsed = urlparse(clean)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                raise ValueError("destination_url must be a valid absolute HTTP or HTTPS URL")
            return clean
        return None


class TrackingTokenIssueResponse(BaseModel):
    """Response containing issued tracking token and ready-to-use tracking URL."""
    model_config = ConfigDict(from_attributes=True)

    token_id: int
    raw_token: str
    token_type: str
    tracking_url: str
    destination_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

