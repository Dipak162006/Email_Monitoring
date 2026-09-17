from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
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
            "provider": "GOOGLE",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "Password123!",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "Password123!",
        },
    )
    return resp.json()["id"]


# =============================================================================
# Dashboard Analytics Tests
# =============================================================================

@pytest.mark.anyio
async def test_empty_dashboard_stats(async_client: AsyncClient):
    """Empty company/workspace returns 0 counts, 0.0 bounce rate, and None for comparison percentages."""
    token = await register_and_login(async_client, "owner_empty@test.com")
    company_id = await create_company_helper(async_client, token, "Empty Co")
    await create_account_helper(async_client, token, company_id)

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent_count"] == 0
    assert data["bounced_count"] == 0
    assert data["response_count"] == 0
    assert data["bounce_rate"] == 0.0
    assert data["sent_change_percent"] is None
    assert data["bounced_change_percent"] is None
    assert data["response_change_percent"] is None


@pytest.mark.anyio
async def test_dashboard_stats_calculations(async_client: AsyncClient, db_session: AsyncSession):
    """Accurately calculates total sent, bounced, customer responses, and bounce rate."""
    token = await register_and_login(async_client, "stats_user@test.com")
    company_id = await create_company_helper(async_client, token, "Metrics Inc")
    account_id = await create_account_helper(async_client, token, company_id)

    now = datetime.now(timezone.utc)

    # 1. Add 10 outgoing sent emails
    for i in range(10):
        db_session.add(
            Email(
                company_id=company_id,
                email_account_id=account_id,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.SENT.value,
                sender="support@testco.com",
                recipients=[f"client{i}@example.com"],
                subject=f"Notice #{i}",
                sent_at=now - timedelta(days=2),
            )
        )

    # 2. Add 2 bounced emails
    for i in range(2):
        db_session.add(
            Email(
                company_id=company_id,
                email_account_id=account_id,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.BOUNCED.value,
                sender="support@testco.com",
                recipients=[f"bad{i}@invalid.domain"],
                subject=f"Failed delivery #{i}",
                sent_at=now - timedelta(days=1),
            )
        )

    # 3. Add 1 conversation thread with has_reply = True and incoming response emails
    thread = EmailThread(
        company_id=company_id,
        email_account_id=account_id,
        subject="Thread with response",
        has_reply=True,
        message_count=2,
        last_message_at=now,
    )
    db_session.add(thread)
    await db_session.flush()

    # Incoming response
    db_session.add(
        Email(
            company_id=company_id,
            email_account_id=account_id,
            thread_id=thread.id,
            direction=EmailDirection.INCOMING.value,
            status=EmailStatus.RECEIVED.value,
            sender="client@example.com",
            recipients=["support@testco.com"],
            subject="Re: Thread with response",
            received_at=now - timedelta(hours=5),
        )
    )

    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["sent_count"] == 10
    assert data["bounced_count"] == 2
    assert data["response_count"] == 1
    # Bounce rate: 2 / 10 * 100 = 20.0%
    assert data["bounce_rate"] == 20.0


@pytest.mark.anyio
async def test_dashboard_stats_previous_period_comparison(async_client: AsyncClient, db_session: AsyncSession):
    """Calculates previous period comparison safely without division by zero errors."""
    token = await register_and_login(async_client, "comp_user@test.com")
    company_id = await create_company_helper(async_client, token, "Compare Corp")
    account_id = await create_account_helper(async_client, token, company_id)

    now = datetime.now(timezone.utc)
    # Current period: last 7 days (now-7d to now)
    # Previous period: now-14d to now-7d

    # 4 sent in previous period
    for i in range(4):
        db_session.add(
            Email(
                company_id=company_id,
                email_account_id=account_id,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.SENT.value,
                sender="support@testco.com",
                recipients=[f"p{i}@example.com"],
                subject=f"Old Sent #{i}",
                sent_at=now - timedelta(days=10),
            )
        )

    # 6 sent in current period
    for i in range(6):
        db_session.add(
            Email(
                company_id=company_id,
                email_account_id=account_id,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.SENT.value,
                sender="support@testco.com",
                recipients=[f"c{i}@example.com"],
                subject=f"Current Sent #{i}",
                sent_at=now - timedelta(days=2),
            )
        )

    await db_session.commit()

    date_from = (now - timedelta(days=7)).isoformat()
    date_to = now.isoformat()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/stats",
        params={"date_from": date_from, "date_to": date_to},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["sent_count"] == 6
    # ((6 - 4) / 4) * 100 = +50.0%
    assert data["sent_change_percent"] == 50.0
    # No bounced in previous or current -> None
    assert data["bounced_change_percent"] is None


