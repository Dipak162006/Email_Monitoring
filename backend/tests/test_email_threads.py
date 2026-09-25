from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.service import EmailService
from app.modules.emails.thread_service import EmailThreadService
from app.services.imap.client import IMAPClient
from app.services.smtp.client import SMTPClient


def make_raw_email(
    msg_id: str,
    subject: str,
    from_addr: str,
    to_addrs: list[str],
    body: str,
    in_reply_to: str = None,
    references: str = None,
    date_str: str = "Mon, 14 Sep 2026 10:00:00 +0000",
) -> bytes:
    """Helper to construct raw RFC 822 email bytes for IMAP mock responses."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = date_str
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    return msg.as_bytes()


@contextmanager
def mock_imap_sync(raw_messages: list[bytes], uids: list[str] = None):
    """Context manager mocking IMAPClient methods matching test_imap_sync.py."""
    if uids is None:
        uids = [str(i + 1) for i in range(len(raw_messages))]
    with (
        patch.object(IMAPClient, "connect"),
        patch.object(IMAPClient, "login"),
        patch.object(IMAPClient, "select_folder", return_value=len(raw_messages)),
        patch.object(IMAPClient, "search_uids", return_value=uids),
        patch.object(IMAPClient, "fetch_message_by_uid", side_effect=raw_messages),
        patch.object(IMAPClient, "close"),
    ):
        yield


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


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    name: str = "Support Desk",
    email: str = "support@company.com",
) -> int:
    """Helper to create an email account with both SMTP and IMAP settings."""
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
            "smtp_password": "AccountPassword123!",
            "imap_host": "imap.company.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "AccountPassword123!",
        },
    )
    assert resp.status_code == 201, f"Failed to create account: {resp.text}"
    return resp.json()["id"]


# =============================================================================
# Helper / Unit Tests: ThreadService parsing & normalization
# =============================================================================

def test_subject_normalization():
    """Verify that prefixes like Re:, Fwd:, etc. are stripped for display subject."""
    assert EmailThreadService.normalize_subject("Re: Hello World") == "Hello World"
    assert EmailThreadService.normalize_subject("RE: [EXT] Project Update") == "Project Update"
    assert EmailThreadService.normalize_subject("Fwd: Re: Important Note") == "Important Note"
    assert EmailThreadService.normalize_subject("Normal Subject") == "Normal Subject"


def test_references_extraction_and_deduplication():
    """Verify extracting and deduplicating message IDs."""
    raw = "<id1@test.com> <id2@test.com> <id1@test.com> <id3@test.com>"
    extracted = EmailThreadService.extract_message_ids(raw)
    assert extracted == ["<id1@test.com>", "<id2@test.com>", "<id3@test.com>"]


def test_snippet_extraction():
    """Verify snippet generation strips HTML and normalizes whitespace."""
    html = "<div><p>Hello   World!</p><p>This is a <b>test</b> snippet.</p></div>"
    snippet = EmailThreadService.extract_snippet(body_text=None, body_html=html, max_length=50)
    assert "Hello World!" in snippet
    assert "<b>" not in snippet


# =============================================================================
# Core M7 Requirement Tests (1 to 18)
# =============================================================================

@pytest.mark.asyncio
async def test_1_original_outgoing_email_creates_thread(async_client: AsyncClient, db_session: AsyncSession):
    """1. Original outgoing email creates a new conversation thread with correct initial metadata."""
    token = await register_and_login(async_client, "thread_user_1@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 1")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support1@thread.com")

    payload = {
        "email_account_id": acc_id,
        "to": ["customer@example.com"],
        "subject": "New Project Kickoff",
        "body_text": "Welcome to our project! Let's get started.",
    }

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )

    assert resp.status_code == 201
    email_data = resp.json()
    assert email_data["thread_id"] is not None
    thread_id = email_data["thread_id"]

    # Verify thread in database
    thread_stmt = select(EmailThread).where(EmailThread.id == thread_id)
    thread = (await db_session.execute(thread_stmt)).scalars().first()
    assert thread is not None
    assert thread.subject == "New Project Kickoff"
    assert thread.message_count == 1
    assert thread.has_reply is False
    assert thread.company_id == comp_id
    assert thread.email_account_id == acc_id
    assert thread.is_read is True
    assert "Welcome to our project" in thread.snippet


@pytest.mark.asyncio
async def test_2_incoming_unrelated_email_creates_new_thread(async_client: AsyncClient, db_session: AsyncSession):
    """2. Incoming unrelated email without In-Reply-To or References creates a brand new thread."""
    token = await register_and_login(async_client, "thread_user_2@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 2")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support2@thread.com")

    raw_email = make_raw_email(
        msg_id="<inbound-unrelated-1@external.com>",
        subject="Inquiry About Pricing",
        from_addr="lead@external.com",
        to_addrs=["support2@thread.com"],
        body="Can you please send your latest pricing sheet?",
    )

    with mock_imap_sync([raw_email], uids=["101"]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["new_messages"] == 1

    # Check incoming email and its thread
    email_stmt = select(Email).where(Email.message_id == "<inbound-unrelated-1@external.com>")
    email_rec = (await db_session.execute(email_stmt)).scalars().first()
    assert email_rec is not None
    assert email_rec.thread_id is not None

    thread_stmt = select(EmailThread).where(EmailThread.id == email_rec.thread_id)
    thread = (await db_session.execute(thread_stmt)).scalars().first()
    assert thread is not None
    assert thread.subject == "Inquiry About Pricing"
    assert thread.message_count == 1
    assert thread.has_reply is False
    assert thread.is_read is False  # Incoming email defaults to unread


@pytest.mark.asyncio
async def test_3_and_4_incoming_reply_matching_in_reply_to_joins_thread_and_sets_has_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """3 & 4. Incoming email with matching In-Reply-To joins the outgoing email's thread and sets has_reply=True."""
    token = await register_and_login(async_client, "thread_user_3@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 3")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support3@thread.com")

    # Step 1: Send outgoing email
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@partner.com"],
                "subject": "Proposal Discussion",
                "body_text": "Please find our proposal attached.",
            },
        )
    assert send_resp.status_code == 201
    outgoing_email = send_resp.json()
    outgoing_msg_id = outgoing_email["message_id"]
    thread_id = outgoing_email["thread_id"]

    # Verify initial thread state
    thread_before = (await db_session.execute(select(EmailThread).where(EmailThread.id == thread_id))).scalars().first()
    assert thread_before.has_reply is False
    assert thread_before.message_count == 1

    # Step 2: Customer replies to outgoing email
    reply_raw = make_raw_email(
        msg_id="<client-reply-101@partner.com>",
        subject="Re: Proposal Discussion",
        from_addr="client@partner.com",
        to_addrs=["support3@thread.com"],
        body="Thank you! We accept your proposal.",
        in_reply_to=outgoing_msg_id,
        references=outgoing_msg_id,
    )

    with mock_imap_sync([reply_raw], uids=["201"]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["new_messages"] == 1

    # Step 3: Verify incoming reply joined the same thread and set has_reply=True
    reply_stmt = select(Email).where(Email.message_id == "<client-reply-101@partner.com>")
    reply_rec = (await db_session.execute(reply_stmt)).scalars().first()
    assert reply_rec is not None
    assert reply_rec.thread_id == thread_id

    await db_session.refresh(thread_before)
    assert thread_before.message_count == 2
    assert thread_before.has_reply is True
    assert "Thank you! We accept your proposal." in thread_before.snippet


@pytest.mark.asyncio
async def test_5_references_fallback_joins_correct_thread(async_client: AsyncClient, db_session: AsyncSession):
    """5. When In-Reply-To is missing or points to an unknown ID, inspect References from newest to oldest."""
    token = await register_and_login(async_client, "thread_user_5@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 5")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support5@thread.com")

    # Send root outgoing email
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["customer5@client.com"],
                "subject": "System Upgrade Notice",
                "body_text": "System upgrade scheduled for tonight.",
            },
        )
    outgoing_email = send_resp.json()
    root_msg_id = outgoing_email["message_id"]
    thread_id = outgoing_email["thread_id"]

    # Incoming reply with unknown In-Reply-To, but root_msg_id present in References
    incoming_raw = make_raw_email(
        msg_id="<inbound-ref-reply@client.com>",
        subject="Re: System Upgrade Notice",
        from_addr="customer5@client.com",
        to_addrs=["support5@thread.com"],
        body="Understood. Will services stay online?",
        in_reply_to="<unknown-intermediary-id@client.com>",
        references=f"{root_msg_id} <unknown-intermediary-id@client.com>",
    )

    with mock_imap_sync([incoming_raw], uids=["301"]):
        sync_resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_resp.status_code == 200

    reply_rec = (await db_session.execute(select(Email).where(Email.message_id == "<inbound-ref-reply@client.com>"))).scalars().first()
    assert reply_rec is not None
    # Joined the thread found via References
    assert reply_rec.thread_id == thread_id


