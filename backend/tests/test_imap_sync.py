from email.message import EmailMessage
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailAttachment, EmailDirection, EmailStatus
from app.services.imap.client import IMAPClient
from app.services.imap.exceptions import (
    IMAPAuthenticationError,
    IMAPConnectionError,
)
from app.services.imap.parser import EmailParser


def make_plain_email(msg_id: str, subject: str, from_addr: str, to_addrs: list[str], body: str) -> bytes:
    """Helper creating a standard plain-text RFC 822 email message."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = "Mon, 14 Sep 2026 10:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


def make_multipart_email(
    msg_id: str,
    subject: str,
    from_addr: str,
    to_addrs: list[str],
    text_body: str,
    html_body: str,
    cc_addrs: list[str] = None,
) -> bytes:
    """Helper creating a multipart/alternative RFC 822 email message with text and HTML."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Date"] = "Mon, 14 Sep 2026 10:30:00 +0000"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg.as_bytes()


def make_encoded_header_email(msg_id: str, from_addr: str, to_addrs: list[str]) -> bytes:
    """Helper creating an email with RFC 2047 encoded words in Subject and display name."""
    raw = (
        f"Message-ID: {msg_id}\r\n"
        f"From: =?utf-8?B?U3VwcG9ydCDwn5Ka?= <{from_addr}>\r\n"
        f"To: {', '.join(to_addrs)}\r\n"
        f"Subject: =?utf-8?B?Tm91dmVsbGUgY29tbWFuZGUg8J+Snw==?=\r\n"
        f"Date: Mon, 14 Sep 2026 11:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Bonjour, voici votre facture."
    )
    return raw.encode("utf-8")


def make_iso_encoded_email(msg_id: str, from_addr: str, to_addrs: list[str]) -> bytes:
    """Helper creating an email encoded in ISO-8859-1 with special characters."""
    headers = (
        f"Message-ID: {msg_id}\r\n"
        f"From: {from_addr}\r\n"
        f"To: {', '.join(to_addrs)}\r\n"
        f"Subject: Reunion cafe et uber\r\n"
        f"Date: Mon, 14 Sep 2026 12:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=iso-8859-1\r\n"
        f"\r\n"
    ).encode("ascii")
    body = "café et über".encode("iso-8859-1")
    return headers + body


from contextlib import contextmanager

@contextmanager
def mock_imap_fetch(messages: list[tuple[str, bytes]]):
    """Context manager mocking IMAPClient connection and returning provided (uid, raw_bytes) messages."""
    uids = [uid for uid, _ in messages]
    raw_dict = {uid: raw for uid, raw in messages}
    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=len(uids)),
        patch.object(IMAPClient, "search_uids", return_value=uids),
        patch.object(IMAPClient, "fetch_message_by_uid", side_effect=lambda uid: raw_dict[uid]),
        patch.object(
            IMAPClient,
            "fetch_messages_batch",
            side_effect=lambda requested_uids: [(u, raw_dict[u], None) for u in requested_uids if u in raw_dict],
        ),
        patch.object(IMAPClient, "close"),
    ):
        yield


def make_email_with_attachments(
    msg_id: str,
    subject: str,
    from_addr: str,
    to_addrs: list[str],
    body: str,
    attachments: list[tuple[str, str, bytes]],
) -> bytes:
    """Helper creating a multipart/mixed email message with file attachments."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = "Mon, 14 Sep 2026 13:00:00 +0000"
    msg.set_content(body)

    for filename, mime_type, content in attachments:
        maintype, subtype = mime_type.split("/", 1)
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    return msg.as_bytes()


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Helper to register and login a user, returning their JWT bearer token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Test Company") -> int:
    """Helper to create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


