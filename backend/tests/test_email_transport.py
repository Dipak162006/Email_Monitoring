from email.message import EmailMessage
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.email_accounts.models import EmailAccount, SecurityMode
from app.modules.emails.models import Email, EmailStatus
from app.modules.emails.schemas import EmailSendRequest
from app.modules.emails.service import EmailService
from app.modules.campaigns.models import CampaignDelivery
from app.services.smtp.adapter import BaseSMTPAdapter, StandardSMTPAdapter
from app.services.smtp.client import SMTPClient
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConfigurationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
    SMTPSendError,
    SMTPServiceException,
)
from app.services.transport import (
    EmailTransport,
    EmailTransportException,
    EmailTransportRequest,
    EmailTransportResult,
    SMTPTransport,
    TransportAuthenticationError,
    TransportConfigurationError,
    TransportConnectionError,
    TransportRecipientRejectedError,
    TransportSendError,
)


# =============================================================================
# Helper Utilities
# =============================================================================

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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Transport Company") -> int:
    """Helper to create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    name: str = "Support Desk",
    email: str = "support@transport-co.com",
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
            "smtp_host": "smtp.transport-co.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": password,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# 1. Transport Interface & Contract Tests
# =============================================================================

def test_email_transport_interface_contract():
    """Verify that EmailTransport is an abstract contract that cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EmailTransport()  # type: ignore[abstract]  # pyright: ignore[reportAbstractUsage]


def test_smtp_transport_implements_email_transport():
    """Verify that SMTPTransport properly implements the EmailTransport interface."""
    transport = SMTPTransport()
    assert isinstance(transport, EmailTransport)
    assert issubclass(SMTPTransport, EmailTransport)


# =============================================================================
# 2. Delegation & Configuration Pass-Through Tests
# =============================================================================

@pytest.mark.asyncio
async def test_smtp_transport_delegation_to_adapter():
    """Verify SMTPTransport delegates send calls to the underlying BaseSMTPAdapter."""
    mock_adapter = AsyncMock(spec=BaseSMTPAdapter)
    mock_adapter.send.return_value = None

    transport = SMTPTransport(smtp_adapter=mock_adapter)

    account = EmailAccount(
        id=1,
        company_id=1,
        name="Sender",
        email_address="sender@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security=SecurityMode.STARTTLS.value,
        smtp_username="sender@example.com",
    )
    message = EmailMessage()
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "recipient@example.com"
    message["Subject"] = "Test Subject"
    message["Message-ID"] = "<unique-123@example.com>"
    message.set_content("Hello World")

    req = EmailTransportRequest(
        account=account,
        envelope_recipients=["recipient@example.com"],
        message=message,
    )

    result = await transport.send(req)

    # 1. Assert mock adapter received identical account, message, and envelope
    mock_adapter.send.assert_awaited_once_with(
        account=account,
        message=message,
        envelope_recipients=["recipient@example.com"],
    )

    # 2. Assert provider-neutral result returned
    assert isinstance(result, EmailTransportResult)
    assert result.success is True
    assert result.message_id == "<unique-123@example.com>"
    assert result.rejected_recipients == []
    assert result.error_message is None


@pytest.mark.asyncio
async def test_smtp_transport_passes_existing_smtp_configuration():
    """Verify that account configuration (host, port, security, credentials) is preserved verbatim."""
    captured_args = {}

    class InspectingAdapter(BaseSMTPAdapter):
        async def send(self, account, message, envelope_recipients):
            captured_args["host"] = account.smtp_host
            captured_args["port"] = account.smtp_port
            captured_args["security"] = account.smtp_security
            captured_args["username"] = account.smtp_username
            captured_args["from_addr"] = account.email_address
            captured_args["envelope"] = envelope_recipients

    transport = SMTPTransport(smtp_adapter=InspectingAdapter())

    account = EmailAccount(
        id=99,
        company_id=5,
        name="Custom Desk",
        email_address="agent@custom.org",
        smtp_host="mail.custom.org",
        smtp_port=465,
        smtp_security=SecurityMode.SSL.value,
        smtp_username="agent_login",
    )
    req = EmailTransportRequest(
        account=account,
        envelope_recipients=["user1@test.com", "user2@test.com"],
        subject="Hello",
        body_text="Test Body",
    )

    result = await transport.send(req)
    assert result.success is True
    assert captured_args["host"] == "mail.custom.org"
    assert captured_args["port"] == 465
    assert captured_args["security"] == SecurityMode.SSL.value
    assert captured_args["username"] == "agent_login"
    assert captured_args["from_addr"] == "agent@custom.org"
    assert captured_args["envelope"] == ["user1@test.com", "user2@test.com"]


# =============================================================================
# 3. Exception Hierarchy & Retryability Classification Tests
# =============================================================================

