from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.services.imap.adapter import StandardIMAPAdapter
from app.services.imap.parser import EmailParser


# =============================================================================
# MIME Test Message Builders
# =============================================================================

def make_rfc3464_dsn_bounce(
    bounce_msg_id: str,
    orig_msg_id: str,
    recipient: str = "baduser@external.com",
    action: str = "failed",
    status_code: str = "5.1.1",
    diagnostic_code: str = "smtp; 550 5.1.1 User unknown",
    include_outer_in_reply_to: bool = True,
) -> bytes:
    """Build a compliant RFC 3464 multipart/report Delivery Status Notification."""
    boundary = "DSN_BOUNDARY_M13_TEST"
    in_reply_line = f"In-Reply-To: {orig_msg_id}\r\n" if include_outer_in_reply_to else ""

    raw = (
        f"From: MAILER-DAEMON@mail.server.com\r\n"
        f"To: sender@company.com\r\n"
        f"Subject: Delivery Status Notification (Failure)\r\n"
        f"Date: Wed, 16 Sep 2026 10:00:00 +0000\r\n"
        f"Message-ID: {bounce_msg_id}\r\n"
        f"{in_reply_line}"
        f"MIME-Version: 1.0\r\n"
        f'Content-Type: multipart/report; report-type=delivery-status; boundary="{boundary}"\r\n'
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Delivery failed for {recipient}: {diagnostic_code}\r\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: message/delivery-status\r\n"
        f"\r\n"
        f"Reporting-MTA: dns; mail.server.com\r\n"
        f"\r\n"
        f"Final-Recipient: rfc822; {recipient}\r\n"
        f"Action: {action}\r\n"
        f"Status: {status_code}\r\n"
        f"Diagnostic-Code: {diagnostic_code}\r\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: message/rfc822\r\n"
        f"\r\n"
        f"From: sender@company.com\r\n"
        f"To: {recipient}\r\n"
        f"Subject: Original Message\r\n"
        f"Message-ID: {orig_msg_id}\r\n"
        f"Date: Wed, 16 Sep 2026 09:30:00 +0000\r\n"
        f"\r\n"
        f"Original message body content.\r\n"
        f"--{boundary}--\r\n"
    )
    return raw.encode("utf-8")


def make_nonstandard_bounce(
    bounce_msg_id: str,
    orig_msg_id: str,
    recipient: str = "invalid@external.com",
) -> bytes:
    """Build a non-standard bounce using X-Failed-Recipients header."""
    raw = (
        f"From: postmaster@mail.server.com\r\n"
        f"To: sender@company.com\r\n"
        f"Subject: Undelivered Mail Returned to Sender\r\n"
        f"Date: Wed, 16 Sep 2026 10:00:00 +0000\r\n"
        f"Message-ID: {bounce_msg_id}\r\n"
        f"In-Reply-To: {orig_msg_id}\r\n"
        f"X-Failed-Recipients: {recipient}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Delivery to {recipient} failed permanently."
    )
    return raw.encode("utf-8")


def make_auto_reply(
    msg_id: str,
    orig_msg_id: str,
    subject: str = "Out of Office: Meeting",
    auto_submitted: str = "auto-replied",
) -> bytes:
    """Build an automated out-of-office reply with Auto-Submitted header."""
    raw = (
        f"From: recipient@external.com\r\n"
        f"To: sender@company.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Wed, 16 Sep 2026 10:15:00 +0000\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"In-Reply-To: {orig_msg_id}\r\n"
        f"References: {orig_msg_id}\r\n"
        f"Auto-Submitted: {auto_submitted}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"I am away from the office until next week with no email access."
    )
    return raw.encode("utf-8")


def make_genuine_reply(
    msg_id: str,
    orig_msg_id: str,
    subject: str = "Re: Hello",
    body: str = "Thank you, I received your email and will review it!",
) -> bytes:
    """Build a normal genuine customer reply."""
    raw = (
        f"From: recipient@external.com\r\n"
        f"To: sender@company.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Wed, 16 Sep 2026 10:20:00 +0000\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"In-Reply-To: {orig_msg_id}\r\n"
        f"References: {orig_msg_id}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}"
    )
    return raw.encode("utf-8")