async def create_email_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    name: str = "Support Inbox",
    email: str = "support@company.com",
    imap_password: str = "SuperSecretImapPassword!",
) -> int:
    """Helper to create an email account with IMAP configuration."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
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
            "imap_password": imap_password,
        },
    )
    return resp.json()["id"]


# -----------------------------------------------------------------------------
# Test Scenarios
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_imap_sync_and_parsing(async_client: AsyncClient, db_session: AsyncSession):
    """Test successful IMAP synchronization, MIME parsing, and database persistence."""
    owner_token = await register_and_login(async_client, "owner_m6@test.com", "Owner User")
    company_id = await create_company_helper(async_client, owner_token, "Acme Corp M6")
    imap_pw = "ConfidentialImapPass456!"
    account_id = await create_email_account_helper(
        async_client,
        owner_token,
        company_id,
        name="Acme Support",
        email="support@acme.com",
        imap_password=imap_pw,
    )

    msg1_raw = make_plain_email(
        msg_id="<msg-101@client.org>",
        subject="Order Question",
        from_addr="Client Alice <alice@client.org>",
        to_addrs=["support@acme.com"],
        body="Hello, when will my order ship?",
    )
    msg2_raw = make_multipart_email(
        msg_id="<msg-102@client.org>",
        subject="Status Update",
        from_addr="Bob <bob@client.org>",
        to_addrs=["support@acme.com"],
        cc_addrs=["manager@client.org"],
        text_body="Plain update",
        html_body="<p>HTML <b>update</b></p>",
    )

    with (
        patch.object(IMAPClient, "connect") as mock_connect,
        patch.object(IMAPClient, "login") as mock_login,
        patch.object(IMAPClient, "select_folder", return_value=2) as mock_select,
        patch.object(IMAPClient, "search_uids", return_value=["1", "2"]) as mock_search,
        patch.object(IMAPClient, "fetch_message_by_uid", side_effect=[msg1_raw, msg2_raw]) as mock_fetch,
        patch.object(IMAPClient, "close") as mock_close,
    ):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["email_account_id"] == account_id
        assert data["status"] == "SUCCESS"
        assert data["folder"] == "INBOX"
        assert data["total_discovered"] == 2
        assert data["new_messages"] == 2
        assert data["duplicates_skipped"] == 0
        assert data["malformed_skipped"] == 0

        # Verify IMAP client calls
        mock_connect.assert_called_once_with(host="imap.company.com", port=993, security_mode="SSL")
        mock_login.assert_called_once_with(username="support@acme.com", password=imap_pw)
        mock_select.assert_called_once_with(folder="INBOX")
        mock_search.assert_called_once_with("ALL")
        assert mock_fetch.call_count == 2
        mock_close.assert_called_once()

        # Verify Database Persistence
        emails = (
            await db_session.execute(
                select(Email).where(Email.email_account_id == account_id).order_by(Email.id.asc())
            )
        ).scalars().all()

        assert len(emails) == 2
        # Email 1 assertions
        assert emails[0].direction == EmailDirection.INCOMING.value
        assert emails[0].status == EmailStatus.RECEIVED.value
        assert emails[0].message_id == "<msg-101@client.org>"
        assert emails[0].imap_uid == "1"
        assert emails[0].sender == "Client Alice <alice@client.org>"
        assert emails[0].recipients == ["support@acme.com"]
        assert emails[0].subject == "Order Question"
        assert "when will my order ship?" in emails[0].body_text
        assert emails[0].body_html is None
        assert emails[0].is_read is False

        # Email 2 assertions (multipart)
        assert emails[1].direction == EmailDirection.INCOMING.value
        assert emails[1].status == EmailStatus.RECEIVED.value
        assert emails[1].message_id == "<msg-102@client.org>"
        assert emails[1].imap_uid == "2"
        assert emails[1].cc == ["manager@client.org"]
        assert emails[1].body_text.strip() == "Plain update"
        assert "<p>HTML <b>update</b></p>" in emails[1].body_html

        # Verify Account last_synced_at was updated
        account = (
            await db_session.execute(select(EmailAccount).where(EmailAccount.id == account_id))
        ).scalars().first()
        assert account.last_synced_at is not None


@pytest.mark.asyncio
async def test_duplicate_prevention(async_client: AsyncClient, db_session: AsyncSession):
    """Test that repeated synchronization does not insert duplicate messages."""
    owner_token = await register_and_login(async_client, "owner_dup@test.com", "Dup Owner")
    company_id = await create_company_helper(async_client, owner_token, "DupCorp")
    account_id = await create_email_account_helper(
        async_client,
        owner_token,
        company_id,
        name="Dup Inbox",
        email="inbox@dupcorp.com",
    )

    msg_raw = make_plain_email(
        msg_id="<msg-unique-555@example.com>",
        subject="Invoice #555",
        from_addr="billing@example.com",
        to_addrs=["inbox@dupcorp.com"],
        body="Invoice details.",
    )

    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=1),
        patch.object(IMAPClient, "search_uids", return_value=["100"]),
        patch.object(IMAPClient, "fetch_message_by_uid", return_value=msg_raw),
        patch.object(IMAPClient, "close"),
    ):
        # 1. First sync -> 1 new message
        resp1 = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["new_messages"] == 1
        assert resp1.json()["duplicates_skipped"] == 0

        # 2. Second sync with same message -> 0 new, 1 duplicate skipped
        resp2 = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["new_messages"] == 0
        assert resp2.json()["duplicates_skipped"] == 1

        # Check DB row count remains 1
        emails = (
            await db_session.execute(select(Email).where(Email.email_account_id == account_id))
        ).scalars().all()
        assert len(emails) == 1


@pytest.mark.asyncio
async def test_account_scoped_deduplication(async_client: AsyncClient, db_session: AsyncSession):
    """Test that two different email accounts receiving the same Message-ID each persist a record."""
    owner_token = await register_and_login(async_client, "owner_multi@test.com", "Multi Owner")
    company_id = await create_company_helper(async_client, owner_token, "MultiCorp")

    account1_id = await create_email_account_helper(
        async_client, owner_token, company_id, "Inbox 1", "inbox1@multicorp.com"
    )
    account2_id = await create_email_account_helper(
        async_client, owner_token, company_id, "Inbox 2", "inbox2@multicorp.com"
    )

    shared_msg_raw = make_plain_email(
        msg_id="<broadcast-newsletter@service.org>",
        subject="Monthly Digest",
        from_addr="newsletter@service.org",
        to_addrs=["all@multicorp.com"],
        body="Newsletter contents.",
    )

    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=1),
        patch.object(IMAPClient, "search_uids", return_value=["1"]),
        patch.object(IMAPClient, "fetch_message_by_uid", return_value=shared_msg_raw),
        patch.object(IMAPClient, "close"),
    ):
        # Sync account 1
        resp1 = await async_client.post(
            f"/api/v1/email-accounts/{account1_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp1.json()["new_messages"] == 1

        # Sync account 2 with same message_id
        resp2 = await async_client.post(
            f"/api/v1/email-accounts/{account2_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp2.json()["new_messages"] == 1

        # Verify both accounts have their own record
        emails1 = (await db_session.execute(select(Email).where(Email.email_account_id == account1_id))).scalars().all()
        emails2 = (await db_session.execute(select(Email).where(Email.email_account_id == account2_id))).scalars().all()
        assert len(emails1) == 1
        assert len(emails2) == 1
        assert emails1[0].message_id == emails2[0].message_id


@pytest.mark.asyncio
async def test_encoded_headers_and_charset_parsing(async_client: AsyncClient, db_session: AsyncSession):
    """Test parsing RFC 2047 encoded words and ISO-8859-1 character set encodings."""
    owner_token = await register_and_login(async_client, "owner_enc@test.com", "Enc Owner")
    company_id = await create_company_helper(async_client, owner_token, "EncCorp")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "Enc Inbox", "enc@enccorp.com")

    enc_msg_raw = make_encoded_header_email("<enc-1@test.com>", "support@partner.fr", ["enc@enccorp.com"])
    iso_msg_raw = make_iso_encoded_email("<iso-2@test.com>", "paris@partner.fr", ["enc@enccorp.com"])

    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=2),
        patch.object(IMAPClient, "search_uids", return_value=["1", "2"]),
        patch.object(IMAPClient, "fetch_message_by_uid", side_effect=[enc_msg_raw, iso_msg_raw]),
        patch.object(IMAPClient, "close"),
    ):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["new_messages"] == 2

        emails = (
            await db_session.execute(
                select(Email).where(Email.email_account_id == account_id).order_by(Email.id.asc())
            )
        ).scalars().all()

        # Check encoded header decoding
        assert "Nouvelle commande" in emails[0].subject
        assert "Support" in emails[0].sender

        # Check ISO-8859-1 decoding
        assert "café" in emails[1].body_text
        assert "über" in emails[1].body_text


@pytest.mark.asyncio
async def test_malformed_email_skipped_without_crashing_sync(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a malformed email is skipped while valid emails in the batch are safely persisted."""
    owner_token = await register_and_login(async_client, "owner_mal@test.com", "Mal Owner")
    company_id = await create_company_helper(async_client, owner_token, "MalCorp")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "Mal Inbox", "mal@malcorp.com")

    valid_msg = make_plain_email("<valid-1@test.com>", "Valid Subject", "valid@test.com", ["mal@malcorp.com"], "Valid body")
    malformed_bytes = b"CORRUPTED HEADER WITHOUT SEPARATOR \x00\xff\xfe"

    # We patch EmailParser.parse_raw_email on the second call to raise an exception simulating corrupted parsing
    original_parse = EmailParser.parse_raw_email

    def faulty_parse(raw_bytes, imap_uid=None):
        if raw_bytes == malformed_bytes:
            raise ValueError("Corrupted MIME payload syntax")
        return original_parse(raw_bytes, imap_uid=imap_uid)

    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=2),
        patch.object(IMAPClient, "search_uids", return_value=["1", "2"]),
        patch.object(IMAPClient, "fetch_message_by_uid", side_effect=[valid_msg, malformed_bytes]),
        patch.object(IMAPClient, "close"),
        patch.object(EmailParser, "parse_raw_email", side_effect=faulty_parse),
    ):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PARTIAL"
        assert data["total_discovered"] == 2
        assert data["new_messages"] == 1
        assert data["malformed_skipped"] == 1

        # Check that valid email was saved
        emails = (await db_session.execute(select(Email).where(Email.email_account_id == account_id))).scalars().all()
        assert len(emails) == 1
        assert emails[0].message_id == "<valid-1@test.com>"


