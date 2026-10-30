from email.message import EmailMessage
import poplib
import socket
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_credential
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount, IncomingProtocol, SecurityMode
from app.modules.emails.models import Email, EmailAttachment
from app.modules.emails.sync_service import EmailSyncService
from app.services.imap.adapter import StandardIMAPAdapter
from app.services.pop3.adapter import StandardPOP3Adapter
from app.services.pop3.client import POP3Client
from app.services.pop3.exceptions import (
    POP3AuthenticationError,
    POP3ConfigurationError,
    POP3ConnectionError,
)
from app.workers.tasks import is_retryable_exception


def make_test_rfc822_email(
    msg_id: str,
    subject: str,
    from_addr: str,
    to_addr: str,
    body_text: str,
    body_html: str = "",
    date_header: str = "Fri, 30 Oct 2026 10:00:00 +0000",
) -> bytes:
    """Helper creating a standard RFC 822 MIME message for POP3 RETR simulation."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = date_header
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg.as_bytes()


def make_test_rfc822_with_attachment(
    msg_id: str,
    subject: str,
    from_addr: str,
    to_addr: str,
    filename: str,
    file_bytes: bytes,
) -> bytes:
    """Helper creating an RFC 822 email containing a binary attachment."""
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = "Fri, 30 Oct 2026 10:15:00 +0000"
    msg.set_content("Please find attached invoice.")
    msg.add_attachment(
        file_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Test 1: POP3 SSL Connection and Successful Authentication
# ---------------------------------------------------------------------------
def test_pop3_client_connect_and_login_success():
    """Verify POP3Client connects via implicit SSL to pop3s.aruba.it:995 and logs in."""
    client = POP3Client(timeout=10)

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_instance = MagicMock()
        mock_ssl_cls.return_value = mock_instance

        client.connect(host="pop3s.aruba.it", port=995, security_mode="SSL")
        mock_ssl_cls.assert_called_once()
        assert client._connected is True

        client.login(username="info@arubadomain.it", password="SecretPassword123")
        mock_instance.user.assert_called_once_with("info@arubadomain.it")
        mock_instance.pass_.assert_called_once_with("SecretPassword123")

        client.quit()
        mock_instance.quit.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Authentication Failure Classification (Non-Retryable)
# ---------------------------------------------------------------------------
def test_pop3_client_auth_failure_classification():
    """Verify that POP3 authentication errors raise POP3AuthenticationError and are non-retryable."""
    client = POP3Client(timeout=10)

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_instance = MagicMock()
        mock_instance.pass_.side_effect = poplib.error_proto(b"-ERR [AUTH] Authentication failed.")
        mock_ssl_cls.return_value = mock_instance

        client.connect(host="pop3s.aruba.it", port=995, security_mode="SSL")

        with pytest.raises(POP3AuthenticationError) as exc_info:
            client.login(username="info@arubadomain.it", password="WrongPassword")

        assert "Authentication failed" in str(exc_info.value)
        # Verify Celery task categorizes this fatal error as non-retryable
        assert is_retryable_exception(exc_info.value) is False


# ---------------------------------------------------------------------------
# Test 3: UIDL Retrieval and Stable Message Identification
# ---------------------------------------------------------------------------
def test_pop3_uidl_retrieval_and_parsing():
    """Verify POP3 UIDL command correctly extracts persistent message identifier mapping."""
    client = POP3Client(timeout=10)

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_instance = MagicMock()
        # poplib.uidl() returns (resp, [lines], octets)
        mock_instance.uidl.return_value = (
            b"+OK",
            [
                b"1 000000014b2d38f2",
                b"2 000000024b2d38f3",
                b"3 000000034b2d38f4",
            ],
            120,
        )
        mock_ssl_cls.return_value = mock_instance

        client.connect(host="pop3s.aruba.it", port=995, security_mode="SSL")
        uidl_map = client.get_uidl_map()

        assert len(uidl_map) == 3
        assert uidl_map[1] == "000000014b2d38f2"
        assert uidl_map[2] == "000000024b2d38f3"
        assert uidl_map[3] == "000000034b2d38f4"


# ---------------------------------------------------------------------------
# Test 4: POP3 Duplicate Prevention via Existing UIDLs
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_pop3_sync_duplicate_prevention(db_session: AsyncSession):
    """Verify that previously synced UIDLs are excluded and not duplicated."""
    # 1. Create company and POP3 EmailAccount
    company = Company(name="POP3 Deduplication Test Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Aruba POP3 Inbox",
        email_address="contact@arubadomain.it",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
        imap_port=995,
        imap_security=SecurityMode.SSL.value,
        imap_username="contact@arubadomain.it",
        imap_password_encrypted=encrypt_credential("SecretArubaPass!"),
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    # 2. Insert one pre-existing email with UIDL '000000014b2d38f2'
    existing_email = Email(
        company_id=company.id,
        email_account_id=account.id,
        message_id="<already-exists@remote.com>",
        imap_uid="000000014b2d38f2",
        direction="INCOMING",
        status="RECEIVED",
        sender="sender1@client.com",
        recipients=["contact@arubadomain.it"],
        subject="Existing Message",
        body_text="Already synced",
    )
    db_session.add(existing_email)
    await db_session.commit()

    # 3. Mock POP3 server with 2 messages on server (1 existing, 1 new)
    email2_raw = make_test_rfc822_email(
        msg_id="<new-message-2@remote.com>",
        subject="Brand New Email",
        from_addr="sender2@client.com",
        to_addr="contact@arubadomain.it",
        body_text="Here is a brand new email body.",
    )

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_pop = MagicMock()
        mock_pop.uidl.return_value = (
            b"+OK",
            [
                b"1 000000014b2d38f2",
                b"2 000000024b2d38f3",
            ],
            80,
        )
        # Message 2 RETR returns lines as bytes
        mock_pop.retr.return_value = (b"+OK", email2_raw.splitlines(), len(email2_raw))
        mock_ssl_cls.return_value = mock_pop

        sync_service = EmailSyncService()
        result = await sync_service.sync_mailbox(
            db=db_session,
            account=account,
            folder="INBOX",
            max_messages=50,
        )

        assert result.new_messages == 1
        assert result.duplicates_skipped == 0
        assert result.total_discovered == 1

        # Verify database has 2 emails total for this account
        db_emails = await db_session.execute(
            select(Email).where(Email.email_account_id == account.id)
        )
        stored = db_emails.scalars().all()
        assert len(stored) == 2
        uids = {e.imap_uid for e in stored}
        assert uids == {"000000014b2d38f2", "000000024b2d38f3"}


# ---------------------------------------------------------------------------
# Test 5: Safe Message Retrieval and MIME Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_pop3_safe_message_retrieval_and_mime_parsing(db_session: AsyncSession):
    """Verify that POP3 RETR bytes are passed through EmailParser and populate database fields."""
    company = Company(name="POP3 MIME Parsing Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Aruba Info",
        email_address="info@aruba.it",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
        imap_port=995,
        imap_security=SecurityMode.SSL.value,
        imap_username="info@aruba.it",
        imap_password_encrypted=encrypt_credential("Password123!"),
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    raw_email = make_test_rfc822_email(
        msg_id="<mime-test-123@domain.com>",
        subject="Proposta Commerciale",
        from_addr="Cliente Importante <cliente@partner.com>",
        to_addr="info@aruba.it",
        body_text="Buongiorno, inviamo la proposta in allegato.",
        body_html="<p>Buongiorno, inviamo la proposta in <strong>allegato</strong>.</p>",
        date_header="Wed, 28 Oct 2026 14:30:00 +0000",
    )

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_pop = MagicMock()
        mock_pop.uidl.return_value = (b"+OK", [b"1 00000001pop3uidl123"], 40)
        mock_pop.retr.return_value = (b"+OK", raw_email.splitlines(), len(raw_email))
        mock_ssl_cls.return_value = mock_pop

        sync_service = EmailSyncService()
        result = await sync_service.sync_mailbox(
            db=db_session,
            account=account,
        )

        assert result.new_messages == 1

        # Check stored email
        res = await db_session.execute(
            select(Email).where(Email.email_account_id == account.id)
        )
        email_obj = res.scalars().first()
        assert email_obj is not None
        assert email_obj.subject == "Proposta Commerciale"
        assert "Cliente Importante" in email_obj.sender
        assert email_obj.imap_uid == "00000001pop3uidl123"
        assert "<p>Buongiorno" in (email_obj.body_html or "")
        assert email_obj.received_at is not None
        assert email_obj.received_at.year == 2026


# ---------------------------------------------------------------------------
# Test 6: POP3 Attachment Parsing
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_pop3_attachment_parsing(db_session: AsyncSession):
    """Verify that attachments delivered via POP3 are extracted and stored in EmailAttachment."""
    company = Company(name="POP3 Attachment Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Orders Account",
        email_address="orders@aruba.it",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
        imap_port=995,
        imap_security=SecurityMode.SSL.value,
        imap_username="orders@aruba.it",
        imap_password_encrypted=encrypt_credential("Password123!"),
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    pdf_bytes = b"%PDF-1.4 test invoice attachment content"
    raw_email = make_test_rfc822_with_attachment(
        msg_id="<order-att-999@domain.com>",
        subject="Invoice #88492",
        from_addr="billing@supplier.com",
        to_addr="orders@aruba.it",
        filename="invoice_88492.pdf",
        file_bytes=pdf_bytes,
    )

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_pop = MagicMock()
        mock_pop.uidl.return_value = (b"+OK", [b"1 00000001invoiceuidl"], 40)
        mock_pop.retr.return_value = (b"+OK", raw_email.splitlines(), len(raw_email))
        mock_ssl_cls.return_value = mock_pop

        sync_service = EmailSyncService()
        result = await sync_service.sync_mailbox(db=db_session, account=account)

        assert result.new_messages == 1

        # Check attachment record
        att_res = await db_session.execute(
            select(EmailAttachment).where(EmailAttachment.email_account_id == account.id)
        )
        attachment = att_res.scalars().first()
        assert attachment is not None
        assert attachment.file_name == "invoice_88492.pdf"
        assert attachment.file_size == len(pdf_bytes)


# ---------------------------------------------------------------------------
# Test 7: Non-Destructive Ingest: Explicit Verification DELE is NEVER Called
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_pop3_non_destructive_verification_dele_never_called(db_session: AsyncSession):
    """Verify strictly that the POP3 DELE command is NEVER called during synchronization."""
    company = Company(name="POP3 Non-Destructive Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Safety Check Account",
        email_address="safe@aruba.it",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
        imap_port=995,
        imap_security=SecurityMode.SSL.value,
        imap_username="safe@aruba.it",
        imap_password_encrypted=encrypt_credential("Password123!"),
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    email_bytes = make_test_rfc822_email(
        msg_id="<safe-check@domain.com>",
        subject="Important Server Message",
        from_addr="remote@domain.com",
        to_addr="safe@aruba.it",
        body_text="This must stay on the remote server forever.",
    )

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_pop = MagicMock()
        mock_pop.uidl.return_value = (b"+OK", [b"1 00000001stayonserver"], 40)
        mock_pop.retr.return_value = (b"+OK", email_bytes.splitlines(), len(email_bytes))
        mock_ssl_cls.return_value = mock_pop

        sync_service = EmailSyncService()
        await sync_service.sync_mailbox(db=db_session, account=account)

        # STRICT VERIFICATION: dele was NEVER called
        assert not hasattr(mock_pop, "dele") or mock_pop.dele.called is False
        # Clean QUIT was issued
        mock_pop.quit.assert_called_once()


# ---------------------------------------------------------------------------
# Test 8: Protocol-Aware Adapter Selection (IMAP vs POP3)
# ---------------------------------------------------------------------------
def test_adapter_selection_imap_vs_pop3():
    """Verify EmailSyncService selects StandardPOP3Adapter for POP3 and StandardIMAPAdapter for IMAP."""
    service = EmailSyncService()

    # IMAP Account
    imap_account = EmailAccount(
        company_id=1,
        name="IMAP Acc",
        email_address="imap@test.com",
        incoming_protocol=IncomingProtocol.IMAP.value,
        imap_host="imap.test.com",
    )
    adapter_imap = service.get_adapter(imap_account)
    assert isinstance(adapter_imap, StandardIMAPAdapter)

    # POP3 Account
    pop3_account = EmailAccount(
        company_id=1,
        name="POP3 Acc",
        email_address="pop3@test.com",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
    )
    adapter_pop3 = service.get_adapter(pop3_account)
    assert isinstance(adapter_pop3, StandardPOP3Adapter)


# ---------------------------------------------------------------------------
# Test 9: Transient Connection Retry Behavior
# ---------------------------------------------------------------------------
def test_pop3_transient_connection_retry_behavior():
    """Verify that socket timeouts and connection errors raise POP3ConnectionError and are marked retryable."""
    client = POP3Client(timeout=5)

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_ssl_cls.side_effect = socket.timeout("Timed out connecting to POP3 socket")

        with pytest.raises(POP3ConnectionError) as exc_info:
            client.connect(host="pop3s.aruba.it", port=995, security_mode="SSL")

        # Must be classified as retryable by Celery task classifier
        assert is_retryable_exception(exc_info.value) is True


# ---------------------------------------------------------------------------
# Test 10: POP3 Folder Normalization to Single Inbox
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_pop3_folder_normalization_to_inbox(db_session: AsyncSession):
    """Verify that passing an arbitrary folder argument to POP3 sync safely normalizes to 'INBOX'."""
    company = Company(name="POP3 Folder Norm Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Folder Test Account",
        email_address="folder@aruba.it",
        incoming_protocol=IncomingProtocol.POP3.value,
        imap_host="pop3s.aruba.it",
        imap_port=995,
        imap_security=SecurityMode.SSL.value,
        imap_username="folder@aruba.it",
        imap_password_encrypted=encrypt_credential("Password123!"),
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    email_bytes = make_test_rfc822_email(
        msg_id="<folder-test@domain.com>",
        subject="Folder Normalization Test",
        from_addr="remote@domain.com",
        to_addr="folder@aruba.it",
        body_text="Folder test message",
    )

    with patch("poplib.POP3_SSL") as mock_ssl_cls:
        mock_pop = MagicMock()
        mock_pop.uidl.return_value = (b"+OK", [b"1 00000001norminbox"], 40)
        mock_pop.retr.return_value = (b"+OK", email_bytes.splitlines(), len(email_bytes))
        mock_ssl_cls.return_value = mock_pop

        sync_service = EmailSyncService()
        # Pass non-inbox folder name e.g. "Sent"
        result = await sync_service.sync_mailbox(
            db=db_session,
            account=account,
            folder="CustomNonInboxFolder",
        )

        assert result.new_messages == 1
        assert result.folder == "INBOX"