@pytest.mark.anyio
async def test_dashboard_multi_tenant_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """User cannot view another company's dashboard statistics or activity data."""
    # User 1 & Company 1
    token_a = await register_and_login(async_client, "user_a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, name="Account A")

    # User 2 & Company 2
    token_b = await register_and_login(async_client, "user_b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Company B")

    # Company A has 5 sent emails
    now = datetime.now(timezone.utc)
    for i in range(5):
        db_session.add(
            Email(
                company_id=comp_a,
                email_account_id=acc_a,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.SENT.value,
                sender="a@test.com",
                recipients=["ext@example.com"],
                subject=f"Msg A #{i}",
                sent_at=now - timedelta(days=1),
            )
        )
    await db_session.commit()

    # User B tries to access Company A stats -> 403 Forbidden
    resp = await async_client.get(
        f"/api/v1/companies/{comp_a}/emails/dashboard/stats",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403

    # User B accessing their own dashboard gets 0
    resp_b = await async_client.get(
        f"/api/v1/companies/{comp_b}/emails/dashboard/stats",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["sent_count"] == 0


@pytest.mark.anyio
async def test_activity_trends_daily_aggregation(async_client: AsyncClient, db_session: AsyncSession):
    """Daily activity trends return complete calendar points with correct volumes."""
    token = await register_and_login(async_client, "activity_user@test.com")
    company_id = await create_company_helper(async_client, token, "Trends Inc")
    account_id = await create_account_helper(async_client, token, company_id)

    now = datetime.now(timezone.utc)
    # Add emails on 2 distinct days
    day_yesterday = now - timedelta(days=1)
    day_3_days_ago = now - timedelta(days=3)

    db_session.add(
        Email(
            company_id=company_id,
            email_account_id=account_id,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.SENT.value,
            sender="trends@test.com",
            recipients=["user@example.com"],
            subject="Recent Dispatch",
            sent_at=day_yesterday,
        )
    )
    db_session.add(
        Email(
            company_id=company_id,
            email_account_id=account_id,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.BOUNCED.value,
            sender="trends@test.com",
            recipients=["bounce@example.com"],
            subject="Delivery Failure",
            sent_at=day_3_days_ago,
        )
    )
    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_sent"] == 1
    assert data["total_bounced"] == 1
    assert data["total_responses"] == 0
    assert len(data["points"]) >= 7  # 7 days default
    # Verify each point has date, label, sent, responses, bounced
    for pt in data["points"]:
        assert "date" in pt
        assert "label" in pt
        assert "sent" in pt
        assert "responses" in pt
        assert "bounced" in pt


@pytest.mark.anyio
async def test_account_health_overview(async_client: AsyncClient, db_session: AsyncSession):
    """Account health returns total accounts, active status, and synced timestamps."""
    token = await register_and_login(async_client, "health_user@test.com")
    company_id = await create_company_helper(async_client, token, "Health Corp")
    account_id = await create_account_helper(async_client, token, company_id, name="Support Mail", email="support@health.com")

    # Update account last_synced_at
    acc = await db_session.get(EmailAccount, account_id)
    now = datetime.now(timezone.utc)
    acc.last_synced_at = now - timedelta(minutes=5)
    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/account-health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_accounts"] == 1
    assert data["active_accounts"] == 1
    assert data["syncing_accounts"] == 0
    assert len(data["accounts"]) == 1
    acc_item = data["accounts"][0]
    assert acc_item["id"] == account_id
    assert acc_item["name"] == "Support Mail"
    assert acc_item["status_label"] == "Operational"
    assert acc_item["last_synced_at"] is not None


@pytest.mark.anyio
async def test_invalid_date_range(async_client: AsyncClient):
    """Supplying date_from after date_to returns a 400 Bad Request."""
    token = await register_and_login(async_client, "invalid_range@test.com")
    company_id = await create_company_helper(async_client, token, "Range Co")

    now = datetime.now(timezone.utc)
    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/emails/dashboard/stats",
        params={
            "date_from": now.isoformat(),
            "date_to": (now - timedelta(days=5)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "date_from cannot be later than date_to" in resp.json()["detail"]