@pytest.mark.asyncio
async def test_authorization_member_and_cross_company(async_client: AsyncClient):
    """Test access control: authorized member succeeds, unauthorized member and cross-company user fail."""
    owner_a_token = await register_and_login(async_client, "owner_a_sync@test.com", "Owner A")
    company_a_id = await create_company_helper(async_client, owner_a_token, "Company A Sync")
    account_a_id = await create_email_account_helper(
        async_client, owner_a_token, company_a_id, "Sales A", "sales@companya.com"
    )

    # Member in Company A
    member_a_token = await register_and_login(async_client, "member_a_sync@test.com", "Member A")
    await async_client.post(
        f"/api/v1/companies/{company_a_id}/members",
        headers={"Authorization": f"Bearer {owner_a_token}"},
        json={"email": "member_a_sync@test.com", "role": "MEMBER"},
    )

    # User in Company B
    owner_b_token = await register_and_login(async_client, "owner_b_sync@test.com", "Owner B")
    await create_company_helper(async_client, owner_b_token, "Company B Sync")

    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=0),
        patch.object(IMAPClient, "search_uids", return_value=[]),
        patch.object(IMAPClient, "close"),
    ):
        # 1. Member without explicit access -> 403 Forbidden
        resp_unauth = await async_client.post(
            f"/api/v1/email-accounts/{account_a_id}/sync",
            headers={"Authorization": f"Bearer {member_a_token}"},
        )
        assert resp_unauth.status_code == 403

        # 2. Grant access to member
        user_resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {member_a_token}"},
        )
        member_id = user_resp.json()["id"]
        await async_client.post(
            f"/api/v1/companies/{company_a_id}/email-accounts/{account_a_id}/access",
            headers={"Authorization": f"Bearer {owner_a_token}"},
            json={"user_id": member_id},
        )

        # 3. Member with access -> 200 OK
        resp_auth = await async_client.post(
            f"/api/v1/email-accounts/{account_a_id}/sync",
            headers={"Authorization": f"Bearer {member_a_token}"},
        )
        assert resp_auth.status_code == 200

        # 4. User from Company B -> 403 Forbidden
        resp_cross = await async_client.post(
            f"/api/v1/email-accounts/{account_a_id}/sync",
            headers={"Authorization": f"Bearer {owner_b_token}"},
        )
        assert resp_cross.status_code == 403


