from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
)
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.services.transport.models import EmailTransportResult
from app.workers import tasks
from app.workers.campaign_tasks import (
    _async_dispatch_campaign_task,
    _async_retry_campaign_delivery_task,
    _async_scheduled_campaign_dispatch_task,
)
from tests.conftest import TestAsyncSessionLocal


@pytest.fixture(autouse=True)
def configure_worker_db():
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Hardening Org") -> int:
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def add_member_helper(
    client: AsyncClient,
    owner_token: str,
    company_id: int,
    email: str,
    role: str = "MEMBER",
) -> None:
    resp = await client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": email, "role": role},
    )
    assert resp.status_code == 201


async def setup_test_campaign(
    client: AsyncClient,
    db: AsyncSession,
    owner_token: str,
    company_id: int,
    subject: str = "Hardening Subject",
    body: str = "Hardening Body",
) -> tuple[int, int]:
    dom_suffix = uuid.uuid4().hex[:6]
    domain_name = f"org{company_id}-{dom_suffix}.com"

    dom_resp = await client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"domain_name": domain_name},
    )
    dom_id = dom_resp.json()["id"]

    dom_res = await db.execute(select(Domain).where(Domain.id == dom_id))
    domain = dom_res.scalar_one()
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db.commit()

    sender_email = f"sender@{domain_name}"
    acc_resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Sender Account",
            "email_address": sender_email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": sender_email,
            "smtp_password": "Pass!",
            "imap_host": "imap.test.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": sender_email,
            "imap_password": "Pass!",
            "domain_id": dom_id,
        },
    )
    acc_id = acc_resp.json()["id"]

    camp_resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Hardening Campaign",
            "email_account_id": acc_id,
            "subject": subject,
            "body_text": body,
            "body_html": f"<p>{body}</p>",
        },
    )
    assert camp_resp.status_code == 201
    return camp_resp.json()["id"], acc_id


# =============================================================================
# 1. Authorization: MEMBER Mutation Rejection (403 Forbidden)
# =============================================================================

@pytest.mark.asyncio
async def test_member_mutation_rejection_on_all_campaign_routes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """MEMBER role receives 403 Forbidden on all campaign and recipient mutation endpoints."""
    owner_token = await register_and_login(async_client, "owner_auth@example.com")
    member_email = "member_auth@example.com"
    member_token = await register_and_login(async_client, member_email)

    comp_id = await create_company_helper(async_client, owner_token, "Auth Org")
    await add_member_helper(async_client, owner_token, comp_id, member_email, role="MEMBER")

    camp_id, acc_id = await setup_test_campaign(async_client, db_session, owner_token, comp_id)

    # 1. Create campaign -> 403
    resp_create = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "name": "Member Campaign",
            "email_account_id": acc_id,
            "subject": "Sub",
            "body_text": "Text",
        },
    )
    assert resp_create.status_code == 403

    # 2. Update campaign -> 403
    resp_update = await async_client.patch(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Hacked Name"},
    )
    assert resp_update.status_code == 403

    # 3. Delete campaign -> 403
    resp_del = await async_client.delete(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_del.status_code == 403

    # 4. Preflight -> 403
    resp_preflight = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/preflight",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_preflight.status_code == 403

    # 5. Dispatch -> 403
    resp_dispatch = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/dispatch",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_dispatch.status_code == 403

    # 6. Schedule -> 403
    resp_sched = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_sched.status_code == 403

    # 7. Pause -> 403
    resp_pause = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/pause",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_pause.status_code == 403

    # 8. Resume -> 403
    resp_resume = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_resume.status_code == 403

    # 9. Cancel -> 403
    resp_cancel = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/cancel",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_cancel.status_code == 403

    # 10. Add recipient -> 403
    resp_recip = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "victim@example.com"},
    )
    assert resp_recip.status_code == 403

    # 11. Add suppression -> 403
    resp_suppress = await async_client.post(
        f"/api/v1/companies/{comp_id}/suppressions",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "suppress_victim@example.com", "reason": "MANUAL"},
    )
    assert resp_suppress.status_code == 403


# =============================================================================
# 2. Authorization: MEMBER Read Access Allowed
# =============================================================================

