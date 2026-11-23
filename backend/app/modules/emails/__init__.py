from app.modules.emails.attachment_service import AttachmentService
from app.modules.emails.models import (
    Email,
    EmailAttachment,
    EmailDirection,
    EmailSignature,
    EmailStatus,
    EmailTemplate,
    EmailThread,
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventQuarantine,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_service import EmailTrackingService
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.link_tracking_service import LinkTrackingService
from app.modules.emails.open_tracking_service import OpenTrackingService
from app.modules.emails.bot_classifier import BotClassifier, BotClassificationResult
from app.modules.emails.tracking_schemas import (
    TrackingEventItemResponse,
    TrackingTokenIssueRequest,
    TrackingTokenIssueResponse,
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
    EmailSyncJobResponse,
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
    "EmailSyncJobResponse",
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
    "EmailTrackingToken",
    "EmailTrackingEvent",
    "TrackingEventQuarantine",
    "TrackingTokenType",
    "TrackingEventType",
    "EmailTrackingService",
    "TrackingServiceClient",
    "LinkTrackingService",
    "OpenTrackingService",
    "BotClassifier",
    "BotClassificationResult",
    "TrackingTokenIssueRequest",
    "TrackingTokenIssueResponse",
    "TrackingEventItemResponse",
    "router",
]


