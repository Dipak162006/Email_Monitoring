from app.modules.emails.attachment_service import AttachmentService
from app.modules.emails.models import (
    Email,
    EmailAttachment,
    EmailDirection,
    EmailSignature,
    EmailStatus,
    EmailTemplate,
    EmailThread,
)
from app.modules.emails.routes import router
from app.modules.emails.schemas import (
    AttachmentListResponse,
    AttachmentRead,
    EmailAttachmentListResponse,
    EmailAttachmentRead,
    EmailRead,
    EmailSendRequest,
    EmailSignatureCreate,
    EmailSignatureListResponse,
    EmailSignatureRead,
    EmailSignatureUpdate,
    EmailSyncRequest,
    EmailSyncResult,
    EmailTemplateCreate,
    EmailTemplateListResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
    EmailThreadDetail,
    EmailThreadRead,
    SignatureCreate,
    SignatureListResponse,
    SignatureRead,
    SignatureUpdate,
    ThreadListResponse,
)
from app.modules.emails.monitoring_service import EmailMonitoringService
from app.modules.emails.service import EmailService
from app.modules.emails.signature_service import SignatureService
from app.modules.emails.sync_service import EmailSyncService
from app.modules.emails.template_service import EmailTemplateService
from app.modules.emails.thread_service import EmailThreadService

__all__ = [
    "Email",
    "EmailAttachment",
    "EmailDirection",
    "EmailSignature",
    "EmailStatus",
    "EmailTemplate",
    "EmailThread",
    "EmailAttachmentRead",
    "EmailAttachmentListResponse",
    "AttachmentRead",
    "AttachmentListResponse",
    "EmailRead",
    "EmailSendRequest",
    "EmailSignatureCreate",
    "EmailSignatureListResponse",
    "EmailSignatureRead",
    "EmailSignatureUpdate",
    "SignatureCreate",
    "SignatureListResponse",
    "SignatureRead",
    "SignatureUpdate",
    "EmailSyncRequest",
    "EmailSyncResult",
    "EmailTemplateCreate",
    "EmailTemplateListResponse",
    "EmailTemplateRead",
    "EmailTemplateUpdate",
    "EmailThreadRead",
    "EmailThreadDetail",
    "ThreadListResponse",
    "EmailMonitoringService",
    "EmailService",
    "SignatureService",
    "AttachmentService",
    "EmailSyncService",
    "EmailTemplateService",
    "EmailThreadService",
    "router",
]