@pytest.mark.asyncio
async def test_smtp_transport_exception_classification_and_retryability():
    """Verify that underlying SMTP failures are mapped to Transport exceptions with correct is_retryable status."""
    account = EmailAccount(id=1, company_id=1, email_address="test@co.com", smtp_host="smtp.co.com")
    req = EmailTransportRequest(account=account, envelope_recipients=["dest@co.com"], subject="Test")

    # Case 1: SMTPConnectionError -> TransportConnectionError (retryable)
    mock_adapter = AsyncMock(spec=BaseSMTPAdapter)
    mock_adapter.send.side_effect = SMTPConnectionError("Connection timed out")
    transport = SMTPTransport(smtp_adapter=mock_adapter)
    with pytest.raises(TransportConnectionError) as exc_info:
        await transport.send(req)
    assert exc_info.value.is_retryable is True
    assert isinstance(exc_info.value, SMTPConnectionError)  # Subclass check preserves backward compatibility
    assert isinstance(exc_info.value, EmailTransportException)

    # Case 2: SMTPAuthenticationError -> TransportAuthenticationError (non-retryable)
    mock_adapter.send.side_effect = SMTPAuthenticationError("Invalid credentials")
    with pytest.raises(TransportAuthenticationError) as exc_info:
        await transport.send(req)
    assert exc_info.value.is_retryable is False
    assert isinstance(exc_info.value, SMTPAuthenticationError)
    assert isinstance(exc_info.value, EmailTransportException)

    # Case 3: SMTPConfigurationError -> TransportConfigurationError (non-retryable)
    mock_adapter.send.side_effect = SMTPConfigurationError("Missing SMTP host")
    with pytest.raises(TransportConfigurationError) as exc_info:
        await transport.send(req)
    assert exc_info.value.is_retryable is False
    assert isinstance(exc_info.value, SMTPConfigurationError)
    assert isinstance(exc_info.value, EmailTransportException)

    # Case 4: SMTPRecipientRejectedError -> TransportRecipientRejectedError (non-retryable)
    mock_adapter.send.side_effect = SMTPRecipientRejectedError(
        rejected_recipients=["banned@test.com"], message="Recipient rejected"
    )
    with pytest.raises(TransportRecipientRejectedError) as exc_info:
        await transport.send(req)
    assert exc_info.value.is_retryable is False
    assert exc_info.value.rejected_recipients == ["banned@test.com"]
    assert isinstance(exc_info.value, SMTPRecipientRejectedError)

    # Case 5: SMTPSendError -> TransportSendError (retryable)
    mock_adapter.send.side_effect = SMTPSendError("Data transmission failed")
    with pytest.raises(TransportSendError) as exc_info:
        await transport.send(req)
    assert exc_info.value.is_retryable is True
    assert isinstance(exc_info.value, SMTPSendError)


# =============================================================================
# 4. EmailTransportRequest Message Construction
# =============================================================================

def test_transport_request_lazy_message_builder():
    """Verify that EmailTransportRequest generates a RFC-compliant MIME message when none is pre-built."""
    account = EmailAccount(
        id=1,
        company_id=1,
        name="Support Team",
        email_address="support@domain.com",
    )
    req = EmailTransportRequest(
        account=account,
        envelope_recipients=["customer@example.com"],
        subject="Welcome to Service",
        body_text="Plain text body.",
        body_html="<p>HTML body.</p>",
        headers={"X-Custom-Campaign": "Spring2026"},
    )

    mime_msg = req.get_message()
    assert mime_msg["From"] == "Support Team <support@domain.com>"
    assert mime_msg["To"] == "customer@example.com"
    assert mime_msg["Subject"] == "Welcome to Service"
    assert mime_msg["Message-ID"] is not None
    assert mime_msg["Date"] is not None
    assert mime_msg["X-Custom-Campaign"] == "Spring2026"
    assert mime_msg.is_multipart() is True


# =============================================================================
# 5. EmailService Integration & Backward Compatibility Tests
# =============================================================================

def test_email_service_initialization_options():
    """Verify EmailService accepts both new transport and legacy smtp_adapter parameters."""
    # 1. Default initialization
    svc1 = EmailService()
    assert isinstance(svc1.transport, SMTPTransport)
    assert isinstance(svc1.smtp_adapter, StandardSMTPAdapter)

    # 2. Initialization with custom transport
    custom_transport = SMTPTransport()
    svc2 = EmailService(transport=custom_transport)
    assert svc2.transport is custom_transport
    assert isinstance(svc2.smtp_adapter, StandardSMTPAdapter)

    # 3. Legacy initialization with smtp_adapter
    mock_adapter = AsyncMock(spec=BaseSMTPAdapter)
    svc3 = EmailService(smtp_adapter=mock_adapter)
    assert isinstance(svc3.transport, SMTPTransport)
    assert svc3.smtp_adapter is mock_adapter