# =============================================================================
# Helper setup fixtures
# =============================================================================

async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and login a test user, returning bearer token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str) -> int:
    """Create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email: str = "sender@company.com",
) -> int:
    """Create an email account configured for IMAP synchronization."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Support Inbox",
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.company.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "SmtpPassword123!",
            "imap_host": "imap.company.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "SecretPassword123!",
        },
    )
    return resp.json()["id"]


# =============================================================================
# M13 Test Cases
# =============================================================================

def test_01_rfc3464_dsn_bounce_detection():
    """1. Standard RFC 3464 DSN bounce detection parses structured fields."""
    raw = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-001@mail.server.com>",
        orig_msg_id="<orig-001@company.com>",
        recipient="user@fail.com",
        action="failed",
        status_code="5.1.1",
        diagnostic_code="smtp; 550 5.1.1 User unknown",
    )
    parsed = EmailParser.parse_raw_email(raw, imap_uid="101")
    assert parsed.is_bounce is True
    assert parsed.bounce_action == "failed"
    assert parsed.bounce_status == "5.1.1"
    assert "550 5.1.1 User unknown" in (parsed.bounce_diagnostic or "")
    assert "user@fail.com" in (parsed.bounce_recipient or "")
    assert parsed.bounce_original_message_id == "<orig-001@company.com>"
    assert parsed.is_auto_reply is False


def test_04_original_message_id_extracted_from_embedded_headers():
    """4. Original Message-ID is extracted from embedded headers even without outer In-Reply-To."""
    raw = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-no-inreply@mail.server.com>",
        orig_msg_id="<embedded-orig-002@company.com>",
        include_outer_in_reply_to=False,
    )
    parsed = EmailParser.parse_raw_email(raw)
    assert parsed.is_bounce is True
    assert parsed.in_reply_to is None
    assert parsed.bounce_original_message_id == "<embedded-orig-002@company.com>"


def test_05_supported_non_standard_bounce_handling():
    """5. Supported non-standard bounce (X-Failed-Recipients) is classified and parsed."""
    raw = make_nonstandard_bounce(
        bounce_msg_id="<bounce-nonstd@mail.server.com>",
        orig_msg_id="<orig-nonstd@company.com>",
        recipient="bounced@domain.com",
    )
    parsed = EmailParser.parse_raw_email(raw)
    assert parsed.is_bounce is True
    assert parsed.bounce_recipient == "bounced@domain.com"
    assert parsed.bounce_original_message_id == "<orig-nonstd@company.com>"


def test_06_sender_or_subject_alone_does_not_cause_unsafe_classification():
    """6. Sender or subject alone does not cause unsafe bounce classification."""
    msg = EmailMessage()
    msg["From"] = "mailer-daemon@example.com"
    msg["To"] = "sender@company.com"
    msg["Subject"] = "Delivery Status Notification (Failure) or general question"
    msg["Date"] = "Wed, 16 Sep 2026 10:00:00 +0000"
    msg["Message-ID"] = "<normal-email-123@example.com>"
    msg.set_content("Hello support, I have a question about failure handling.")

    parsed = EmailParser.parse_raw_email(msg.as_bytes())
    # Conservative detection: lacks multipart/report, message/delivery-status, and X-Failed-Recipients
    assert parsed.is_bounce is False