@pytest.mark.asyncio
async def test_6_7_8_9_outgoing_reply_thread_headers_and_deduplication(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """6, 7, 8, 9. Outgoing reply joins existing thread, sets In-Reply-To and References, and deduplicates IDs."""
    token = await register_and_login(async_client, "thread_user_6@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 6")
    acc_id = await create_account_helper(async_client, token, comp_id, email="agent@thread6.com")

    # 1. Incoming customer question with existing references containing duplicate tokens
    inbound_raw = make_raw_email(
        msg_id="<customer-q-1@external.com>",
        subject="Billing Question",
        from_addr="customer@external.com",
        to_addrs=["agent@thread6.com"],
        body="Why was I charged twice?",
        in_reply_to="<root-invoice@thread6.com>",
        references="<root-invoice@thread6.com> <root-invoice@thread6.com>",  # contains duplicate
    )

    with mock_imap_sync([inbound_raw], uids=["401"]):
        await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )

    parent_email = (await db_session.execute(select(Email).where(Email.message_id == "<customer-q-1@external.com>"))).scalars().first()
    thread_id = parent_email.thread_id
    assert thread_id is not None

    # 2. Agent sends an outgoing reply referencing thread_id and in_reply_to
    reply_payload = {
        "email_account_id": acc_id,
        "to": ["customer@external.com"],
        "subject": "Re: Billing Question",
        "body_text": "We have refunded the duplicate charge.",
        "thread_id": thread_id,
        "in_reply_to": "<customer-q-1@external.com>",
    }

    sent_mime_holder = {}

    def capture_send(*args, **kwargs):
        if "message" in kwargs:
            sent_mime_holder["mime"] = kwargs["message"]
        else:
            for arg in args:
                if isinstance(arg, EmailMessage):
                    sent_mime_holder["mime"] = arg
                    break

    with patch.object(SMTPClient, "send_email_sync", side_effect=capture_send):
        reply_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=reply_payload,
        )


    assert reply_resp.status_code == 201
    sent_data = reply_resp.json()
    # 6. Outgoing reply joins the existing thread
    assert sent_data["thread_id"] == thread_id
    assert sent_data["in_reply_to"] == "<customer-q-1@external.com>"

    # 7 & 8 & 9: Inspect captured MIME headers
    sent_mime = sent_mime_holder["mime"]
    assert sent_mime["In-Reply-To"] == "<customer-q-1@external.com>"

    # References should have <root-invoice@thread6.com> and <customer-q-1@external.com> without duplicates
    references_header = sent_mime["References"]
    assert "<customer-q-1@external.com>" in references_header
    assert "<root-invoice@thread6.com>" in references_header

    # 9. Verify no duplicate message IDs
    tokens = EmailThreadService.extract_message_ids(references_header)
    assert len(tokens) == len(set(tokens))
    assert tokens.count("<root-invoice@thread6.com>") == 1


