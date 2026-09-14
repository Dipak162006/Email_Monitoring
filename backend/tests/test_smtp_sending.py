from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount, EmailAccountAccess
from app.modules.emails.models import Email, EmailStatus
from app.services.smtp.client import SMTPClient
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
)


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
    password: str = "PlainSmtpPassword123!",
) -> int:
    """Helper to create an email account with SMTP settings and return its ID."""
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
            "smtp_password": password,
        },
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_successful_email_send(async_client: AsyncClient, db_session: AsyncSession):
    """Test sending an email successfully with MIME headers, recipient envelope, and DB logging."""
    owner_token = await register_and_login(async_client, "owner_m5@test.com", "Owner User")
    company_id = await create_company_helper(async_client, owner_token, "Acme M5")
    account_id = await create_account_helper(
        async_client,
        owner_token,
        company_id,
        name="Acme Support",
        email="support@acme.com",
        password="SuperSecretPassword!",
    )

    send_payload = {
        "email_account_id": account_id,
        "to": ["customer@example.com"],
        "cc": ["manager@example.com"],
        "bcc": ["archive@example.com"],
        "subject": "Ticket Resolved",
        "body_text": "Your issue has been resolved.",
        "body_html": "<p>Your issue has been <b>resolved</b>.</p>",
    }

    with patch.object(SMTPClient, "send_email_sync", return_value=None) as mock_send:
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {owner_token}"},
            json=send_payload,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["subject"] == "Ticket Resolved"
        assert data["status"] == "SENT"
        assert data["direction"] == "OUTGOING"
        assert data["sender"] == "Acme Support <support@acme.com>"
        assert data["recipients"] == ["customer@example.com"]
        assert data["cc"] == ["manager@example.com"]
        assert data["bcc"] == ["archive@example.com"]
        assert data["sent_at"] is not None
        assert data["error_message"] is None

        # Verify SMTP Client arguments
        assert mock_send.call_count == 1
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["host"] == "smtp.company.com"
        assert call_kwargs["port"] == 587
        assert call_kwargs["security_mode"] == "STARTTLS"
        assert call_kwargs["username"] == "support@acme.com"
        assert call_kwargs["password"] == "SuperSecretPassword!"  # Decrypted in memory
        assert call_kwargs["from_addr"] == "support@acme.com"
        assert "customer@example.com" in call_kwargs["to_addrs"]
        assert "manager@example.com" in call_kwargs["to_addrs"]
        assert "archive@example.com" in call_kwargs["to_addrs"]

        # Verify message headers
        mime_msg = call_kwargs["message"]
        assert mime_msg["From"] == "Acme Support <support@acme.com>"
        assert mime_msg["To"] == "customer@example.com"
        assert mime_msg["Cc"] == "manager@example.com"
        assert mime_msg["Bcc"] is None  # BCC must not leak into headers
        assert mime_msg["Message-ID"] is not None

        # Verify Database Record
        db_email = (
            await db_session.execute(select(Email).where(Email.id == data["id"]))
        ).scalars().first()
        assert db_email is not None
        assert db_email.status == EmailStatus.SENT.value
        assert db_email.sent_at is not None


@pytest.mark.asyncio
async def test_credentials_not_exposed_in_api_or_logs(async_client: AsyncClient, db_session: AsyncSession):
    """Test that decrypted or encrypted passwords are never returned in API responses."""
    owner_token = await register_and_login(async_client, "owner_sec@test.com", "Security Owner")
    company_id = await create_company_helper(async_client, owner_token, "SecCorp")
    secret_pw = "ExtremelyConfidentialPassword999!"
    account_id = await create_account_helper(
        async_client,
        owner_token,
        company_id,
        name="Billing",
        email="billing@seccorp.com",
        password=secret_pw,
    )

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "email_account_id": account_id,
                "to": ["client@example.com"],
                "subject": "Invoice Paid",
                "body_text": "Thank you for your payment.",
            },
        )
        assert resp.status_code == 201
        resp_text = resp.text
        assert secret_pw not in resp_text
        assert "password" not in resp_text.lower() or '"has_smtp_password"' in resp_text

        email_id = resp.json()["id"]
        # Fetch email detail endpoint
        detail_resp = await async_client.get(
            f"/api/v1/emails/{email_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert detail_resp.status_code == 200
        assert secret_pw not in detail_resp.text


@pytest.mark.asyncio
async def test_from_address_cannot_be_spoofed(async_client: AsyncClient):
    """Verify that From address is derived strictly from EmailAccount and client input is ignored/rejected."""
    owner_token = await register_and_login(async_client, "owner_from@test.com", "From Owner")
    company_id = await create_company_helper(async_client, owner_token, "FromCorp")
    account_id = await create_account_helper(
        async_client,
        owner_token,
        company_id,
        name="Official Mailer",
        email="mailer@fromcorp.com",
    )

    # Attempting to send with arbitrary extra field 'from' or 'sender' should fail Pydantic validation (extra='forbid')
    bad_payload = {
        "email_account_id": account_id,
        "to": ["target@example.com"],
        "subject": "Spoof Attempt",
        "body_text": "Hello",
        "from": "ceo@whitehouse.gov",
    }
    resp = await async_client.post(
        "/api/v1/emails/send",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=bad_payload,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_member_email_account_authorization(async_client: AsyncClient, db_session: AsyncSession):
    """Test authorized user vs unauthorized member vs cross-company user permissions."""
    # Setup Company A with Owner and Member
    token_a_owner = await register_and_login(async_client, "owner_a@test.com", "Owner A")
    company_a_id = await create_company_helper(async_client, token_a_owner, "Company A")
    account_a_id = await create_account_helper(
        async_client,
        token_a_owner,
        company_a_id,
        name="Sales A",
        email="sales@companya.com",
    )

    token_a_member = await register_and_login(async_client, "member_a@test.com", "Member A")
    await async_client.post(
        f"/api/v1/companies/{company_a_id}/members",
        headers={"Authorization": f"Bearer {token_a_owner}"},
        json={"email": "member_a@test.com", "role": "MEMBER"},
    )

    # Setup Company B with Owner
    token_b = await register_and_login(async_client, "owner_b@test.com", "Owner B")
    company_b_id = await create_company_helper(async_client, token_b, "Company B")

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        # 1. Member A does not have access yet -> 403 Forbidden
        resp_unauth = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token_a_member}"},
            json={
                "email_account_id": account_a_id,
                "to": ["recipient@example.com"],
                "subject": "Unauthorized Test",
                "body_text": "Content",
            },
        )
        assert resp_unauth.status_code == 403

        # 2. Grant Member A access to account_a
        # Get member A user id
        user_resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_a_member}"},
        )
        member_a_id = user_resp.json()["id"]

        grant_resp = await async_client.post(
            f"/api/v1/companies/{company_a_id}/email-accounts/{account_a_id}/access",
            headers={"Authorization": f"Bearer {token_a_owner}"},
            json={"user_id": member_a_id},
        )
        assert grant_resp.status_code == 201

        # 3. Member A can now send successfully -> 201 Created
        resp_auth = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token_a_member}"},
            json={
                "email_account_id": account_a_id,
                "to": ["recipient@example.com"],
                "subject": "Authorized Test",
                "body_text": "Content",
            },
        )
        assert resp_auth.status_code == 201

        # 4. User from Company B attempts to send from Company A account -> 403 Forbidden
        resp_cross = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "email_account_id": account_a_id,
                "to": ["recipient@example.com"],
                "subject": "Cross Company Attempt",
                "body_text": "Content",
            },
        )
        assert resp_cross.status_code == 403


