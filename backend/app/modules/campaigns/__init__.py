from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import (
    CampaignCreate,
    CampaignDetailRead,
    CampaignDispatchResponse,
    CampaignPreflightResponse,
    CampaignRead,
    CampaignRecipientBulkCreateRequest,
    CampaignRecipientBulkCreateResponse,
    CampaignRecipientCreate,
    CampaignRecipientImportResponse,
    CampaignRecipientRead,
    CampaignRecipientUpdate,
    CampaignScheduleRequest,
    CampaignUpdate,
    PreflightIssue,
    SuppressionBulkCreateRequest,
    SuppressionBulkCreateResponse,
    SuppressionCreate,
    SuppressionRead,
    normalize_and_validate_email,
)
from app.modules.campaigns.delivery_service import (
    CampaignDeliveryService,
    is_retryable_delivery_error,
    render_content_for_recipient,
)
from app.modules.campaigns.preflight_service import CampaignPreflightService
from app.modules.campaigns.recipient_service import CampaignRecipientService
from app.modules.campaigns.scheduling_service import CampaignSchedulingService
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.campaigns.suppression_routes import router as suppression_router
from app.modules.campaigns.service import (
    CampaignService,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
    DELETABLE_STATES,
)

__all__ = [
    "Campaign",
    "CampaignStatus",
    "CampaignRecipient",
    "CampaignRecipientStatus",
    "CampaignDelivery",
    "CampaignDeliveryStatus",
    "SuppressionEntry",
    "SuppressionReason",
    "CampaignCreate",
    "CampaignUpdate",
    "CampaignRead",
    "CampaignDetailRead",
    "CampaignScheduleRequest",
    "CampaignPreflightResponse",
    "PreflightIssue",
    "CampaignRecipientCreate",
    "CampaignRecipientUpdate",
    "CampaignRecipientRead",
    "CampaignRecipientBulkCreateRequest",
    "CampaignRecipientBulkCreateResponse",
    "CampaignRecipientImportResponse",
    "SuppressionCreate",
    "SuppressionRead",
    "SuppressionBulkCreateRequest",
    "SuppressionBulkCreateResponse",
    "normalize_and_validate_email",
    "CampaignDeliveryService",
    "CampaignDispatchResponse",
    "CampaignDispatchService",
    "CampaignService",
    "CampaignPreflightService",
    "render_content_for_recipient",
    "CampaignRecipientService",
    "CampaignSchedulingService",
    "SuppressionService",
    "suppression_router",
    "VALID_TRANSITIONS",
    "TERMINAL_STATES",
    "DELETABLE_STATES",
]


def __getattr__(name: str):
    if name == "CampaignDispatchService":
        from app.modules.campaigns.dispatch_service import CampaignDispatchService
        return CampaignDispatchService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
