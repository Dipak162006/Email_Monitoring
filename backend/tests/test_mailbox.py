from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread


# =============================================================================
# Test Setup Helpers
# =============================================================================

async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and log in a user, returning access token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Test Co") -> int:
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
    name: str = "Support",
    email: str = "support@testco.com",
) -> int:
    """Create an EmailAccount and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.testco.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "Password123!",
            "imap_host": "imap.testco.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "Password123!",
        },
    )
    return resp.json()["id"]


async def create_email_record(
    db: AsyncSession,
    company_id: int,
    email_account_id: int,
    direction: str = EmailDirection.INCOMING.value,
    status: str = EmailStatus.RECEIVED.value,
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    recipients: list = None,
    is_read: bool = False,
    is_starred: bool = False,
    is_deleted: bool = False,
    deleted_at: datetime = None,
    thread_id: int = None,
    sent_at: datetime = None,
    received_at: datetime = None,
    body_text: str = "Test body",
) -> Email:
    """Insert an Email record directly for test setup."""
    email = Email(
        company_id=company_id,
        email_account_id=email_account_id,
        direction=direction,
        status=status,
        subject=subject,
        sender=sender,
        recipients=recipients or ["recipient@example.com"],
        is_read=is_read,
        is_starred=is_starred,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
        thread_id=thread_id,
        sent_at=sent_at,
        received_at=received_at,
        body_text=body_text,
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)
    return email


async def create_thread_record(
    db: AsyncSession,
    company_id: int,
    email_account_id: int,
    subject: str = "Test Thread",
    has_reply: bool = False,
    is_read: bool = False,
    message_count: int = 1,
) -> EmailThread:
    """Insert an EmailThread record directly for test setup."""
    thread = EmailThread(
        company_id=company_id,
        email_account_id=email_account_id,
        subject=subject,
        has_reply=has_reply,
        is_read=is_read,
        message_count=message_count,
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


# =============================================================================
# Milestone M8 Test Cases
# =============================================================================

@pytest.mark.asyncio
async def test_01_inbox_listing_returns_only_incoming_received(async_client: AsyncClient, db_session: AsyncSession):
    """1. Inbox listing returns only incoming received emails (is_deleted=False)."""
    token = await register_and_login(async_client, "user01@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 01")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support01@test.com")

    # Incoming Received -> should appear in inbox
    e1 = await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", subject="Inbox Email")
    # Outgoing Sent -> should NOT appear in inbox
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", subject="Sent Email")
    # Incoming Bounced -> should NOT appear in inbox
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="BOUNCED", subject="Bounced Email")
    # Incoming Trashed -> should NOT appear in inbox
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", is_deleted=True, subject="Deleted Inbox Email")

    resp = await async_client.get(
        "/api/v1/emails?folder=inbox",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e1.id
    assert data["emails"][0]["subject"] == "Inbox Email"


@pytest.mark.asyncio
async def test_02_sent_listing_returns_only_outgoing_sent(async_client: AsyncClient, db_session: AsyncSession):
    """2. Sent listing returns only outgoing sent emails."""
    token = await register_and_login(async_client, "user02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 02")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support02@test.com")

    e_sent = await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", subject="Sent Message")
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", subject="Incoming Message")
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="DRAFT", subject="Draft Message")
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", is_deleted=True, subject="Deleted Sent")

    resp = await async_client.get(
        "/api/v1/emails?folder=sent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_sent.id
    assert data["emails"][0]["subject"] == "Sent Message"


@pytest.mark.asyncio
async def test_03_draft_listing_works_without_draft_creation_endpoint(async_client: AsyncClient, db_session: AsyncSession):
    """3. Draft listing works even though no draft creation endpoint exists."""
    token = await register_and_login(async_client, "user03@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 03")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support03@test.com")

    e_draft = await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="DRAFT", subject="Unsent Draft")
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", subject="Sent Email")

    resp = await async_client.get(
        "/api/v1/emails?folder=drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_draft.id
    assert data["emails"][0]["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_04_bounced_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """4. Bounced filter returns emails with status=BOUNCED and is_deleted=False."""
    token = await register_and_login(async_client, "user04@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 04")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support04@test.com")

    e_bounced = await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="BOUNCED", subject="Delivery Failed")
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", subject="Delivered")
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="BOUNCED", is_deleted=True, subject="Deleted Bounced")

    resp = await async_client.get(
        "/api/v1/emails?folder=bounced",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_bounced.id
    assert data["emails"][0]["status"] == "BOUNCED"


@pytest.mark.asyncio
async def test_05_responses_filter_returns_incoming_emails_in_replied_threads(async_client: AsyncClient, db_session: AsyncSession):
    """5. Responses filter returns incoming emails belonging to threads with has_reply=True."""
    token = await register_and_login(async_client, "user05@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 05")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support05@test.com")

    # Thread A has a reply
    t_replied = await create_thread_record(db_session, comp_id, acc_id, subject="Replied Thread", has_reply=True)
    # Thread B does NOT have a reply
    t_no_reply = await create_thread_record(db_session, comp_id, acc_id, subject="Solo Thread", has_reply=False)

    # Incoming email in replied thread -> should appear in responses
    e_resp = await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", thread_id=t_replied.id, subject="Re: Replied Thread")
    # Outgoing email in replied thread -> should NOT appear
    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT", thread_id=t_replied.id, subject="Original Thread")
    # Incoming email in non-replied thread -> should NOT appear
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", thread_id=t_no_reply.id, subject="Solo Inbound")

    resp = await async_client.get(
        "/api/v1/emails?folder=responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_resp.id
    assert data["emails"][0]["direction"] == "INCOMING"


@pytest.mark.asyncio
async def test_06_trash_listing_returns_soft_deleted_emails(async_client: AsyncClient, db_session: AsyncSession):
    """6. Trash listing returns soft-deleted emails."""
    token = await register_and_login(async_client, "user06@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 06")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support06@test.com")

    now = datetime.now(timezone.utc)
    e_trashed = await create_email_record(db_session, comp_id, acc_id, is_deleted=True, deleted_at=now, subject="Trashed Mail")
    await create_email_record(db_session, comp_id, acc_id, is_deleted=False, subject="Active Mail")

    resp = await async_client.get(
        "/api/v1/emails?folder=trash",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_trashed.id
    assert data["emails"][0]["is_deleted"] is True
    assert data["emails"][0]["deleted_at"] is not None


@pytest.mark.asyncio
async def test_07_folder_plus_additional_filter_uses_and_semantics(async_client: AsyncClient, db_session: AsyncSession):
    """7. Folder shorthand combines with additional filters using strict AND semantics."""
    token = await register_and_login(async_client, "user07@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 07")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support07@test.com")

    # Inbox Read
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", is_read=True, subject="Inbox Read")
    # Inbox Unread
    e_unread = await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", is_read=False, subject="Inbox Unread")

    # Query folder=inbox AND is_read=false
    resp = await async_client.get(
        "/api/v1/emails?folder=inbox&is_read=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_unread.id

    # Query folder=inbox AND direction=OUTGOING -> contradictory filter should return 0 results
    resp_contradict = await async_client.get(
        "/api/v1/emails?folder=inbox&direction=OUTGOING",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_contradict.status_code == 200
    assert resp_contradict.json()["total"] == 0


@pytest.mark.asyncio
async def test_08_raw_status_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """8. Raw status filter works."""
    token = await register_and_login(async_client, "user08@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 08")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support08@test.com")

    await create_email_record(db_session, comp_id, acc_id, status="SENT", subject="Sent 1")
    await create_email_record(db_session, comp_id, acc_id, status="FAILED", subject="Failed 1")

    resp = await async_client.get(
        "/api/v1/emails?status=FAILED",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_09_raw_direction_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """9. Raw direction filter works."""
    token = await register_and_login(async_client, "user09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 09")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support09@test.com")

    await create_email_record(db_session, comp_id, acc_id, direction="OUTGOING", status="SENT")
    await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED")

    resp = await async_client.get(
        "/api/v1/emails?direction=OUTGOING",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["direction"] == "OUTGOING"


@pytest.mark.asyncio
async def test_10_account_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """10. Account filter works."""
    token = await register_and_login(async_client, "user10@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 10")
    acc1 = await create_account_helper(async_client, token, comp_id, name="Acc 1", email="acc1@test.com")
    acc2 = await create_account_helper(async_client, token, comp_id, name="Acc 2", email="acc2@test.com")

    e1 = await create_email_record(db_session, comp_id, acc1, subject="Email on Acc 1")
    await create_email_record(db_session, comp_id, acc2, subject="Email on Acc 2")

    resp = await async_client.get(
        f"/api/v1/emails?email_account_id={acc1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e1.id


@pytest.mark.asyncio
async def test_11_read_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """11. Read filter works."""
    token = await register_and_login(async_client, "user11@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 11")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support11@test.com")

    await create_email_record(db_session, comp_id, acc_id, is_read=True, subject="Read Email")
    await create_email_record(db_session, comp_id, acc_id, is_read=False, subject="Unread Email")

    resp_read = await async_client.get("/api/v1/emails?is_read=true", headers={"Authorization": f"Bearer {token}"})
    assert resp_read.status_code == 200
    assert resp_read.json()["total"] == 1
    assert resp_read.json()["emails"][0]["is_read"] is True

    resp_unread = await async_client.get("/api/v1/emails?is_read=false", headers={"Authorization": f"Bearer {token}"})
    assert resp_unread.status_code == 200
    assert resp_unread.json()["total"] == 1
    assert resp_unread.json()["emails"][0]["is_read"] is False


@pytest.mark.asyncio
async def test_12_starred_filter_works(async_client: AsyncClient, db_session: AsyncSession):
    """12. Starred filter works."""
    token = await register_and_login(async_client, "user12@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 12")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support12@test.com")

    await create_email_record(db_session, comp_id, acc_id, is_starred=True, subject="Starred Note")
    await create_email_record(db_session, comp_id, acc_id, is_starred=False, subject="Unstarred Note")

    resp_starred = await async_client.get("/api/v1/emails?is_starred=true", headers={"Authorization": f"Bearer {token}"})
    assert resp_starred.status_code == 200
    assert resp_starred.json()["total"] == 1
    assert resp_starred.json()["emails"][0]["is_starred"] is True


@pytest.mark.asyncio
async def test_13_search_matches_subject(async_client: AsyncClient, db_session: AsyncSession):
    """13. Search matches subject case-insensitively."""
    token = await register_and_login(async_client, "user13@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 13")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support13@test.com")

    e_match = await create_email_record(db_session, comp_id, acc_id, subject="Urgent: Invoice #9988 payment due")
    await create_email_record(db_session, comp_id, acc_id, subject="Team picnic this weekend")

    resp = await async_client.get("/api/v1/emails?search=invoice", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_match.id


@pytest.mark.asyncio
async def test_14_search_matches_sender(async_client: AsyncClient, db_session: AsyncSession):
    """14. Search matches sender case-insensitively."""
    token = await register_and_login(async_client, "user14@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 14")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support14@test.com")

    e_match = await create_email_record(db_session, comp_id, acc_id, sender="billing.dept@supplier.com", subject="Statement")
    await create_email_record(db_session, comp_id, acc_id, sender="marketing@newsletter.com", subject="Updates")

    resp = await async_client.get("/api/v1/emails?search=BILLING", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_match.id


@pytest.mark.asyncio
async def test_15_date_range_filtering_works(async_client: AsyncClient, db_session: AsyncSession):
    """15. Date range filtering works."""
    token = await register_and_login(async_client, "user15@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 15")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support15@test.com")

    base = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    t_past = base - timedelta(days=5)
    t_target = base
    t_future = base + timedelta(days=5)

    await create_email_record(db_session, comp_id, acc_id, received_at=t_past, subject="Old")
    e_mid = await create_email_record(db_session, comp_id, acc_id, received_at=t_target, subject="Target")
    await create_email_record(db_session, comp_id, acc_id, received_at=t_future, subject="Future")

    date_from = (base - timedelta(days=1)).isoformat()
    date_to = (base + timedelta(days=1)).isoformat()

    resp = await async_client.get(
        "/api/v1/emails",
        params={"date_from": date_from, "date_to": date_to},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["emails"][0]["id"] == e_mid.id


@pytest.mark.asyncio
async def test_16_newest_sorting_works(async_client: AsyncClient, db_session: AsyncSession):
    """16. Newest sorting works (default and explicit sort=newest)."""
    token = await register_and_login(async_client, "user16@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 16")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support16@test.com")

    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)

    e_older = await create_email_record(db_session, comp_id, acc_id, received_at=t1, subject="Older")
    e_newer = await create_email_record(db_session, comp_id, acc_id, received_at=t2, subject="Newer")

    resp = await async_client.get("/api/v1/emails?sort=newest", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = resp.json()["emails"]
    assert emails[0]["id"] == e_newer.id
    assert emails[1]["id"] == e_older.id


@pytest.mark.asyncio
async def test_17_oldest_sorting_works(async_client: AsyncClient, db_session: AsyncSession):
    """17. Oldest sorting works."""
    token = await register_and_login(async_client, "user17@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 17")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support17@test.com")

    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)

    e_older = await create_email_record(db_session, comp_id, acc_id, received_at=t1, subject="Older")
    e_newer = await create_email_record(db_session, comp_id, acc_id, received_at=t2, subject="Newer")

    resp = await async_client.get("/api/v1/emails?sort=oldest", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = resp.json()["emails"]
    assert emails[0]["id"] == e_older.id
    assert emails[1]["id"] == e_newer.id


@pytest.mark.asyncio
async def test_18_pagination_works(async_client: AsyncClient, db_session: AsyncSession):
    """18. Pagination works (limit and offset)."""
    token = await register_and_login(async_client, "user18@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 18")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support18@test.com")

    # Create 5 emails
    for i in range(5):
        await create_email_record(
            db_session, comp_id, acc_id,
            received_at=datetime(2026, 9, 1, i, 0, 0, tzinfo=timezone.utc),
            subject=f"Item {i}",
        )

    resp_p1 = await async_client.get("/api/v1/emails?limit=2&offset=0&sort=oldest", headers={"Authorization": f"Bearer {token}"})
    assert resp_p1.status_code == 200
    d1 = resp_p1.json()
    assert d1["total"] == 5
    assert len(d1["emails"]) == 2
    assert d1["emails"][0]["subject"] == "Item 0"
    assert d1["emails"][1]["subject"] == "Item 1"

    resp_p2 = await async_client.get("/api/v1/emails?limit=2&offset=2&sort=oldest", headers={"Authorization": f"Bearer {token}"})
    assert resp_p2.status_code == 200
    d2 = resp_p2.json()
    assert len(d2["emails"]) == 2
    assert d2["emails"][0]["subject"] == "Item 2"
    assert d2["emails"][1]["subject"] == "Item 3"


@pytest.mark.asyncio
async def test_19_mark_email_read(async_client: AsyncClient, db_session: AsyncSession):
    """19. Mark email read."""
    token = await register_and_login(async_client, "user19@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 19")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support19@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_read=False)

    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_read": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    # Verify DB
    await db_session.refresh(e)
    assert e.is_read is True


@pytest.mark.asyncio
async def test_20_mark_email_unread(async_client: AsyncClient, db_session: AsyncSession):
    """20. Mark email unread."""
    token = await register_and_login(async_client, "user20@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 20")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support20@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_read=True)

    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_read": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_read"] is False

    await db_session.refresh(e)
    assert e.is_read is False


@pytest.mark.asyncio
async def test_21_thread_is_read_becomes_true_when_no_unread_remain(async_client: AsyncClient, db_session: AsyncSession):
    """21. Thread.is_read becomes True when no unread emails remain."""
    token = await register_and_login(async_client, "user21@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 21")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support21@test.com")

    thread = await create_thread_record(db_session, comp_id, acc_id, is_read=False, message_count=2)
    e1 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=True)
    e2 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=False)

    # Mark the only unread email as read
    resp = await async_client.patch(
        f"/api/v1/emails/{e2.id}/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_read": True},
    )
    assert resp.status_code == 200

    # Thread should now be recalculated to is_read=True
    await db_session.refresh(thread)
    assert thread.is_read is True


@pytest.mark.asyncio
async def test_22_thread_is_read_remains_false_when_another_unread_remains(async_client: AsyncClient, db_session: AsyncSession):
    """22. Thread.is_read remains False when another unread email remains."""
    token = await register_and_login(async_client, "user22@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 22")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support22@test.com")

    thread = await create_thread_record(db_session, comp_id, acc_id, is_read=False, message_count=2)
    e1 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=False)
    e2 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=False)

    # Mark e1 as read; e2 is still unread
    resp = await async_client.patch(
        f"/api/v1/emails/{e1.id}/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_read": True},
    )
    assert resp.status_code == 200

    await db_session.refresh(thread)
    assert thread.is_read is False


@pytest.mark.asyncio
async def test_23_mark_email_starred(async_client: AsyncClient, db_session: AsyncSession):
    """23. Mark email starred."""
    token = await register_and_login(async_client, "user23@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 23")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support23@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_starred=False)

    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/star",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_starred": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_starred"] is True

    await db_session.refresh(e)
    assert e.is_starred is True


@pytest.mark.asyncio
async def test_24_unstar_email(async_client: AsyncClient, db_session: AsyncSession):
    """24. Unstar email."""
    token = await register_and_login(async_client, "user24@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 24")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support24@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_starred=True)

    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/star",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_starred": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_starred"] is False

    await db_session.refresh(e)
    assert e.is_starred is False


@pytest.mark.asyncio
async def test_25_soft_delete_moves_email_to_trash(async_client: AsyncClient, db_session: AsyncSession):
    """25. Soft delete moves email to Trash."""
    token = await register_and_login(async_client, "user25@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 25")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support25@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_deleted=False)

    resp = await async_client.delete(
        f"/api/v1/emails/{e.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_deleted"] is True
    assert data["deleted_at"] is not None

    await db_session.refresh(e)
    assert e.is_deleted is True
    assert e.deleted_at is not None


@pytest.mark.asyncio
async def test_26_soft_deleted_email_disappears_from_normal_folders(async_client: AsyncClient, db_session: AsyncSession):
    """26. Soft-deleted email disappears from normal folders (inbox, sent, etc.)."""
    token = await register_and_login(async_client, "user26@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 26")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support26@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, direction="INCOMING", status="RECEIVED", is_deleted=False)

    # Initial check: in inbox
    resp_before = await async_client.get("/api/v1/emails?folder=inbox", headers={"Authorization": f"Bearer {token}"})
    assert resp_before.json()["total"] == 1

    # Soft delete
    await async_client.delete(f"/api/v1/emails/{e.id}", headers={"Authorization": f"Bearer {token}"})

    # Now disappears from inbox
    resp_inbox = await async_client.get("/api/v1/emails?folder=inbox", headers={"Authorization": f"Bearer {token}"})
    assert resp_inbox.json()["total"] == 0

    # Appears in trash
    resp_trash = await async_client.get("/api/v1/emails?folder=trash", headers={"Authorization": f"Bearer {token}"})
    assert resp_trash.json()["total"] == 1
    assert resp_trash.json()["emails"][0]["id"] == e.id


@pytest.mark.asyncio
async def test_27_restore_returns_email_to_normal_folder(async_client: AsyncClient, db_session: AsyncSession):
    """27. Restore returns email to its normal folder."""
    token = await register_and_login(async_client, "user27@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 27")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support27@test.com")

    now = datetime.now(timezone.utc)
    e = await create_email_record(
        db_session, comp_id, acc_id,
        direction="INCOMING", status="RECEIVED",
        is_deleted=True, deleted_at=now,
    )

    # Restore
    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_deleted"] is False
    assert data["deleted_at"] is None

    # Should be back in inbox
    resp_inbox = await async_client.get("/api/v1/emails?folder=inbox", headers={"Authorization": f"Bearer {token}"})
    assert resp_inbox.json()["total"] == 1
    assert resp_inbox.json()["emails"][0]["id"] == e.id


@pytest.mark.asyncio
async def test_28_permanent_delete_removes_trashed_email(async_client: AsyncClient, db_session: AsyncSession):
    """28. Permanent delete removes a trashed email from the database."""
    token = await register_and_login(async_client, "user28@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 28")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support28@test.com")

    now = datetime.now(timezone.utc)
    e = await create_email_record(db_session, comp_id, acc_id, is_deleted=True, deleted_at=now)
    target_id = e.id

    resp = await async_client.delete(
        f"/api/v1/emails/{target_id}/permanent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == target_id

    # Check database: record is permanently deleted
    check_stmt = select(Email).where(Email.id == target_id)
    check_res = await db_session.execute(check_stmt)
    assert check_res.scalars().first() is None


@pytest.mark.asyncio
async def test_29_permanent_delete_rejects_non_trashed_email(async_client: AsyncClient, db_session: AsyncSession):
    """29. Permanent delete rejects an email that is not in Trash."""
    token = await register_and_login(async_client, "user29@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 29")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support29@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_deleted=False)

    resp = await async_client.delete(
        f"/api/v1/emails/{e.id}/permanent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "in trash" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_30_unauthorized_user_cannot_read_another_company_email(async_client: AsyncClient, db_session: AsyncSession):
    """30. Unauthorized user cannot read another company's email."""
    token_a = await register_and_login(async_client, "user30a@companyA.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support@compA.com")
    email_a = await create_email_record(db_session, comp_a, acc_a, subject="Company A Secret")

    token_b = await register_and_login(async_client, "user30b@companyB.com")
    await create_company_helper(async_client, token_b, "Company B")

    # User B tries to view Company A's email
    resp = await async_client.get(
        f"/api/v1/emails/{email_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_31_unauthorized_user_cannot_modify_another_company_email(async_client: AsyncClient, db_session: AsyncSession):
    """31. Unauthorized user cannot modify another company's email (read/star/delete/restore/permanent)."""
    token_a = await register_and_login(async_client, "user31a@companyA.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support@compA.com")
    email_a = await create_email_record(db_session, comp_a, acc_a, subject="Protected Email")

    token_b = await register_and_login(async_client, "user31b@companyB.com")
    await create_company_helper(async_client, token_b, "Company B")

    # Try read toggle
    r1 = await async_client.patch(f"/api/v1/emails/{email_a.id}/read", headers={"Authorization": f"Bearer {token_b}"}, json={"is_read": True})
    assert r1.status_code == 403

    # Try star toggle
    r2 = await async_client.patch(f"/api/v1/emails/{email_a.id}/star", headers={"Authorization": f"Bearer {token_b}"}, json={"is_starred": True})
    assert r2.status_code == 403

    # Try soft delete
    r3 = await async_client.delete(f"/api/v1/emails/{email_a.id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r3.status_code == 403

    # Try restore
    r4 = await async_client.patch(f"/api/v1/emails/{email_a.id}/restore", headers={"Authorization": f"Bearer {token_b}"})
    assert r4.status_code == 403

    # Try permanent delete
    r5 = await async_client.delete(f"/api/v1/emails/{email_a.id}/permanent", headers={"Authorization": f"Bearer {token_b}"})
    assert r5.status_code == 403


@pytest.mark.asyncio
async def test_32_member_can_only_access_granted_email_accounts(async_client: AsyncClient, db_session: AsyncSession):
    """32. Member can only access explicitly granted email accounts."""
    token_owner = await register_and_login(async_client, "owner32@company.com")
    comp_id = await create_company_helper(async_client, token_owner, "Co 32")
    acc_granted = await create_account_helper(async_client, token_owner, comp_id, name="Public Support", email="public@co32.com")
    acc_restricted = await create_account_helper(async_client, token_owner, comp_id, name="Executive", email="exec@co32.com")

    e_granted = await create_email_record(db_session, comp_id, acc_granted, subject="Public Question")
    e_restricted = await create_email_record(db_session, comp_id, acc_restricted, subject="Executive Confidential")

    # Register member and add to company with role MEMBER
    token_member = await register_and_login(async_client, "member32@company.com")
    member_info = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_member}"})).json()
    member_id = member_info["id"]

    add_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "member32@company.com", "role": "MEMBER"},
    )
    assert add_resp.status_code == 201

    # Before grant: member cannot view or list either account
    r_list_init = await async_client.get("/api/v1/emails", headers={"Authorization": f"Bearer {token_member}"})
    assert r_list_init.status_code == 200
    assert r_list_init.json()["total"] == 0

    # Grant access ONLY to acc_granted
    grant_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_granted}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": member_id},
    )
    assert grant_resp.status_code == 201

    # Now member sees e_granted but NOT e_restricted
    r_list_after = await async_client.get("/api/v1/emails", headers={"Authorization": f"Bearer {token_member}"})
    assert r_list_after.status_code == 200
    assert r_list_after.json()["total"] == 1
    assert r_list_after.json()["emails"][0]["id"] == e_granted.id

    # Detail view of granted email works
    r_detail_ok = await async_client.get(f"/api/v1/emails/{e_granted.id}", headers={"Authorization": f"Bearer {token_member}"})
    assert r_detail_ok.status_code == 200

    # Detail view of restricted email fails with 403
    r_detail_forbid = await async_client.get(f"/api/v1/emails/{e_restricted.id}", headers={"Authorization": f"Bearer {token_member}"})
    assert r_detail_forbid.status_code == 403