@pytest.mark.asyncio
async def test_02_and_03_original_outgoing_email_changes_to_bounced_and_stores_diagnostic(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """2 & 3. Original outgoing email changes from SENT to BOUNCED and stores diagnostic."""
    token = await register_and_login(async_client, "user_m13_02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-02")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Insert an existing outgoing email with status SENT
    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<orig-sent-001@company.com>",
        sender="sender@company.com",
        recipients=["baduser@external.com"],
        subject="Invoice #1001",
        body_text="Please find attached invoice.",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()
    await db_session.refresh(orig_email)

    # Sync an incoming RFC 3464 DSN bounce
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-rec-001@mail.server.com>",
        orig_msg_id="<orig-sent-001@company.com>",
        recipient="baduser@external.com",
        status_code="5.1.1",
        diagnostic_code="smtp; 550 User unknown",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1001", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["new_messages"] == 1

        # Verify original outgoing email transitioned to BOUNCED
        await db_session.refresh(orig_email)
        assert orig_email.status == EmailStatus.BOUNCED.value
        assert "5.1.1" in (orig_email.error_message or "")
        assert "User unknown" in (orig_email.error_message or "")


@pytest.mark.asyncio
async def test_07_and_08_unmatched_bounce_does_not_crash_and_does_not_update_unrelated_email(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """7 & 8. Unmatched bounce does not crash synchronization and does not update another email."""
    token = await register_and_login(async_client, "user_m13_07@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-07")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Unrelated outgoing email
    other_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<other-sent-999@company.com>",
        sender="sender@company.com",
        recipients=["valid@external.com"],
        subject="Newsletter",
        is_read=True,
    )
    db_session.add(other_email)
    await db_session.commit()

    # Bounce for a message that does not exist in the database
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-unmatched@mail.server.com>",
        orig_msg_id="<ghost-msg-not-found@company.com>",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1002", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["new_messages"] == 1

    # Verify other email is untouched
    await db_session.refresh(other_email)
    assert other_email.status == EmailStatus.SENT.value
    assert other_email.error_message is None


@pytest.mark.asyncio
async def test_09_account_isolation_bounce_cannot_update_another_account(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """9. Account A bounce cannot update an email belonging to Account B."""
    token = await register_and_login(async_client, "user_m13_09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-09")
    acc_a = await create_account_helper(async_client, token, comp_id, email="acc_a@company.com")
    acc_b = await create_account_helper(async_client, token, comp_id, email="acc_b@company.com")

    # Email sent by Account B
    email_b = Email(
        company_id=comp_id,
        email_account_id=acc_b,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<orig-b@company.com>",
        sender="acc_b@company.com",
        recipients=["customer@external.com"],
        subject="Account B Message",
        is_read=True,
    )
    db_session.add(email_b)
    await db_session.commit()

    # Bounce arrives in Account A syncing mailbox
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-in-a@mail.server.com>",
        orig_msg_id="<orig-b@company.com>",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1003", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_a}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Verify Account B's email was NOT updated
    await db_session.refresh(email_b)
    assert email_b.status == EmailStatus.SENT.value
    assert email_b.error_message is None


@pytest.mark.asyncio
async def test_10_company_isolation_bounce_cannot_update_another_company(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """10. Company A bounce cannot update an email belonging to Company B."""
    token_1 = await register_and_login(async_client, "user_m13_10_c1@test.com")
    comp_1 = await create_company_helper(async_client, token_1, "Co 1")
    acc_1 = await create_account_helper(async_client, token_1, comp_1, email="c1@company1.com")

    token_2 = await register_and_login(async_client, "user_m13_10_c2@test.com")
    comp_2 = await create_company_helper(async_client, token_2, "Co 2")
    acc_2 = await create_account_helper(async_client, token_2, comp_2, email="c2@company2.com")

    # Email sent by Company 2
    email_c2 = Email(
        company_id=comp_2,
        email_account_id=acc_2,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<shared-id@world.com>",
        sender="c2@company2.com",
        recipients=["customer@external.com"],
        subject="Company 2 Message",
        is_read=True,
    )
    db_session.add(email_c2)
    await db_session.commit()

    # Bounce arrives in Company 1 mailbox referencing the same message ID
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-c1@mail.server.com>",
        orig_msg_id="<shared-id@world.com>",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1004", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_1}/sync",
            headers={"Authorization": f"Bearer {token_1}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Verify Company 2's email remains SENT
    await db_session.refresh(email_c2)
    assert email_c2.status == EmailStatus.SENT.value
    assert email_c2.error_message is None


@pytest.mark.asyncio
async def test_11_only_outgoing_emails_can_be_updated_to_bounced(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """11. Only outgoing emails can be updated to BOUNCED; incoming emails are never touched."""
    token = await register_and_login(async_client, "user_m13_11@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-11")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # An incoming email with message ID <incoming-msg@external.com>
    incoming_msg = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        message_id="<incoming-msg@external.com>",
        sender="someone@external.com",
        recipients=["sender@company.com"],
        subject="Inquiry",
        is_read=False,
    )
    db_session.add(incoming_msg)
    await db_session.commit()

    # Bounce referencing the incoming message ID
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-targeting-incoming@mail.server.com>",
        orig_msg_id="<incoming-msg@external.com>",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1005", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Verify incoming email is still RECEIVED, not BOUNCED
    await db_session.refresh(incoming_msg)
    assert incoming_msg.status == EmailStatus.RECEIVED.value


@pytest.mark.asyncio
async def test_12_and_13_genuine_reply_sets_has_reply_and_appears_in_responses(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """12 & 13. Genuine customer reply sets thread.has_reply to True and appears in responses folder."""
    token = await register_and_login(async_client, "user_m13_12@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-12")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # 1. Create thread and outgoing email
    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Project Proposal",
        has_reply=False,
        message_count=1,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<orig-prop-001@company.com>",
        sender="sender@company.com",
        recipients=["client@external.com"],
        subject="Project Proposal",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    # 2. Sync genuine customer reply
    reply_bytes = make_genuine_reply(
        msg_id="<client-reply-001@external.com>",
        orig_msg_id="<orig-prop-001@company.com>",
        subject="Re: Project Proposal",
        body="Looks great! Let us proceed.",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("2001", reply_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Verify thread.has_reply became True
    await db_session.refresh(thread)
    assert thread.has_reply is True

    # Verify reply appears in folder="responses"
    resp = await async_client.get(
        "/api/v1/emails?folder=responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    emails = resp.json()["emails"]
    assert len(emails) == 1
    assert emails[0]["message_id"] == "<client-reply-001@external.com>"


@pytest.mark.asyncio
async def test_14_bounce_notification_does_not_set_has_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """14. Bounce notification does not set thread.has_reply to True."""
    token = await register_and_login(async_client, "user_m13_14@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-14")
    acc_id = await create_account_helper(async_client, token, comp_id)

    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Important Notice",
        has_reply=False,
        message_count=1,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<notice-001@company.com>",
        sender="sender@company.com",
        recipients=["unreachable@external.com"],
        subject="Important Notice",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    # Sync bounce notification
    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-notice-001@mail.server.com>",
        orig_msg_id="<notice-001@company.com>",
        recipient="unreachable@external.com",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("2002", bounce_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Thread.has_reply must remain False!
    await db_session.refresh(thread)
    assert thread.has_reply is False

    # Verify folder="responses" is empty
    resp = await async_client.get(
        "/api/v1/emails?folder=responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["emails"]) == 0


@pytest.mark.asyncio
async def test_15_auto_reply_does_not_set_has_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """15. Automatic or out-of-office reply does not set thread.has_reply to True."""
    token = await register_and_login(async_client, "user_m13_15@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-15")
    acc_id = await create_account_helper(async_client, token, comp_id)

    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Quarterly Review",
        has_reply=False,
        message_count=1,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<review-001@company.com>",
        sender="sender@company.com",
        recipients=["vacationing@external.com"],
        subject="Quarterly Review",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    # Sync out-of-office automated reply
    ooo_bytes = make_auto_reply(
        msg_id="<ooo-reply-001@external.com>",
        orig_msg_id="<review-001@company.com>",
        subject="Automatic reply: Quarterly Review",
        auto_submitted="auto-replied",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("2003", ooo_bytes)]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert sync_resp.status_code == 200

    # Thread.has_reply must remain False!
    await db_session.refresh(thread)
    assert thread.has_reply is False

    # Responses folder must not contain the auto-reply
    resp = await async_client.get(
        "/api/v1/emails?folder=responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["emails"]) == 0


@pytest.mark.asyncio
async def test_16_and_17_and_18_and_19_bounced_folder_and_thread_preservation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """16, 17, 18, 19. Bounced email folder behavior, thread relationship preservation, and responses exclusion."""
    token = await register_and_login(async_client, "user_m13_16@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-16")
    acc_id = await create_account_helper(async_client, token, comp_id)

    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Account Activation",
        has_reply=False,
        message_count=1,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<activation-001@company.com>",
        sender="sender@company.com",
        recipients=["invalid-user@external.com"],
        subject="Account Activation",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-activation-001@mail.server.com>",
        orig_msg_id="<activation-001@company.com>",
        recipient="invalid-user@external.com",
        status_code="5.1.2",
        diagnostic_code="Host unknown",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("3001", bounce_bytes)]):
        await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )

    # 16. Appears in folder="bounced"
    bounced_res = await async_client.get(
        "/api/v1/emails?folder=bounced",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bounced_res.status_code == 200
    bounced_ids = [m["message_id"] for m in bounced_res.json()["emails"]]
    assert "<activation-001@company.com>" in bounced_ids

    # 17. No longer appears in folder="sent"
    sent_res = await async_client.get(
        "/api/v1/emails?folder=sent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sent_res.status_code == 200
    sent_ids = [m["message_id"] for m in sent_res.json()["emails"]]
    assert "<activation-001@company.com>" not in sent_ids

    # 18. Not treated as genuine response
    resp_res = await async_client.get(
        "/api/v1/emails?folder=responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_res.status_code == 200
    assert len(resp_res.json()["emails"]) == 0

    # 19. Original thread relationship preserved
    await db_session.refresh(orig_email)
    assert orig_email.thread_id == thread.id


@pytest.mark.asyncio
async def test_20_duplicate_bounce_synchronization_safe_and_idempotent(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """20. Duplicate bounce synchronization does not create duplicates or corrupt state."""
    token = await register_and_login(async_client, "user_m13_20@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-20")
    acc_id = await create_account_helper(async_client, token, comp_id)

    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<dup-test-001@company.com>",
        sender="sender@company.com",
        recipients=["fail@external.com"],
        subject="Dup Test",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    bounce_bytes = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-dup-001@mail.server.com>",
        orig_msg_id="<dup-test-001@company.com>",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages") as mock_fetch:
        # First sync
        mock_fetch.return_value = [("4001", bounce_bytes)]
        resp1 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert resp1.status_code == 200
        assert resp1.json()["new_messages"] == 1

        # Second sync with exact same UID and Message-ID
        resp2 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert resp2.status_code == 200
        assert resp2.json()["new_messages"] == 0
        assert resp2.json()["duplicates_skipped"] == 1

    # Verify original email remains cleanly BOUNCED
    await db_session.refresh(orig_email)
    assert orig_email.status == EmailStatus.BOUNCED.value


@pytest.mark.asyncio
async def test_21_malformed_bounce_message_handled_safely(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """21. Malformed bounce message does not crash synchronization."""
    token = await register_and_login(async_client, "user_m13_21@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M13-21")
    acc_id = await create_account_helper(async_client, token, comp_id)

    corrupted_bytes = b"This is not a valid MIME email at all \x00\xff\xfe random garbage"

    with patch.object(EmailParser, "parse_raw_email", side_effect=Exception("Corrupted raw email byte stream")):
        with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("5001", corrupted_bytes)]):
            sync_resp = await async_client.post(
                f"/api/v1/email-accounts/{acc_id}/sync",
                headers={"Authorization": f"Bearer {token}"},
                json={"folder": "INBOX", "max_messages": 50},
            )
            assert sync_resp.status_code == 200
            data = sync_resp.json()
            assert data["status"] == "PARTIAL"
            assert data["malformed_skipped"] == 1
            assert data["new_messages"] == 0
