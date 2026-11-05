import logging
import re
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.modules.emails.models import TrackingTokenType
from app.modules.emails.tracking_client import TrackingServiceClient

logger = logging.getLogger(__name__)

# Pattern to locate <a ... href="..." ...> tags while preserving all attributes
A_TAG_PATTERN = re.compile(
    r'(<a\b(?P<attrs1>[^>]*?)\bhref\s*=\s*(?:(?P<quote>["\'])(?P<href>.*?)(?P=quote)|(?P<href_noq>[^\s>]+))(?P<attrs2>[^>]*?>))',
    re.IGNORECASE | re.DOTALL,
)

# Schemes and targets that should never be rewritten for click tracking
BLOCKED_SCHEMES = (
    "mailto:",
    "tel:",
    "sms:",
    "javascript:",
    "data:",
    "cid:",
    "file:",
    "ftp:",
)


class LinkTrackingService:
    """Service for rewriting HTML hyperlinks with secure tracking redirect URLs.
    
    Used exclusively in campaign email dispatch pipelines.
    Guarantees:
    - Never rewrites non-HTTP URLs (mailto, tel, javascript, cid, anchor fragments).
    - Never rewrites unsubscribe URLs or un-rendered template variables.
    - Preserves all HTML anchor tag attributes (class, style, target, id, data-*).
    - Fails open: If tracking client is unconfigured, times out, or fails,
      the original URL is left completely intact so email dispatch is never halted.
    - Generates distinct deterministic idempotency keys per link instance.
    """

    @staticmethod
    def is_eligible_url(url: Optional[str], tracking_base_url: Optional[str] = None) -> bool:
        """Determine if a URL is eligible for click tracking rewrite."""
        if not url or not isinstance(url, str):
            return False

        trimmed = url.strip()
        if not trimmed:
            return False

        # Exclude un-rendered template variables / Jinja placeholders
        if "{{" in trimmed or "{%" in trimmed or "}}" in trimmed or "%}" in trimmed:
            return False

        # Exclude anchor/fragment jumps
        if trimmed.startswith("#"):
            return False

        lower = trimmed.lower()

        # Exclude non-web schemes
        if any(lower.startswith(scheme) for scheme in BLOCKED_SCHEMES):
            return False

        # Parse scheme and netloc
        try:
            parsed = urlparse(trimmed)
        except Exception:
            return False

        if parsed.scheme.lower() not in ("http", "https"):
            return False

        if not parsed.netloc:
            return False

        # Exclude unsubscribe URLs (RFC 8058 / RFC 2369 compliance)
        if "unsubscribe" in lower:
            return False

        # Exclude already rewritten tracking URLs
        if "/t/c/" in lower or "/t/o/" in lower or "/t/u/" in lower:
            return False

        if tracking_base_url:
            clean_base = tracking_base_url.rstrip("/").lower()
            if clean_base and lower.startswith(clean_base):
                return False

        return True

    @classmethod
    async def rewrite_campaign_html(
        cls,
        html_content: Optional[str],
        company_id: int,
        campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        delivery_id: Optional[int] = None,
        email_id: Optional[int] = None,
        tracking_client: Optional[TrackingServiceClient] = None,
    ) -> Optional[str]:
        """Rewrite eligible hyperlinks in campaign email HTML with tracked URLs.
        
        Fail-open: Returns the original HTML if tracking is unconfigured, disabled,
        or encounters errors.
        """
        if not html_content or not isinstance(html_content, str):
            return html_content

        client = tracking_client or TrackingServiceClient()
        if not client.is_configured:
            logger.debug("TrackingServiceClient not configured; skipping HTML link rewriting")
            return html_content

        tracking_base_url = settings.get_tracking_base_url()
        effective_email_id = email_id or delivery_id or 0

        matches = list(A_TAG_PATTERN.finditer(html_content))
        if not matches:
            return html_content

        new_pieces = []
        last_end = 0
        link_idx = 0

        for match in matches:
            full_tag = match.group(0)
            raw_href = match.group("href") or match.group("href_noq")
            attrs1 = match.group("attrs1")
            attrs2 = match.group("attrs2")
            quote = match.group("quote") or '"'

            start, end = match.span()
            new_pieces.append(html_content[last_end:start])
            last_end = end

            if not cls.is_eligible_url(raw_href, tracking_base_url=tracking_base_url):
                new_pieces.append(full_tag)
                continue

            # Deterministic idempotency key per link in delivery sequence
            idempotency_key = f"c{campaign_id or 0}_d{delivery_id or 0}_l{link_idx}"
            link_idx += 1

            try:
                issue_resp = await client.issue_token(
                    company_id=company_id,
                    email_id=effective_email_id,
                    token_type=TrackingTokenType.CLICK,
                    destination_url=raw_href,
                    campaign_id=campaign_id,
                    recipient_id=recipient_id,
                    delivery_id=delivery_id,
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                logger.warning(
                    "Error requesting tracking token for link %s (fail-open): %s",
                    raw_href,
                    exc,
                )
                issue_resp = None

            if issue_resp and issue_resp.tracking_url:
                rewritten_tag = f"<a{attrs1}href={quote}{issue_resp.tracking_url}{quote}{attrs2}"
                new_pieces.append(rewritten_tag)
            else:
                # Fail-open: retain original anchor tag
                new_pieces.append(full_tag)

        new_pieces.append(html_content[last_end:])
        return "".join(new_pieces)

