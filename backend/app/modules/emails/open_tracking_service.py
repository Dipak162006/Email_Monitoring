import logging
import re
from typing import Optional

from app.modules.emails.models import TrackingTokenType
from app.modules.emails.tracking_client import TrackingServiceClient

logger = logging.getLogger(__name__)

# Pattern to detect existing open tracking pixel in HTML
EXISTING_PIXEL_PATTERN = re.compile(
    r'(<img\b[^>]*?\b(?:data-pulsemail-open-pixel\b|src\s*=\s*["\'][^"\']*/t/o/[^"\']+["\'])[^>]*?>)',
    re.IGNORECASE,
)

# Pattern to locate closing </body> tag
BODY_CLOSE_PATTERN = re.compile(r'</body\s*>', re.IGNORECASE)


class OpenTrackingService:
    """Service for injecting transparent 1x1 open tracking pixels into campaign emails.
    
    Used exclusively in campaign email dispatch pipelines.
    Guarantees:
    - Campaign emails only (never mailbox or inbound emails).
    - Prevents duplicate pixel injection if HTML already contains a tracking pixel.
    - Preserves existing click tracking links, attachments, and HTML styling.
    - Injects pixel before </body> if present, or appends to the end of the HTML.
    - Fails open: If tracking service is unconfigured, times out, or fails,
      the original HTML is left completely intact so email dispatch is never halted.
    - Idempotent: Uses deterministic idempotency keys per campaign delivery.
    """

    @staticmethod
    def build_pixel_tag(tracking_url: str) -> str:
        """Construct a lightweight, standards-compliant 1x1 transparent tracking pixel image tag."""
        return (
            f'<img src="{tracking_url}" width="1" height="1" border="0" alt="" '
            f'data-pulsemail-open-pixel="true" '
            f'style="display:none !important; min-height:1px !important; width:1px !important; '
            f'border:0 !important; margin:0 !important; padding:0 !important" />'
        )

    @classmethod
    def has_open_pixel(cls, html_content: Optional[str]) -> bool:
        """Check if the HTML content already contains an open tracking pixel."""
        if not html_content or not isinstance(html_content, str):
            return False
        return bool(EXISTING_PIXEL_PATTERN.search(html_content))

    @classmethod
    def inject_pixel_html(cls, html_content: str, tracking_url: str) -> str:
        """Inject the pixel tag into HTML, placing it before </body> if present, or appending to the end."""
        pixel_tag = cls.build_pixel_tag(tracking_url)
        match = BODY_CLOSE_PATTERN.search(html_content)
        if match:
            pos = match.start()
            return html_content[:pos] + pixel_tag + html_content[pos:]
        return html_content + pixel_tag

    @classmethod
    async def inject_campaign_open_pixel(
        cls,
        html_content: Optional[str],
        company_id: int,
        campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        delivery_id: Optional[int] = None,
        email_id: Optional[int] = None,
        tracking_client: Optional[TrackingServiceClient] = None,
    ) -> Optional[str]:
        """Inject a 1x1 transparent open tracking pixel into campaign email HTML.
        
        Fail-open: Returns the original HTML if tracking is unconfigured, disabled,
        times out, or encounters errors.
        """
        if not html_content or not isinstance(html_content, str):
            return html_content

        # Prevent duplicate pixel injection
        if cls.has_open_pixel(html_content):
            logger.debug("Open tracking pixel already present in HTML; skipping injection")
            return html_content

        client = tracking_client or TrackingServiceClient()
        if not client.is_configured:
            logger.debug("TrackingServiceClient not configured; skipping open pixel injection")
            return html_content

        effective_email_id = email_id or delivery_id or 0
        idempotency_key = f"c{campaign_id or 0}_d{delivery_id or 0}_open"

        try:
            issue_resp = await client.issue_token(
                company_id=company_id,
                email_id=effective_email_id,
                token_type=TrackingTokenType.OPEN,
                destination_url=None,
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                delivery_id=delivery_id,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            logger.warning(
                "Error requesting OPEN tracking token (fail-open): %s",
                exc,
            )
            issue_resp = None

        if issue_resp and issue_resp.tracking_url:
            return cls.inject_pixel_html(html_content, issue_resp.tracking_url)

        return html_content

