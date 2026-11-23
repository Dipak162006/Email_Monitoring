"""T5.1 Conservative Bot and Scanner Classifier Tests.

Verifies:
1. Apple Mail Privacy Protection (MPP) / Apple Image Proxy detection.
2. Google Image Proxy detection.
3. Microsoft Defender / SafeLinks detection.
4. Enterprise security scanners (Proofpoint, Barracuda, Mimecast, etc.) detection.
5. Known automated crawlers, scripting HTTP clients, and headless browsers detection.
6. Normal interactive browsers (Chrome, Safari, Firefox, Edge) remaining unclassified (is_bot=None).
7. Unknown, unfamiliar, or blank user agents remaining unclassified (is_bot=None).
8. Timing signals alone NEVER forcing bot classification on standard/unknown browsers.
9. Unsubscribe requests excluded from engagement classification.
"""
from datetime import datetime, timedelta, timezone
import pytest

from app.modules.emails.bot_classifier import BotClassifier, BotClassificationResult
from app.modules.emails.models import EmailTrackingToken, TrackingEventType, TrackingTokenType


def test_apple_mpp_classification():
    """Verify Apple Mail Privacy Protection and Apple Image Proxy UA tokens are classified as bot."""
    apple_uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) AppleImageProxy/1.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 AppleImageProxy/1.0",
        "AppleImageProxy/1.0 CFNetwork/1331.0.7 Darwin/21.4.0",
    ]
    for ua in apple_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.OPEN)
        assert res.is_bot is True, f"Failed for UA: {ua}"
        assert res.bot_reason == "apple_mpp"
        assert res.bot_confidence == 0.95


def test_ordinary_apple_mail_client_not_classified_as_bot():
    """Verify ordinary Apple Mail without AppleImageProxy proxy header is NOT classified as bot."""
    ordinary_apple_uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 AppleMail/3608",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "AppleMail/3608.120.23.2.4",
    ]
    for ua in ordinary_apple_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.OPEN)
        assert res.is_bot is None, f"Ordinary Apple Mail must remain is_bot=None: {ua}"
        assert res.bot_reason is None
        assert res.bot_confidence is None



def test_google_image_proxy_classification():
    """Verify Gmail / Google Image Proxy UA tokens are classified as bot."""
    google_uas = [
        "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
        "GoogleImageProxy",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 (via ggpht.com)",
    ]
    for ua in google_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.OPEN)
        assert res.is_bot is True, f"Failed for UA: {ua}"
        assert res.bot_reason == "google_image_proxy"
        assert res.bot_confidence == 0.95


def test_microsoft_safelinks_classification():
    """Verify Microsoft SafeLinks / ATP scanner tokens are classified as bot."""
    safelinks_uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36 SafeLinks/1.0",
        "Mozilla/5.0 (compatible; BingPreview/1.0b; +http://www.bing.com/bingpreview.htm)",
        "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; MS Search 6.0; rv:11.0) like Gecko",
    ]
    for ua in safelinks_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.CLICK)
        assert res.is_bot is True, f"Failed for UA: {ua}"
        assert res.bot_reason == "microsoft_safelinks"
        assert res.bot_confidence >= 0.90


def test_security_scanners_classification():
    """Verify enterprise mail gateway scanners are classified as bot."""
    scanner_uas = [
        "Proofpoint-URL-Defense/1.0 (https://www.proofpoint.com)",
        "Mozilla/5.0 (compatible; Barracuda-Security-Scanner/1.0)",
        "Mimecast-Inbound-Filter/2.0",
        "FireEye-Security-Engine/1.0",
        "Sophos-AntiVirus-Scanner",
        "Zscaler-Cloud-Browser",
        "MessageLabs-AntiSpam/3.0",
        "Trend Micro Deep Security Crawler",
        "Forcepoint-Web-Security",
        "Cisco IronPort Email Security Gateway",
    ]
    for ua in scanner_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.CLICK)
        assert res.is_bot is True, f"Failed for UA: {ua}"
        assert res.bot_reason == "security_scanner"
        assert res.bot_confidence == 0.95


def test_automated_crawlers_and_headless_browsers_classification():
    """Verify script tools, HTTP clients, and headless browsers are classified as bot."""
    crawler_uas = [
        "curl/7.88.1",
        "python-requests/2.31.0",
        "aiohttp/3.8.5",
        "httpx/0.24.1",
        "Go-http-client/1.1",
        "Wget/1.21.3",
        "PostmanRuntime/7.32.3",
        "HTTPie/3.2.1",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/114.0.5735.198 Safari/537.36",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
        "facebookexternalhit/1.1",
        "Twitterbot/1.0",
        "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    ]
    for ua in crawler_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.CLICK)
        assert res.is_bot is True, f"Failed for UA: {ua}"
        assert res.bot_reason == "automated_crawler"
        assert res.bot_confidence == 0.95


def test_standard_browsers_remain_unclassified():
    """Verify normal interactive human browser user agents remain unclassified (is_bot=None)."""
    browser_uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    for ua in browser_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.OPEN)
        assert res.is_bot is None, f"Expected None for browser UA: {ua}"
        assert res.bot_reason is None
        assert res.bot_confidence is None


def test_unknown_or_blank_user_agents_remain_unclassified():
    """Verify missing, empty, or unrecognized user agents remain unclassified (is_bot=None).
    The system never automatically assumes an unfamiliar client is human.
    """
    unfamiliar_uas = [
        None,
        "",
        "   ",
        "MyCompanyInternalCustomApp/3.1",
        "CorporateMailHub/2.0",
        "Thunderbird/115.3.1",
        "Roundcube/1.6.0",
    ]
    for ua in unfamiliar_uas:
        res = BotClassifier.classify(user_agent=ua, event_type=TrackingEventType.CLICK)
        assert res.is_bot is None, f"Expected None for unfamiliar UA: {ua}"
        assert res.bot_reason is None
        assert res.bot_confidence is None


def test_timing_signal_does_not_independently_force_bot_classification():
    """Verify that very fast request timing (<1s) on a normal browser does NOT set is_bot=True."""
    now = datetime.now(timezone.utc)
    token = EmailTrackingToken(
        id=1,
        company_id=10,
        email_id=20,
        token_hash="a" * 64,
        token_type=TrackingTokenType.OPEN.value,
        created_at=now - timedelta(milliseconds=200),  # Arrived 200ms after creation
    )

    # Standard browser arriving 200ms after send
    normal_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    res = BotClassifier.classify(
        user_agent=normal_ua,
        event_type=TrackingEventType.OPEN,
        token=token,
        occurred_at=now,
    )
    # Timing alone MUST NOT classify as bot
    assert res.is_bot is None
    assert res.bot_reason is None

    # However, for an affirmative scanner UA (e.g. SafeLinks), immediate timing elevates confidence
    safelinks_ua = "Mozilla/5.0 SafeLinks/1.0"
    res_safelinks = BotClassifier.classify(
        user_agent=safelinks_ua,
        event_type=TrackingEventType.CLICK,
        token=token,
        occurred_at=now,
    )
    assert res_safelinks.is_bot is True
    assert res_safelinks.bot_reason == "microsoft_safelinks"
    assert res_safelinks.bot_confidence == 0.95


def test_unsubscribe_events_excluded_from_engagement_classification():
    """Verify that UNSUBSCRIBE events are explicitly not classified as engagement."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SafeLinks/1.0"
    res = BotClassifier.classify(
        user_agent=ua,
        event_type=TrackingEventType.UNSUBSCRIBE,
    )
    assert res.is_bot is None
    assert res.bot_reason is None
    assert res.bot_confidence is None