@pytest.mark.asyncio
async def test_imap_connection_and_auth_failures(async_client: AsyncClient):
    """Test safe handling of connection and authentication errors (502, no leaked credentials)."""
    owner_token = await register_and_login(async_client, "owner_err@test.com", "Err Owner")
    company_id = await create_company_helper(async_client, owner_token, "ErrCorp")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "Err", "err@errcorp.com")

    # 1. Connection Error
    with patch.object(IMAPClient, "connect", side_effect=IMAPConnectionError("Failed to connect to IMAP server.")):
        resp_conn = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_conn.status_code == 502
        assert "Could not connect to IMAP server" in resp_conn.json()["detail"]

    # 2. Authentication Error
    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login", side_effect=IMAPAuthenticationError("IMAP authentication failed.")),
    ):
        resp_auth = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp_auth.status_code == 502
        assert "IMAP authentication failed" in resp_auth.json()["detail"]


@pytest.mark.asyncio
async def test_inactive_account_cannot_sync(async_client: AsyncClient):
    """Test that deactivated accounts cannot be synchronized (400 Bad Request)."""
    owner_token = await register_and_login(async_client, "owner_inact_sync@test.com", "Inact Owner")
    company_id = await create_company_helper(async_client, owner_token, "InactSyncCorp")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "Inact", "inact@corp.com")

    # Deactivate account
    await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"is_active": False},
    )

    resp = await async_client.post(
        f"/api/v1/email-accounts/{account_id}/sync",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_database_duplicate_protection_under_concurrency(async_client: AsyncClient, db_session: AsyncSession):
    """Test that the database unique index on (email_account_id, imap_uid) prevents duplicates."""
    from sqlalchemy.exc import IntegrityError

    owner_token = await register_and_login(async_client, "owner_concurrent@test.com", "Concurrent Owner")
    company_id = await create_company_helper(async_client, owner_token, "ConcurrentCorp")
    account_id = await create_email_account_helper(
        async_client, owner_token, company_id, "Concurrent Inbox", "concurrent@corp.com"
    )

    # 1. Direct database check: insert first email
    email1 = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<test-concurrent-1@corp.com>",
        imap_uid="999",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="sender@corp.com",
        recipients=["concurrent@corp.com"],
        subject="Test 1",
    )
    db_session.add(email1)
    await db_session.commit()

    # 2. Attempt duplicate insert with same (email_account_id, imap_uid)
    email2 = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<test-concurrent-2@corp.com>",
        imap_uid="999",  # Same UID
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="sender@corp.com",
        recipients=["concurrent@corp.com"],
        subject="Test 2 Duplicate UID",
    )
    db_session.add(email2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # 3. Verify that outgoing emails with imap_uid=None do not conflict
    out1 = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<out-1@corp.com>",
        imap_uid=None,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="concurrent@corp.com",
        recipients=["client1@example.com"],
        subject="Out 1",
    )
    out2 = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<out-2@corp.com>",
        imap_uid=None,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="concurrent@corp.com",
        recipients=["client2@example.com"],
        subject="Out 2",
    )
    db_session.add(out1)
    db_session.add(out2)
    await db_session.commit()  # Both succeed because NULLs are distinct