@pytest.mark.asyncio
async def test_33_cross_company_access_is_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """33. Cross-company access is rejected on company-scoped endpoints."""
    token_a = await register_and_login(async_client, "user33a@compA.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")

    token_b = await register_and_login(async_client, "user33b@compB.com")
    await create_company_helper(async_client, token_b, "Company B")

    # User B tries to query company A's emails endpoint
    resp = await async_client.get(
        f"/api/v1/companies/{comp_a}/emails",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert "do not belong" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_34_existing_m7_thread_integrity_remains_correct(async_client: AsyncClient, db_session: AsyncSession):
    """34. Existing M7 thread integrity remains correct after mailbox operations."""
    token = await register_and_login(async_client, "user34@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 34")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support34@test.com")

    thread = await create_thread_record(db_session, comp_id, acc_id, subject="Project Alpha", message_count=2, is_read=False)
    e1 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=False, subject="Email 1")
    e2 = await create_email_record(db_session, comp_id, acc_id, thread_id=thread.id, is_read=False, subject="Email 2")

    # Soft delete e1
    del_resp = await async_client.delete(f"/api/v1/emails/{e1.id}", headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 200

    # Thread should still exist, message_count preserved (historical message count)
    await db_session.refresh(thread)
    assert thread.message_count == 2
    # e2 is still unread, so thread remains is_read=False
    assert thread.is_read is False

    # Mark e2 read
    await async_client.patch(f"/api/v1/emails/{e2.id}/read", headers={"Authorization": f"Bearer {token}"}, json={"is_read": True})
    await db_session.refresh(thread)
    # Since e1 is in Trash and e2 is Read, active unread messages = 0 -> thread is_read becomes True
    assert thread.is_read is True


@pytest.mark.asyncio
async def test_35_invalid_folder_returns_400(async_client: AsyncClient, db_session: AsyncSession):
    """35. Invalid folder parameter returns 400 Bad Request."""
    token = await register_and_login(async_client, "user35@test.com")
    await create_company_helper(async_client, token, "Co 35")

    resp = await async_client.get(
        "/api/v1/emails?folder=invalid_folder_name",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Invalid folder" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_36_restore_non_trashed_email_returns_400(async_client: AsyncClient, db_session: AsyncSession):
    """36. Restoring an email that is not in trash returns 400 Bad Request."""
    token = await register_and_login(async_client, "user36@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 36")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support36@test.com")

    e = await create_email_record(db_session, comp_id, acc_id, is_deleted=False)

    resp = await async_client.patch(
        f"/api/v1/emails/{e.id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "not in trash" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_37_nonexistent_email_returns_404(async_client: AsyncClient, db_session: AsyncSession):
    """37. Operations on nonexistent email IDs return 404 Not Found."""
    token = await register_and_login(async_client, "user37@test.com")
    await create_company_helper(async_client, token, "Co 37")

    r1 = await async_client.get("/api/v1/emails/999999", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 404

    r2 = await async_client.patch("/api/v1/emails/999999/read", headers={"Authorization": f"Bearer {token}"}, json={"is_read": True})
    assert r2.status_code == 404

    r3 = await async_client.patch("/api/v1/emails/999999/star", headers={"Authorization": f"Bearer {token}"}, json={"is_starred": True})
    assert r3.status_code == 404

    r4 = await async_client.delete("/api/v1/emails/999999", headers={"Authorization": f"Bearer {token}"})
    assert r4.status_code == 404

    r5 = await async_client.patch("/api/v1/emails/999999/restore", headers={"Authorization": f"Bearer {token}"})
    assert r5.status_code == 404

    r6 = await async_client.delete("/api/v1/emails/999999/permanent", headers={"Authorization": f"Bearer {token}"})
    assert r6.status_code == 404


@pytest.mark.asyncio
async def test_38_mailbox_counts_endpoint(async_client: AsyncClient, db_session: AsyncSession):
    """38. GET /api/v1/emails/counts returns accurate counts across all mailbox folders."""
    token = await register_and_login(async_client, "user38@test.com")
    comp_id = await create_company_helper(async_client, token, "Co 38")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support38@test.com")

    # 1. Inbox unread email
    await create_email_record(db_session, comp_id, acc_id, is_read=False, is_deleted=False)
    # 2. Inbox read email
    await create_email_record(db_session, comp_id, acc_id, is_read=True, is_deleted=False)
    # 3. Sent email
    await create_email_record(
        db_session, comp_id, acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        is_deleted=False,
    )
    # 4. Bounced email
    await create_email_record(
        db_session, comp_id, acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.BOUNCED.value,
        is_deleted=False,
    )
    # 5. Soft-deleted (Trash) email
    await create_email_record(
        db_session, comp_id, acc_id,
        is_deleted=True,
        is_read=False,  # Should not be counted in unread
    )
    # 6. Response email (incoming in thread with has_reply=True)
    th = await create_thread_record(db_session, comp_id, acc_id, has_reply=True)
    await create_email_record(
        db_session, comp_id, acc_id,
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        thread_id=th.id,
        is_read=True,
        is_deleted=False,
    )

    resp = await async_client.get(
        "/api/v1/emails/counts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inbox"] == 3       # 2 regular incoming + 1 response incoming
    assert data["unread"] == 1      # Only the active non-deleted unread email
    assert data["sent"] == 1
    assert data["drafts"] == 0
    assert data["bounced"] == 1
    assert data["responses"] == 1
    assert data["trash"] == 1


@pytest.mark.asyncio
async def test_39_mailbox_counts_company_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """39. GET /api/v1/emails/counts respects multi-tenant company isolation."""
    # Company A setup
    token_a = await register_and_login(async_client, "user39a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Co 39A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support39a@test.com")
    await create_email_record(db_session, comp_a, acc_a, is_read=False)

    # Company B setup
    token_b = await register_and_login(async_client, "user39b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Co 39B")
    acc_b = await create_account_helper(async_client, token_b, comp_b, email="support39b@test.com")

    # Co B sees 0 emails
    resp_b = await async_client.get(
        "/api/v1/emails/counts",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["inbox"] == 0
    assert resp_b.json()["unread"] == 0

    # Co A sees 1 email
    resp_a = await async_client.get(
        "/api/v1/emails/counts",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["inbox"] == 1
    assert resp_a.json()["unread"] == 1


@pytest.mark.asyncio
async def test_40_mailbox_list_attachment_count(async_client: AsyncClient, db_session: AsyncSession):
    """40. GET /api/v1/emails correctly returns attachment_count for emails with/without attachments."""
    from app.modules.emails.models import EmailAttachment

    token = await register_and_login(async_client, "user40@test.com")
    comp = await create_company_helper(async_client, token, "Co 40")
    acc = await create_account_helper(async_client, token, comp, email="user40@testco.com")

    # Email 1: No attachments
    e1 = await create_email_record(db_session, comp, acc, subject="No Attachment")

    # Email 2: Has 2 attachments
    e2 = await create_email_record(db_session, comp, acc, subject="With Attachments")
    att1 = EmailAttachment(
        company_id=comp,
        email_account_id=acc,
        email_id=e2.id,
        file_name="report.pdf",
        content_type="application/pdf",
        file_size=1024,
        storage_path="mock/path/report.pdf",
    )
    att2 = EmailAttachment(
        company_id=comp,
        email_account_id=acc,
        email_id=e2.id,
        file_name="data.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size=2048,
        storage_path="mock/path/data.xlsx",
    )
    db_session.add_all([att1, att2])
    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{comp}/emails",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["emails"]) == 2

    # Map by subject to check attachment_count
    counts_by_subj = {e["subject"]: e["attachment_count"] for e in data["emails"]}
    assert counts_by_subj["No Attachment"] == 0
    assert counts_by_subj["With Attachments"] == 2