@pytest.mark.asyncio
async def test_10_and_11_thread_message_count_and_last_message_at(async_client: AsyncClient, db_session: AsyncSession):
    """10 & 11. Thread message_count and last_message_at update accurately on successive messages."""
    token = await register_and_login(async_client, "thread_user_10@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 10")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support10@thread.com")

    # Step 1: Outgoing message
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user10@example.com"],
                "subject": "Follow Up",
                "body_text": "First message.",
            },
        )
    thread_id = r1.json()["thread_id"]
    out_msg_id = r1.json()["message_id"]

    thread_rec = (await db_session.execute(select(EmailThread).where(EmailThread.id == thread_id))).scalars().first()
    assert thread_rec.message_count == 1

    # Step 2: Incoming reply
    incoming_raw = make_raw_email(
        msg_id="<reply-10@example.com>",
        subject="Re: Follow Up",
        from_addr="user10@example.com",
        to_addrs=["support10@thread.com"],
        body="Second message.",
        in_reply_to=out_msg_id,
        date_str="Mon, 14 Sep 2026 15:00:00 +0000",
    )

    with mock_imap_sync([incoming_raw], uids=["501"]):
        await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(thread_rec)
    assert thread_rec.message_count == 2
    assert thread_rec.last_message_at is not None


@pytest.mark.asyncio
async def test_12_thread_detail_returns_messages_chronologically(async_client: AsyncClient, db_session: AsyncSession):
    """12. Thread detail API returns all emails chronologically ordered."""
    token = await register_and_login(async_client, "thread_user_12@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 12")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support12@thread.com")

    now = datetime.now(timezone.utc)

    # Send initial email
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user12@example.com"],
                "subject": "Chronological Thread Test",
                "body_text": "Message 1 (Initial)",
            },
        )
    thread_id = r1.json()["thread_id"]
    msg1_id = r1.json()["message_id"]

    # Explicitly set Message 1 sent_at to 10 minutes ago
    m1_rec = (await db_session.execute(select(Email).where(Email.message_id == msg1_id))).scalars().first()
    m1_rec.sent_at = now - timedelta(minutes=10)
    await db_session.commit()

    # Sync message 2 (incoming) with date 5 minutes ago
    date_str_m2 = (now - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    raw2 = make_raw_email(
        msg_id="<reply-m2@example.com>",
        subject="Re: Chronological Thread Test",
        from_addr="user12@example.com",
        to_addrs=["support12@thread.com"],
        body="Message 2 (Incoming response)",
        in_reply_to=msg1_id,
        date_str=date_str_m2,
    )

    with mock_imap_sync([raw2], uids=["601"]):
        await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )

    # Send message 3 (outgoing response) with date now
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user12@example.com"],
                "subject": "Re: Chronological Thread Test",
                "body_text": "Message 3 (Final closing)",
                "thread_id": thread_id,
                "in_reply_to": "<reply-m2@example.com>",
            },
        )

    # Fetch thread detail
    detail_resp = await async_client.get(
        f"/api/v1/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["message_count"] == 3
    emails = detail_data["emails"]
    assert len(emails) == 3
    assert emails[0]["body_text"].strip() == "Message 1 (Initial)"
    assert emails[1]["body_text"].strip() == "Message 2 (Incoming response)"
    assert emails[2]["body_text"].strip() == "Message 3 (Final closing)"




@pytest.mark.asyncio
async def test_13_thread_list_sorted_by_latest_message(async_client: AsyncClient, db_session: AsyncSession):
    """13. Thread list returns threads ordered by newest activity first (last_message_at DESC)."""
    token = await register_and_login(async_client, "thread_user_13@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 13")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support13@thread.com")

    # Thread 1: Sent earlier
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user13a@example.com"],
                "subject": "Thread One Early",
                "body_text": "Thread 1 content",
            },
        )
    t1_id = r1.json()["thread_id"]

    # Thread 2: Sent later
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r2 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user13b@example.com"],
                "subject": "Thread Two Recent",
                "body_text": "Thread 2 content",
            },
        )
    t2_id = r2.json()["thread_id"]

    # Explicitly ensure t2 last_message_at > t1
    t1_rec = (await db_session.execute(select(EmailThread).where(EmailThread.id == t1_id))).scalars().first()
    t2_rec = (await db_session.execute(select(EmailThread).where(EmailThread.id == t2_id))).scalars().first()
    t1_rec.last_message_at = datetime.now(timezone.utc) - timedelta(hours=2)
    t2_rec.last_message_at = datetime.now(timezone.utc)
    await db_session.commit()

    # Query threads list
    list_resp = await async_client.get(
        "/api/v1/threads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    threads = list_resp.json()["threads"]
    assert len(threads) >= 2
    # Verify newest thread appears first
    thread_ids = [t["id"] for t in threads]
    assert thread_ids.index(t2_id) < thread_ids.index(t1_id)


@pytest.mark.asyncio
async def test_14_cross_company_thread_access_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """14. Cross-company access to threads is strictly rejected with 403 Forbidden."""
    token_a = await register_and_login(async_client, "owner_co_a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support@comp-a.com")

    # Company A creates a thread
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r_a = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "email_account_id": acc_a,
                "to": ["customer@a.com"],
                "subject": "Secret Company A Thread",
                "body_text": "Confidential internal discussion.",
            },
        )
    thread_a_id = r_a.json()["thread_id"]

    # Company B user logs in
    token_b = await register_and_login(async_client, "owner_co_b@test.com")
    await create_company_helper(async_client, token_b, "Company B")

    # Company B user tries to access Company A's thread
    resp = await async_client.get(
        f"/api/v1/threads/{thread_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert "access" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_15_cross_account_thread_attachment_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """15. Outgoing reply cannot attach to a thread belonging to a different email account."""
    token = await register_and_login(async_client, "multi_acc_user@test.com")
    comp_id = await create_company_helper(async_client, token, "Multi Account Co")
    acc_1 = await create_account_helper(async_client, token, comp_id, name="Account 1", email="acc1@multi.com")
    acc_2 = await create_account_helper(async_client, token, comp_id, name="Account 2", email="acc2@multi.com")

    # Send thread in Account 1
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        r1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_1,
                "to": ["client@multi.com"],
                "subject": "Account 1 Thread",
                "body_text": "Originated from account 1",
            },
        )
    thread_1_id = r1.json()["thread_id"]
    msg_1_id = r1.json()["message_id"]

    # Attempt to reply from Account 2 targeting Thread 1
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        reply_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_2,  # Account 2 attempting to reply into Account 1's thread
                "to": ["client@multi.com"],
                "subject": "Re: Account 1 Thread",
                "body_text": "Illegal cross-account reply",
                "thread_id": thread_1_id,
                "in_reply_to": msg_1_id,
            },
        )

    assert reply_resp.status_code == 403
    assert "different email account" in reply_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_16_invalid_nonexistent_thread_id_handled_correctly(async_client: AsyncClient):
    """16. Nonexistent thread IDs return 404 Not Found cleanly."""
    token = await register_and_login(async_client, "thread_404_user@test.com")
    comp_id = await create_company_helper(async_client, token, "404 Co")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support@404.com")

    # GET nonexistent thread
    resp = await async_client.get(
        "/api/v1/threads/9999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404

    # Send email referencing nonexistent thread
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["test@example.com"],
                "subject": "Ghost Thread Reply",
                "body_text": "This should fail",
                "thread_id": 9999999,
            },
        )
    assert send_resp.status_code == 404


@pytest.mark.asyncio
async def test_17_existing_m6_duplicate_imap_sync_still_works(async_client: AsyncClient, db_session: AsyncSession):
    """17. Existing M6 duplicate IMAP synchronization protection continues to function seamlessly with threading."""
    token = await register_and_login(async_client, "thread_user_17@test.com")
    comp_id = await create_company_helper(async_client, token, "Thread Co 17")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support17@thread.com")

    raw_email = make_raw_email(
        msg_id="<dup-test-msg@example.com>",
        subject="Monthly Report",
        from_addr="finance@example.com",
        to_addrs=["support17@thread.com"],
        body="Here is the monthly report.",
    )

    # First sync: 1 new message
    with mock_imap_sync([raw_email], uids=["701"]):
        sync1 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync1.status_code == 200
        assert sync1.json()["new_messages"] == 1
        assert sync1.json()["duplicates_skipped"] == 0

    # Second sync with identical UID: 1 duplicate skipped
    with mock_imap_sync([raw_email], uids=["701"]):
        sync2 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync2.status_code == 200
        assert sync2.json()["new_messages"] == 0
        assert sync2.json()["duplicates_skipped"] == 1

    # Ensure only 1 thread exists and message_count is still 1
    threads = (await db_session.execute(select(EmailThread).where(EmailThread.email_account_id == acc_id))).scalars().all()
    assert len(threads) == 1
    assert threads[0].message_count == 1


@pytest.mark.asyncio
async def test_18_customer_reply_multi_turn_threading_and_draft_persistence(
    async_client: AsyncClient, db_session: AsyncSession
):
    """18. Multi-turn conversation threading:
    - User sends original email -> Thread created (message_count=1)
    - Customer replies via IMAP -> Same thread (message_count=2)
    - User replies directly -> Preserves thread_id and in_reply_to, remains in same thread (message_count=3)
    - Customer replies again via IMAP -> Same thread (message_count=4)
    - User creates reply draft -> Preserves thread_id and in_reply_to
    - User updates and sends reply draft -> Sent email remains in same thread (message_count=5)
    """
    token = await register_and_login(async_client, "thread_multiturn_user@test.com")
    comp_id = await create_company_helper(async_client, token, "MultiTurn Thread Co")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support@multiturn.com")

    # Step 1: User sends original email
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@partner.com"],
                "subject": "Project Proposal Discussion",
                "body_text": "Hi Client, here is our proposal.",
            },
        )
    assert send_1.status_code == 201
    email_1_data = send_1.json()
    thread_id = email_1_data["thread_id"]
    msg_id_1 = email_1_data["message_id"]
    assert thread_id is not None
    assert msg_id_1 is not None

    # Step 2: Customer sends Reply 1 via IMAP sync
    msg_id_2 = "<client-reply-1@partner.com>"
    raw_reply_1 = make_raw_email(
        msg_id=msg_id_2,
        subject="Re: Project Proposal Discussion",
        from_addr="client@partner.com",
        to_addrs=["support@multiturn.com"],
        body="Thanks, could you clarify the timeline?",
        in_reply_to=msg_id_1,
        references=msg_id_1,
    )
    with mock_imap_sync([raw_reply_1], uids=["801"]):
        sync_1 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_1.status_code == 200
        assert sync_1.json()["new_messages"] == 1

    # Verify thread message_count is 2
    thread_resp = await async_client.get(
        f"/api/v1/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thread_resp.status_code == 200
    assert thread_resp.json()["message_count"] == 2

    # Step 3: User replies directly to Customer Reply 1
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_2 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@partner.com"],
                "subject": "Re: Project Proposal Discussion",
                "body_text": "Timeline is 4 weeks.",
                "thread_id": thread_id,
                "in_reply_to": msg_id_2,
            },
        )
    assert send_2.status_code == 201
    email_3_data = send_2.json()
    assert email_3_data["thread_id"] == thread_id
    assert email_3_data["in_reply_to"] == msg_id_2
    msg_id_3 = email_3_data["message_id"]

    # Verify thread message_count is 3
    thread_resp = await async_client.get(
        f"/api/v1/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thread_resp.json()["message_count"] == 3

    # Step 4: Customer sends Reply 2 via IMAP sync
    msg_id_4 = "<client-reply-2@partner.com>"
    raw_reply_2 = make_raw_email(
        msg_id=msg_id_4,
        subject="Re: Project Proposal Discussion",
        from_addr="client@partner.com",
        to_addrs=["support@multiturn.com"],
        body="Got it. What about milestone billing?",
        in_reply_to=msg_id_3,
        references=f"{msg_id_1} {msg_id_2} {msg_id_3}",
    )
    with mock_imap_sync([raw_reply_2], uids=["802"]):
        sync_2 = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_2.status_code == 200
        assert sync_2.json()["new_messages"] == 1

    # Verify thread message_count is 4
    thread_resp = await async_client.get(
        f"/api/v1/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thread_resp.json()["message_count"] == 4

    # Step 5: User creates a reply draft referencing Customer Reply 2
    draft_create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["client@partner.com"],
            "subject": "Re: Project Proposal Discussion",
            "body_text": "Working draft on milestone billing...",
            "thread_id": thread_id,
            "in_reply_to": msg_id_4,
        },
    )
    assert draft_create_resp.status_code == 201
    draft_data = draft_create_resp.json()
    draft_id = draft_data["id"]
    assert draft_data["thread_id"] == thread_id
    assert draft_data["in_reply_to"] == msg_id_4

    # User updates the reply draft
    draft_update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "We support 50/50 milestone billing.",
            "thread_id": thread_id,
            "in_reply_to": msg_id_4,
        },
    )
    assert draft_update_resp.status_code == 200
    assert draft_update_resp.json()["thread_id"] == thread_id
    assert draft_update_resp.json()["in_reply_to"] == msg_id_4

    # User sends the reply draft
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_draft_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert send_draft_resp.status_code == 200
    sent_draft_data = send_draft_resp.json()
    assert sent_draft_data["thread_id"] == thread_id
    assert sent_draft_data["in_reply_to"] == msg_id_4
    assert sent_draft_data["status"] == "SENT"

    # Step 6: Verify final thread state: all 5 messages remain in ONE thread
    final_thread_resp = await async_client.get(
        f"/api/v1/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert final_thread_resp.status_code == 200
    final_thread = final_thread_resp.json()
    assert final_thread["message_count"] == 5
    assert len(final_thread["emails"]) == 5
    assert all(e["thread_id"] == thread_id for e in final_thread["emails"])