@pytest.mark.asyncio
async def test_incoming_email_with_pdf_attachment(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that an incoming email with a PDF attachment is correctly parsed, persisted, and retrievable."""
    token = await register_and_login(async_client, "pdf_test_user@example.com", "PDF Tester")
    company_id = await create_company_helper(async_client, token, "PDF Test Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "PDF Account", "pdf_sync@example.com"
    )

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Title (Invoice) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    raw_email = make_email_with_attachments(
        msg_id="<msg-pdf-1@example.com>",
        subject="Monthly Invoice",
        from_addr="billing@supplier.com",
        to_addrs=["pdf_sync@example.com"],
        body="Please find attached your invoice for this month.",
        attachments=[("invoice_2026.pdf", "application/pdf", pdf_bytes)],
    )

    with mock_imap_fetch([("101", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["new_messages"] == 1

    # Find the inserted email
    email_res = await db_session.execute(
        select(Email).where(Email.email_account_id == account_id, Email.message_id == "<msg-pdf-1@example.com>")
    )
    email_record = email_res.scalars().first()
    assert email_record is not None
    assert email_record.subject == "Monthly Invoice"

    # Query attachments endpoint
    att_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_resp.status_code == 200
    att_data = att_resp.json()
    assert att_data["total"] == 1
    assert len(att_data["attachments"]) == 1

    attachment = att_data["attachments"][0]
    assert attachment["file_name"] == "invoice_2026.pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["file_size"] == len(pdf_bytes)

    # Download attachment
    dl_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments/{attachment['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.content == pdf_bytes
    assert "invoice_2026.pdf" in dl_resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_incoming_email_with_multiple_attachments(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that multiple attachments (DOCX, XLSX, PNG) on a single email are all stored."""
    token = await register_and_login(async_client, "multi_att_user@example.com", "Multi Att")
    company_id = await create_company_helper(async_client, token, "Multi Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "Multi Inbox", "multi@example.com"
    )

    docx_bytes = b"PK\x03\x04[fake docx binary data]"
    xlsx_bytes = b"PK\x03\x04[fake xlsx binary data]"
    png_bytes = b"\x89PNG\r\n\x1a\n[fake png binary data]"

    raw_email = make_email_with_attachments(
        msg_id="<msg-multi-att@example.com>",
        subject="Project Files",
        from_addr="client@partner.com",
        to_addrs=["multi@example.com"],
        body="Here are the project specification files and screenshot.",
        attachments=[
            ("spec.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_bytes),
            ("budget.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx_bytes),
            ("diagram.png", "image/png", png_bytes),
        ],
    )

    with mock_imap_fetch([("102", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["new_messages"] == 1

    email_res = await db_session.execute(
        select(Email).where(Email.email_account_id == account_id, Email.message_id == "<msg-multi-att@example.com>")
    )
    email_record = email_res.scalars().first()
    assert email_record is not None

    att_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_resp.status_code == 200
    att_data = att_resp.json()
    assert att_data["total"] == 3

    filenames = [a["file_name"] for a in att_data["attachments"]]
    assert "spec.docx" in filenames
    assert "budget.xlsx" in filenames
    assert "diagram.png" in filenames


@pytest.mark.asyncio
async def test_incoming_email_with_encoded_filename(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that RFC 2047 encoded filenames are decoded cleanly."""
    token = await register_and_login(async_client, "encoded_user@example.com", "Encoded Tester")
    company_id = await create_company_helper(async_client, token, "Encoded Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "Encoded Inbox", "encoded@example.com"
    )

    raw_email = (
        b"Message-ID: <msg-encoded-fn@example.com>\r\n"
        b"Subject: Rapport\r\n"
        b"From: finance@example.com\r\n"
        b"To: encoded@example.com\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=\"====boundary====\"\r\n"
        b"\r\n"
        b"--====boundary====\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Veuillez trouver ci-joint votre document.\r\n"
        b"--====boundary====\r\n"
        b"Content-Type: application/pdf\r\n"
        b"Content-Disposition: attachment; filename=\"=?UTF-8?B?UHLDvGZ1bmdfMjAyNi5wZGY=?=\"\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"UmFwcG9ydCBhbm51ZWwgMjAyNg==\r\n"
        b"--====boundary====--\r\n"
    )

    with mock_imap_fetch([("103", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    email_res = await db_session.execute(
        select(Email).where(Email.email_account_id == account_id, Email.message_id == "<msg-encoded-fn@example.com>")
    )
    email_record = email_res.scalars().first()
    assert email_record is not None

    att_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_resp.status_code == 200
    att_data = att_resp.json()
    assert att_data["total"] == 1
    assert att_data["attachments"][0]["file_name"] == "Prüfung_2026.pdf"


@pytest.mark.asyncio
async def test_incoming_email_without_attachments(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that standard plain/HTML emails without attachments create zero attachment records."""
    token = await register_and_login(async_client, "no_att_user@example.com", "No Att Tester")
    company_id = await create_company_helper(async_client, token, "No Att Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "No Att Inbox", "noatt@example.com"
    )

    raw_email = make_multipart_email(
        msg_id="<msg-no-att@example.com>",
        subject="Simple Email",
        from_addr="friend@example.com",
        to_addrs=["noatt@example.com"],
        text_body="Hello, this email has no attachments.",
        html_body="<p>Hello, this email has no attachments.</p>",
    )

    with mock_imap_fetch([("104", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    email_res = await db_session.execute(
        select(Email).where(Email.email_account_id == account_id, Email.message_id == "<msg-no-att@example.com>")
    )
    email_record = email_res.scalars().first()
    assert email_record is not None

    att_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_resp.status_code == 200
    assert att_resp.json()["total"] == 0
    assert len(att_resp.json()["attachments"]) == 0


@pytest.mark.asyncio
async def test_incoming_email_attachment_cross_company_authorization(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that users from another company cannot list or download attachments."""
    token1 = await register_and_login(async_client, "user_co1@example.com", "Co1 User")
    co1_id = await create_company_helper(async_client, token1, "Company 1")
    acc1_id = await create_email_account_helper(async_client, token1, co1_id, "Co1 Inbox", "co1@example.com")

    token2 = await register_and_login(async_client, "user_co2@example.com", "Co2 User")
    await create_company_helper(async_client, token2, "Company 2")

    pdf_bytes = b"%PDF-1.4 [secret company 1 content]"
    raw_email = make_email_with_attachments(
        msg_id="<msg-co1-secret@example.com>",
        subject="Confidential Report",
        from_addr="hq@co1.com",
        to_addrs=["co1@example.com"],
        body="Sensitive financial data.",
        attachments=[("secrets.pdf", "application/pdf", pdf_bytes)],
    )

    with mock_imap_fetch([("105", raw_email)]):
        await async_client.post(
            f"/api/v1/email-accounts/{acc1_id}/sync",
            headers={"Authorization": f"Bearer {token1}"},
        )

    email_res = await db_session.execute(
        select(Email).where(Email.email_account_id == acc1_id, Email.message_id == "<msg-co1-secret@example.com>")
    )
    email_record = email_res.scalars().first()

    # User 2 tries to list attachments for Company 1's email -> 403 Forbidden
    unauth_list = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert unauth_list.status_code == 403

    # User 1 lists attachment to get ID
    att_resp = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments",
        headers={"Authorization": f"Bearer {token1}"},
    )
    att_id = att_resp.json()["attachments"][0]["id"]

    # User 2 tries to download attachment -> 403 Forbidden
    unauth_dl = await async_client.get(
        f"/api/v1/emails/{email_record.id}/attachments/{att_id}/download",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert unauth_dl.status_code == 403


@pytest.mark.asyncio
async def test_resync_does_not_duplicate_attachments(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that repeated synchronization does not create duplicate attachment records."""
    token = await register_and_login(async_client, "resync_att_user@example.com", "Resync Att")
    company_id = await create_company_helper(async_client, token, "Resync Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "Resync Inbox", "resync@example.com"
    )

    pdf_bytes = b"%PDF-1.4 [idempotent content]"
    raw_email = make_email_with_attachments(
        msg_id="<msg-resync-att@example.com>",
        subject="Single Attachment Sync",
        from_addr="partner@example.com",
        to_addrs=["resync@example.com"],
        body="Testing idempotency.",
        attachments=[("idempotent.pdf", "application/pdf", pdf_bytes)],
    )

    # First sync: 1 new message
    with mock_imap_fetch([("106", raw_email)]):
        resp1 = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["new_messages"] == 1

    # Second sync with same message: 0 new messages, 1 duplicate skipped
    with mock_imap_fetch([("106", raw_email)]):
        resp2 = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["new_messages"] == 0
        assert resp2.json()["duplicates_skipped"] == 1

    # Verify only 1 attachment exists in DB
    att_res = await db_session.execute(
        select(EmailAttachment).join(Email).where(Email.email_account_id == account_id)
    )
    attachments = att_res.scalars().all()
    assert len(attachments) == 1
    assert attachments[0].file_name == "idempotent.pdf"


@pytest.mark.asyncio
async def test_backfill_missing_attachments_on_previously_synced_email(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that an email previously stored without attachments gets its attachments backfilled upon re-sync."""
    token = await register_and_login(async_client, "backfill_user@example.com", "Backfill Tester")
    company_id = await create_company_helper(async_client, token, "Backfill Corp")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "Backfill Inbox", "backfill@example.com"
    )

    # 1. Insert an existing email directly in DB with no attachments (simulating previously fetched email)
    msg_id = "<msg-backfill-test@example.com>"
    existing_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id=msg_id,
        imap_uid="201",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="partner@supplier.com",
        recipients=["backfill@example.com"],
        subject="Invoice with Missing Attachment",
        body_text="Invoice body without attachments yet.",
    )
    db_session.add(existing_email)
    await db_session.commit()
    await db_session.refresh(existing_email)

    # Confirm 0 attachments initially
    init_atts = (await db_session.execute(
        select(EmailAttachment).where(EmailAttachment.email_id == existing_email.id)
    )).scalars().all()
    assert len(init_atts) == 0

    # 2. Prepare raw IMAP email with a PDF attachment
    pdf_bytes = b"%PDF-1.4 [backfill test content]"
    raw_email = make_email_with_attachments(
        msg_id=msg_id,
        subject="Invoice with Missing Attachment",
        from_addr="partner@supplier.com",
        to_addrs=["backfill@example.com"],
        body="Invoice body with PDF attachment.",
        attachments=[("backfill_invoice.pdf", "application/pdf", pdf_bytes)],
    )

    # 3. Trigger IMAP sync
    with mock_imap_fetch([("201", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_messages"] == 0
        assert data["duplicates_skipped"] == 1

    # 4. Verify that attachment was backfilled and associated with existing_email
    backfilled_atts = (await db_session.execute(
        select(EmailAttachment).where(EmailAttachment.email_id == existing_email.id)
    )).scalars().all()
    assert len(backfilled_atts) == 1
    assert backfilled_atts[0].file_name == "backfill_invoice.pdf"
    assert backfilled_atts[0].file_size == len(pdf_bytes)

    # 5. Verify download endpoint returns 200 OK and matching content
    dl_resp = await async_client.get(
        f"/api/v1/emails/{existing_email.id}/attachments/{backfilled_atts[0].id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.content == pdf_bytes

    # 6. Re-sync again to verify idempotency (no duplicate attachments created)
    with mock_imap_fetch([("201", raw_email)]):
        resp2 = await async_client.post(
            f"/api/v1/email-accounts/{account_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["duplicates_skipped"] == 1

    repeat_atts = (await db_session.execute(
        select(EmailAttachment).where(EmailAttachment.email_id == existing_email.id)
    )).scalars().all()
    assert len(repeat_atts) == 1

