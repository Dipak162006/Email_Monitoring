"""Conservative Bot and Automated Traffic Classifier for Email Engagement Telemetry.

Provides heuristic classification of interaction telemetry (OPEN pixels and CLICK redirects)
to distinguish automated scanning, proxy pre-fetching, and machine crawlers from potential
human engagement.

Heuristic Limitations & Architectural Principles:
1. Heuristic Detection Boundaries:
   - User-Agent and timing heuristics are probabilistic, not infallible guarantees.
   - Sophisticated headless browsers or scrapers configured with full browser headers
     cannot be reliably identified via header inspection alone.
   - Conversely, aggressive security gateways occasionally simulate full human behavior.
2. Conservative Classification Philosophy:
   - False Positives (misclassifying human leads as bots) are considered catastrophic
     for outbound sales outreach and campaign conversion reporting.
   - Traffic is ONLY classified as `is_bot = True` when affirmative evidence is present
     (e.g., vendor-specific crawler tokens, mail gateway scanners, or headless runners).
   - Ambiguous, unfamiliar, or standard browser user-agents MUST remain `is_bot = None`
     (unclassified/uncertain). The system NEVER assumes traffic is definitively human (`is_bot = False`).
3. Timing Signal Discipline:
   - Millisecond-level interaction relative to email delivery is a corroborating signal,
     never an independent trigger on its own.
4. Provider Independence:
   - Logic is 100% provider-agnostic, operating purely on RFC-compliant HTTP headers,
     token timestamps, and standard network attributes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Optional, Union

from app.modules.emails.models import EmailTrackingToken, TrackingEventType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotClassificationResult:
    """Outcome of conservative interaction classification.
    
    Attributes:
        is_bot: True if affirmative automated-traffic evidence exists;
                None if unclassified/uncertain (never automatically False).
        bot_reason: Classification category code if is_bot is True; None otherwise.
        bot_confidence: Float in [0.0, 1.0] indicating heuristic confidence; None otherwise.
    """
    is_bot: Optional[bool]
    bot_reason: Optional[str]
    bot_confidence: Optional[float]


class BotClassifier:
    """Heuristic classifier for email engagement telemetry (OPEN and CLICK)."""

    # 1. Apple Mail Privacy Protection (MPP) & Apple Image Proxy
    # Apple MPP routes remote image loading through proxy infrastructure.
    # UA token specifically contains "AppleImageProxy".
    # Generic "AppleMail" or standard Apple browser tokens are deliberately excluded
    # to avoid misclassifying ordinary human Apple Mail client opens.
    _APPLE_MPP_PATTERN = re.compile(
        r"AppleImageProxy",
        re.IGNORECASE,
    )

    # 2. Google Image Proxy
    # Gmail web and mobile clients load email images through Google's caching proxy.
    # Standard UA contains "GoogleImageProxy" or "via ggpht.com".
    _GOOGLE_PROXY_PATTERN = re.compile(
        r"(?:GoogleImageProxy|via\s+ggpht\.com)",
        re.IGNORECASE,
    )

    # 3. Microsoft Defender / SafeLinks / ATP
    # Microsoft SafeLinks inspects and pre-fetches incoming email links.
    # Common signatures include "SafeLinks", "BingPreview", "MS Search", or "Microsoft-CryptoAPI".
    _MICROSOFT_SAFELINKS_PATTERN = re.compile(
        r"(?:SafeLinks|BingPreview|MS\s+Search|Microsoft-CryptoAPI)",
        re.IGNORECASE,
    )

    # 4. Enterprise Security Crawlers & Email Gateway Scanners
    # Vendors inspecting links for malware, phishing, and sandboxing:
    # Proofpoint, Barracuda, Mimecast, FireEye, Sophos, Zscaler, Trend Micro, Forcepoint, Cisco IronPort, Symantec
    _SECURITY_SCANNER_PATTERN = re.compile(
        r"(?:Proofpoint|Barracuda|Mimecast|FireEye|Sophos|Zscaler|MessageLabs|Trend\s*Micro|Forcepoint|IronPort|Symantec)",
        re.IGNORECASE,
    )

    # 5. Automated Crawlers, Scripting HTTP Clients & Headless Browsers
    # Command-line tools, automation frameworks, and search engine crawlers:
    # curl, python-requests, httpx, aiohttp, Wget, Go-http-client, HeadlessChrome, Puppeteer, Playwright, etc.
    _AUTOMATED_CRAWLER_PATTERN = re.compile(
        r"(?:curl/|python-requests|aiohttp|httpx|Go-http-client|Wget/|PostmanRuntime|HTTPie|libwww-perl|Apache-HttpClient|node-fetch|axios|HeadlessChrome|PhantomJS|Playwright|Puppeteer|Selenium|WebDriver|Googlebot|bingbot|Baiduspider|YandexBot|DuckDuckBot|Twitterbot|facebookexternalhit|LinkedInBot|Slackbot)",
        re.IGNORECASE,
    )

    @classmethod
    def classify(
        cls,
        user_agent: Optional[str],
        event_type: Union[TrackingEventType, str],
        token: Optional[EmailTrackingToken] = None,
        ip_address: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> BotClassificationResult:
        """Evaluate interaction metadata against conservative bot/scanner rules.
        
        Rules:
        - UNSUBSCRIBE requests are unsubscription actions and are never classified as engagement.
        - Missing or blank user-agents are treated as uncertain (is_bot=None).
        - Specific affirmative patterns set is_bot=True with corresponding reason and confidence.
        - Standard browser or unrecognized user-agents remain is_bot=None.
        - Timing relative to token creation is evaluated as a corroborating signal only.
        """
        type_str = event_type.value if hasattr(event_type, "value") else str(event_type).strip().upper()

        # Unsubscribe events are explicitly not engagement events
        if type_str == TrackingEventType.UNSUBSCRIBE.value:
            return BotClassificationResult(is_bot=None, bot_reason=None, bot_confidence=None)

        if not user_agent or not isinstance(user_agent, str):
            # Missing user agent is ambiguous; remain unclassified
            return BotClassificationResult(is_bot=None, bot_reason=None, bot_confidence=None)

        ua = user_agent.strip()
        if not ua:
            return BotClassificationResult(is_bot=None, bot_reason=None, bot_confidence=None)

        # 1. Apple Mail Privacy Protection (MPP)
        if cls._APPLE_MPP_PATTERN.search(ua):
            return BotClassificationResult(
                is_bot=True,
                bot_reason="apple_mpp",
                bot_confidence=0.95,
            )

        # 2. Google Image Proxy
        if cls._GOOGLE_PROXY_PATTERN.search(ua):
            return BotClassificationResult(
                is_bot=True,
                bot_reason="google_image_proxy",
                bot_confidence=0.95,
            )

        # 3. Microsoft SafeLinks / Defender
        if cls._MICROSOFT_SAFELINKS_PATTERN.search(ua):
            # If timing is available and immediate (<5s), elevate confidence
            confidence = 0.90
            if token and token.created_at:
                now_dt = occurred_at or datetime.now(timezone.utc)
                token_created = token.created_at
                if token_created.tzinfo is None:
                    token_created = token_created.replace(tzinfo=timezone.utc)
                delta_sec = (now_dt - token_created).total_seconds()
                if 0 <= delta_sec < 5.0:
                    confidence = 0.95

            return BotClassificationResult(
                is_bot=True,
                bot_reason="microsoft_safelinks",
                bot_confidence=confidence,
            )

        # 4. Security Gateway Scanners
        if cls._SECURITY_SCANNER_PATTERN.search(ua):
            return BotClassificationResult(
                is_bot=True,
                bot_reason="security_scanner",
                bot_confidence=0.95,
            )

        # 5. Automated Crawlers & Scripting Clients
        if cls._AUTOMATED_CRAWLER_PATTERN.search(ua):
            return BotClassificationResult(
                is_bot=True,
                bot_reason="automated_crawler",
                bot_confidence=0.95,
            )

        # Standard browsers, unrecognized mail clients, or ambiguous UAs remain unclassified
        return BotClassificationResult(is_bot=None, bot_reason=None, bot_confidence=None)
