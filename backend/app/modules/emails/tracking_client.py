import logging
from typing import Optional, Union
import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.modules.emails.models import TrackingTokenType
from app.modules.emails.tracking_schemas import (
    TrackingTokenIssueRequest,
    TrackingTokenIssueResponse,
)

logger = logging.getLogger(__name__)


class TrackingServiceClient:
    """Client for local backend to issue tracking tokens via the remote tracking backend.
    
    Provides fault-tolerant HTTP communication, short timeouts, safe error handling,
    and idempotency support so email sending is never blocked or failed if tracking
    is disabled or unavailable.
    """

    def __init__(
        self,
        service_url: Optional[str] = None,
        internal_secret: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self._service_url = (service_url or settings.get_tracking_service_url() or "").rstrip("/")
        self._internal_secret = internal_secret or settings.TRACKING_INTERNAL_SECRET
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.TRACKING_CLIENT_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        """Return True if both service URL and internal secret are configured."""
        return bool(self._service_url and self._internal_secret)

    async def issue_token(
        self,
        company_id: int,
        email_id: int,
        token_type: Union[TrackingTokenType, str],
        destination_url: Optional[str] = None,
        campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        delivery_id: Optional[int] = None,
        expires_in_seconds: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[TrackingTokenIssueResponse]:
        """Request tracking token issuance from the remote tracking backend.
        
        Returns TrackingTokenIssueResponse on success.
        On timeout, network failure, or non-201 response, returns None (fail-open)
        without raising exceptions, ensuring normal email dispatch is never halted.
        Never logs internal secrets or raw tokens.
        """
        if not self.is_configured:
            logger.debug("Tracking service client not fully configured; skipping remote token issuance")
            return None

        type_str = token_type.value if hasattr(token_type, "value") else str(token_type).strip().upper()

        try:
            req_payload = TrackingTokenIssueRequest(
                company_id=company_id,
                email_id=email_id,
                token_type=type_str,
                destination_url=destination_url,
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                delivery_id=delivery_id,
                expires_in_seconds=expires_in_seconds,
                idempotency_key=idempotency_key,
            )
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid tracking token request parameters: %s", exc)
            return None

        url = f"{self._service_url}/api/v1/internal/tracking/tokens"
        headers = {
            "Content-Type": "application/json",
            "X-Tracking-Internal-Secret": self._internal_secret,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    url,
                    json=req_payload.model_dump(exclude_none=True),
                    headers=headers,
                )

            if response.status_code == 201:
                data = response.json()
                return TrackingTokenIssueResponse.model_validate(data)
            else:
                logger.warning(
                    "Tracking service returned non-201 status: %d (endpoint=%s)",
                    response.status_code,
                    url,
                )
                return None

        except httpx.TimeoutException:
            logger.warning(
                "Tracking service timed out after %.2f seconds (endpoint=%s)",
                self._timeout_seconds,
                url,
            )
            return None
        except httpx.ConnectError:
            logger.warning("Failed to connect to tracking service at %s", self._service_url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("HTTP error communicating with tracking service: %s", exc.__class__.__name__)
            return None
        except Exception as exc:
            logger.warning("Unexpected error communicating with tracking service: %s", exc.__class__.__name__)
            return None

