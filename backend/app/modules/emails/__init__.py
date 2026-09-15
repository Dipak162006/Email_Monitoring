from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailTemplate, EmailThread
from app.modules.emails.routes import router
from app.modules.emails.schemas import (
    EmailRead,
    EmailSendRequest,
    EmailSyncRequest,
    EmailSyncResult,
    EmailTemplateCreate,
    EmailTemplateListResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
    EmailThreadDetail,
    EmailThreadRead,
    ThreadListResponse,
)
from app.modules.emails.service import EmailService
from app.modules.emails.sync_service import EmailSyncService
from app.modules.emails.template_service import EmailTemplateService
from app.modules.emails.thread_service import EmailThreadService

__all__ = [
    "Email",
    "EmailDirection",
    "EmailStatus",
    "EmailTemplate",
    "EmailThread",
    "EmailRead",
    "EmailSendRequest",
    "EmailSyncRequest",
    "EmailSyncResult",
    "EmailTemplateCreate",
    "EmailTemplateListResponse",
    "EmailTemplateRead",
    "EmailTemplateUpdate",
    "EmailThreadRead",
    "EmailThreadDetail",
    "ThreadListResponse",
    "EmailService",
    "EmailSyncService",
    "EmailTemplateService",
    "EmailThreadService",
    "router",
]