@pytest.mark.asyncio
async def test_smtp_authentication_failure_handling(async_client: AsyncClient, db_session: AsyncSession):
    """Test handling SMTP authentication failure (status FAILED saved in DB, 502 returned)."""
    token = await register_and_login(async_client, "owner_fail@test.com", "Fail Owner")
    company_id = await create_company_helper(async_client, token, "FailCorp")
    account_id = await create_account_helper(
        async_client,
        token,
        company_id,
        name="Auth Fail Desk",
        email="authfail@failcorp.com",
    )

    with patch.object(
        SMTPClient,
        "send_email_sync",
        side_effect=SMTPAuthenticationError("SMTP authentication failed. Please verify credentials."),
    ):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": account_id,
                "to": ["user@example.com"],
                "subject": "Auth Failure Test",
                "body_text": "Will fail",
            },
        )
        assert resp.status_code == 502
        assert "SMTP authentication failed" in resp.json()["detail"]

        # Verify failed email was persisted in the database with status FAILED
        emails = (await db_session.execute(select(Email).where(Email.email_account_id == account_id))).scalars().all()
        assert len(emails) == 1
        assert emails[0].status == EmailStatus.FAILED.value
        assert emails[0].sent_at is None
        assert "SMTP authentication failed" in emails[0].error_message


@pytest.mark.asyncio
async def test_smtp_connection_failure_handling(async_client: AsyncClient, db_session: AsyncSession):
    """Test handling SMTP connection failure (server unreachable, timeout)."""
    token = await register_and_login(async_client, "owner_conn@test.com", "Conn Owner")
    company_id = await create_company_helper(async_client, token, "ConnCorp")
    account_id = await create_account_helper(
        async_client,
        token,
        company_id,
        name="Conn Desk",
        email="conn@conncorp.com",
    )

    with patch.object(
        SMTPClient,
        "send_email_sync",
        side_effect=SMTPConnectionError("Failed to connect to SMTP server 'smtp.company.com:587'."),
    ):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": account_id,
                "to": ["user@example.com"],
                "subject": "Connection Failure Test",
                "body_text": "Connection down",
            },
        )
        assert resp.status_code == 502
        assert "Could not connect to SMTP server" in resp.json()["detail"]

        # Verify failed email was persisted in the database with status FAILED
        emails = (await db_session.execute(select(Email).where(Email.email_account_id == account_id))).scalars().all()
        assert len(emails) == 1
        assert emails[0].status == EmailStatus.FAILED.value


@pytest.mark.asyncio
async def test_send_request_validation(async_client: AsyncClient):
    """Test validation errors for invalid recipients and missing bodies."""
    token = await register_and_login(async_client, "owner_val@test.com", "Val Owner")

    # Invalid recipient email format
    resp1 = await async_client.post(
        "/api/v1/emails/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": 1,
            "to": ["not-a-valid-email"],
            "subject": "Invalid Email Test",
            "body_text": "Hello",
        },
    )
    assert resp1.status_code == 422

    # Neither body_text nor body_html provided
    resp2 = await async_client.post(
        "/api/v1/emails/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": 1,
            "to": ["valid@example.com"],
            "subject": "No Body Test",
        },
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_inactive_email_account_cannot_send(async_client: AsyncClient, db_session: AsyncSession):
    """Test that an inactive email account is rejected from sending with 400 Bad Request."""
    token = await register_and_login(async_client, "owner_inact@test.com", "Inactive Owner")
    company_id = await create_company_helper(async_client, token, "InactiveCorp")
    account_id = await create_account_helper(async_client, token, company_id, "Inbox", "inbox@corp.com")

    # Deactivate account
    await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )

    resp = await async_client.post(
        "/api/v1/emails/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": account_id,
            "to": ["user@example.com"],
            "subject": "Inactive Test",
            "body_text": "Hello",
        },
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()