@pytest.mark.asyncio
async def test_email_service_send_via_transport_success(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test full email sending flow through EmailService using the transport boundary."""
    token = await register_and_login(async_client, "owner_svc_trans@co.com", "Owner User")
    company_id = await create_company_helper(async_client, token, "Transport Co")
    account_id = await create_account_helper(async_client, token, company_id, name="HelpDesk", email="help@co.com")

    send_payload = {
        "email_account_id": account_id,
        "to": ["user@dest.com"],
        "subject": "Transport Test",
        "body_text": "Hello via transport abstraction.",
    }

    with patch.object(SMTPClient, "send_email_sync", return_value=None) as mock_send_sync:
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=send_payload,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["subject"] == "Transport Test"
        assert data["status"] == "SENT"
        assert data["direction"] == "OUTGOING"
        assert data["message_id"] is not None

        # Confirm smtplib client was actually called through the transport pipeline
        mock_send_sync.assert_called_once()


@pytest.mark.asyncio
async def test_email_service_send_via_transport_failure_persistence(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that transport-level failure persists a FAILED Email record and raises 502."""
    token = await register_and_login(async_client, "owner_svc_fail@co.com", "Owner Fail")
    company_id = await create_company_helper(async_client, token, "Fail Co")
    account_id = await create_account_helper(async_client, token, company_id, name="FailDesk", email="fail@co.com")

    send_payload = {
        "email_account_id": account_id,
        "to": ["user@dest.com"],
        "subject": "Failure Test",
        "body_text": "Testing transport failure.",
    }

    with patch.object(
        SMTPClient,
        "send_email_sync",
        side_effect=SMTPConnectionError("Remote host unreachable"),
    ):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=send_payload,
        )

        assert resp.status_code == 502

        # Verify failed email was persisted for auditability
        res = await db_session.execute(
            select(Email).where(Email.subject == "Failure Test")
        )
        failed_email = res.scalar_one_or_none()
        assert failed_email is not None
        assert failed_email.status == EmailStatus.FAILED.value
        assert "Could not connect to SMTP server" in failed_email.error_message


# =============================================================================
# 6. Threading & Header Invariant Tests
# =============================================================================

@pytest.mark.asyncio
async def test_email_service_threading_headers_preserved_via_transport(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that In-Reply-To and References headers are preserved across the transport boundary."""
    token = await register_and_login(async_client, "owner_thread_trans@co.com", "Owner Thread")
    company_id = await create_company_helper(async_client, token, "Thread Trans Co")
    account_id = await create_account_helper(async_client, token, company_id, name="ThreadDesk", email="thread@co.com")

    # 1. Send first email
    send_1 = {
        "email_account_id": account_id,
        "to": ["client@example.com"],
        "subject": "Initial Thread Message",
        "body_text": "First message.",
    }
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        resp1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=send_1,
        )
        assert resp1.status_code == 201
        msg1_id = resp1.json()["message_id"]
        thread_id = resp1.json()["thread_id"]

    # 2. Send reply with in_reply_to
    send_2 = {
        "email_account_id": account_id,
        "to": ["client@example.com"],
        "subject": "Re: Initial Thread Message",
        "body_text": "Reply message.",
        "in_reply_to": msg1_id,
        "thread_id": thread_id,
    }

    captured_message = None

    def capture_sync_send(*args, **kwargs):
        nonlocal captured_message
        captured_message = kwargs.get("message")

    with patch.object(SMTPClient, "send_email_sync", side_effect=capture_sync_send):
        resp2 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=send_2,
        )
        assert resp2.status_code == 201
        data2 = resp2.json()
        assert data2["in_reply_to"] == msg1_id
        assert data2["thread_id"] == thread_id
        assert captured_message is not None
        assert captured_message["In-Reply-To"] == msg1_id
        assert msg1_id in captured_message["References"]


# =============================================================================
# 7. Isolation & Non-Interference Invariant Tests
# =============================================================================

@pytest.mark.asyncio
async def test_no_campaign_delivery_side_effects(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify that email transport activity does not create CampaignDelivery records."""
    count_before = len((await db_session.execute(select(CampaignDelivery))).scalars().all())

    token = await register_and_login(async_client, "owner_isolation_c6@co.com", "Owner Iso")
    company_id = await create_company_helper(async_client, token, "Isolation Co")
    account_id = await create_account_helper(async_client, token, company_id, name="IsoDesk", email="iso@co.com")

    send_payload = {
        "email_account_id": account_id,
        "to": ["nobody@example.com"],
        "subject": "Isolation Test",
        "body_text": "Verify no CampaignDelivery records are created.",
    }

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json=send_payload,
        )
        assert resp.status_code == 201

    count_after = len((await db_session.execute(select(CampaignDelivery))).scalars().all())
    assert count_after == count_before