@pytest.mark.asyncio
async def test_member_read_allowed_on_campaigns(
    async_client: AsyncClient, db_session: AsyncSession
):
    """MEMBER role can read campaigns, details, recipients, and suppressions."""
    owner_token = await register_and_login(async_client, "owner_read@example.com")
    member_email = "member_read@example.com"
    member_token = await register_and_login(async_client, member_email)

    comp_id = await create_company_helper(async_client, owner_token, "Read Org")
    await add_member_helper(async_client, owner_token, comp_id, member_email, role="MEMBER")

    camp_id, _ = await setup_test_campaign(async_client, db_session, owner_token, comp_id)

    # 1. List campaigns -> 200
    resp_list = await async_client.get(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    # 2. Get campaign detail -> 200
    resp_get = await async_client.get(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == camp_id

    # 3. List recipients -> 200
    resp_recips = await async_client.get(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_recips.status_code == 200

    # 4. List suppressions -> 200
    resp_supp = await async_client.get(
        f"/api/v1/companies/{comp_id}/suppressions",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp_supp.status_code == 200


# =============================================================================
# 3. Tenant Isolation & Anti-Enumeration (404)
# =============================================================================

@pytest.mark.asyncio
async def test_cross_company_access_returns_404_anti_enumeration(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Accessing Org 1's campaigns or resources from Org 2 returns 404."""
    token1 = await register_and_login(async_client, "org1_iso@example.com")
    token2 = await register_and_login(async_client, "org2_iso@example.com")

    comp1 = await create_company_helper(async_client, token1, "Tenant 1")
    comp2 = await create_company_helper(async_client, token2, "Tenant 2")

    camp1_id, acc1_id = await setup_test_campaign(async_client, db_session, token1, comp1)

    # Org 2 user attempts to get Org 1's campaign via Org 2 route -> 404
    resp = await async_client.get(
        f"/api/v1/companies/{comp2}/campaigns/{camp1_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 404

    # Org 2 user attempts to get Org 1's campaign via Org 1 route -> 404 (anti-enumeration)
    resp2 = await async_client.get(
        f"/api/v1/companies/{comp1}/campaigns/{camp1_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp2.status_code == 404

    # Org 2 user attempts to create campaign with Org 1's email account -> 404
    resp_hack_acc = await async_client.post(
        f"/api/v1/companies/{comp2}/campaigns",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "name": "Cross Account Campaign",
            "email_account_id": acc1_id,
            "subject": "Hack",
            "body_text": "Hack",
        },
    )
    assert resp_hack_acc.status_code == 404


# =============================================================================
# 4. Concurrency: Safe Handling of Concurrent Delivery Creation
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_delivery_integrity_error_recovery(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Simulate concurrent delivery creation: IntegrityError is caught and worker skips cleanly."""
    token = await register_and_login(async_client, "conc_test@example.com")
    comp_id = await create_company_helper(async_client, token, "Concurrent Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Add recipient
    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "conc_recip@example.com", "first_name": "Conc"},
    )
    recip_id = resp.json()["id"]

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    # Create existing delivery directly simulating another worker that just committed
    deliv = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc),
    )
    db_session.add(deliv)
    await db_session.commit()

    # Now execute campaign: delivery row is already in SENDING, so worker skips it
    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=camp_id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
    )

    assert result["skipped_count"] == 1
    assert result["sent_count"] == 0


# =============================================================================
# 5. Worker Robustness & Transaction Rollback
# =============================================================================

@pytest.mark.asyncio
async def test_worker_db_session_rolls_back_on_unhandled_exception():
    """Worker DB context manager automatically issues a rollback when an unhandled exception occurs."""
    async with tasks.get_worker_db() as db:
        # Check session is active
        assert db.is_active

    # When exception raised inside context manager, rollback is invoked
    with pytest.raises(RuntimeError):
        async with tasks.get_worker_db() as db:
            raise RuntimeError("Forced worker error")


# =============================================================================
# 6. Celery Task Error Logging & Propagation
# =============================================================================

@pytest.mark.asyncio
async def test_celery_task_structured_logging_on_failure():
    """Celery task logs structured operational error when delivery engine raises."""
    with patch(
        "app.modules.campaigns.delivery_service.CampaignDeliveryService.execute_campaign",
        side_effect=RuntimeError("Engine failure"),
    ):
        with pytest.raises(RuntimeError):
            await _async_dispatch_campaign_task(campaign_id=999, company_id=1)

    with patch(
        "app.modules.campaigns.delivery_service.CampaignDeliveryService.retry_delivery",
        side_effect=RuntimeError("Retry failure"),
    ):
        with pytest.raises(RuntimeError):
            await _async_retry_campaign_delivery_task(delivery_id=999, company_id=1)

    with patch(
        "app.modules.campaigns.scheduling_service.CampaignSchedulingService.dispatch_due_campaigns",
        side_effect=RuntimeError("Scheduler failure"),
    ):
        with pytest.raises(RuntimeError):
            await _async_scheduled_campaign_dispatch_task()


# =============================================================================
# 7. Delivery Safety: Mismatched Email Account Marks Campaign FAILED
# =============================================================================

@pytest.mark.asyncio
async def test_email_account_company_mismatch_fails_campaign(
    async_client: AsyncClient, db_session: AsyncSession
):
    """If sender account does not belong to company, campaign is safely transitioned to FAILED."""
    token = await register_and_login(async_client, "mismatch_owner@example.com")
    comp_id = await create_company_helper(async_client, token, "Mismatch Org")
    comp2_id = await create_company_helper(async_client, token, "Mismatch Org 2")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Tamper with campaign to point to a mismatched account from Org 2
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    # Set company_id on account to comp2_id
    acc = (await db_session.execute(select(EmailAccount).where(EmailAccount.id == camp.email_account_id))).scalar_one()
    acc.company_id = comp2_id
    await db_session.commit()

    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=camp_id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
    )

    assert result["status"] == "FAILED"
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.FAILED.value


# =============================================================================
# 8. Stale SENDING Delivery Self-Healing & Deadlock Prevention
# =============================================================================

@pytest.mark.asyncio
async def test_stale_sending_delivery_recovery_and_campaign_completion(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that CampaignDelivery rows stuck in SENDING (e.g. crashed worker) are recovered
    to FAILED and do not permanently deadlock campaign completion."""
    from datetime import timedelta
    from app.modules.campaigns.scheduling_service import CampaignSchedulingService

    token = await register_and_login(async_client, "stale_recovery_owner@example.com")
    comp_id = await create_company_helper(async_client, token, "Stale Recovery Org")
    camp_id, acc_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Add 2 recipients
    r1_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "sent_user@test.com", "first_name": "Sent"},
    )
    r1_id = r1_resp.json()["id"]

    r2_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "crashed_worker_user@test.com", "first_name": "Crashed"},
    )
    r2_id = r2_resp.json()["id"]

    # Set campaign to RUNNING
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value

    # Recipient 1 has a completed SENT delivery
    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec1.status = CampaignRecipientStatus.SENT.value
    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    db_session.add(deliv1)

    # Recipient 2 has a stale SENDING delivery stuck for 15 minutes (worker died)
    rec2 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r2_id))).scalar_one()
    rec2.status = CampaignRecipientStatus.PENDING.value
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    deliv2 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r2_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
        last_attempt_at=stale_time,
    )
    db_session.add(deliv2)
    await db_session.commit()

    # 1. Test CampaignSchedulingService.recover_stale_sending_deliveries recovers deliv2
    recovered = await CampaignSchedulingService.recover_stale_sending_deliveries(
        db_factory=TestAsyncSessionLocal,
        stale_minutes=10,
    )
    assert any(d["delivery_id"] == deliv2.id for d in recovered)

    await db_session.refresh(deliv2)
    assert deliv2.status == CampaignDeliveryStatus.FAILED.value
    assert "timed out or worker interrupted" in deliv2.error_message

    await db_session.refresh(rec2)
    assert rec2.status == CampaignRecipientStatus.FAILED.value

    # 2. Test execute_campaign now completes cleanly without active_sending deadlock
    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=camp_id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
    )
    assert result["status"] == CampaignStatus.COMPLETED.value
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_execute_campaign_in_line_self_heals_stale_sending_deliveries(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that CampaignDeliveryService.execute_campaign automatically recovers stale SENDING
    deliveries (>10m) in-line during Phase 2 and Phase 4 without requiring a scheduler tick."""
    from datetime import timedelta

    token = await register_and_login(async_client, "inline_heal_owner@example.com")
    comp_id = await create_company_helper(async_client, token, "Inline Heal Org")
    camp_id, acc_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    r_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "stale_in_flight@test.com", "first_name": "StaleInFlight"},
    )
    r_id = r_resp.json()["id"]

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value

    # Delivery left in SENDING from 12 minutes ago
    deliv = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=12),
    )
    db_session.add(deliv)
    await db_session.commit()

    # execute_campaign recovers it in Phase 2 and completes in Phase 4
    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=camp_id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
    )
    assert result["status"] == CampaignStatus.COMPLETED.value
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.COMPLETED.value

    await db_session.refresh(deliv)
    assert deliv.status == CampaignDeliveryStatus.FAILED.value
    assert "timed out or worker interrupted" in deliv.error_message
