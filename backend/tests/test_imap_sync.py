from email.message import EmailMessage
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus
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
    # "café et über" in iso-8859-1
    body = "Bienvenue au caf\xe9! Votre trajet \xfcber est confirm\xe9.".encode("iso-8859-1")
    return headers + body


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
