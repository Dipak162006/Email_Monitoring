from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.campaigns.schemas import normalize_and_validate_email


# ---------------------------------------------------------------------------
# Recipient List Member Schemas
# ---------------------------------------------------------------------------

class RecipientListMemberCreate(BaseModel):
    """Payload to add a new member contact to a recipient list."""
    email: str = Field(..., description="Recipient email address")
    first_name: Optional[str] = Field(None, max_length=100, description="Optional first name")
    last_name: Optional[str] = Field(None, max_length=100, description="Optional last name")

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        return normalize_and_validate_email(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_optional_names(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


class RecipientListMemberUpdate(BaseModel):
    """Payload to update an existing member contact."""
    email: Optional[str] = Field(None, description="Updated recipient email address")
    first_name: Optional[str] = Field(None, max_length=100, description="Optional first name")
    last_name: Optional[str] = Field(None, max_length=100, description="Optional last name")

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return normalize_and_validate_email(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_optional_names(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


class RecipientListMemberResponse(BaseModel):
    """Response schema for a single recipient list member."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RecipientListMemberPaginationResponse(BaseModel):
    """Paginated response for recipient list members."""
    items: List[RecipientListMemberResponse]
    total: int
    limit: int
    offset: int


class RecipientListImportResponse(BaseModel):
    """Summary response for bulk CSV member import."""
    total_rows: int
    imported_count: int
    file_duplicates_count: int
    existing_duplicates_count: int
    invalid_rows_count: int
    invalid_rows: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Recipient List Schemas
# ---------------------------------------------------------------------------

class RecipientListCreate(BaseModel):
    """Payload to create a new reusable recipient list."""
    name: str = Field(..., max_length=255, description="Name of the recipient list")
    description: Optional[str] = Field(None, max_length=2000, description="Optional list description")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("List name must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("List name cannot be empty")
        if len(stripped) > 255:
            raise ValueError("List name cannot exceed 255 characters")
        return stripped

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


class RecipientListUpdate(BaseModel):
    """Payload to update an existing recipient list."""
    name: Optional[str] = Field(None, max_length=255, description="Updated name of the recipient list")
    description: Optional[str] = Field(None, max_length=2000, description="Updated list description")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("List name cannot be empty")
        if len(stripped) > 255:
            raise ValueError("List name cannot exceed 255 characters")
        return stripped

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


class RecipientListResponse(BaseModel):
    """Response schema for a recipient list."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    description: Optional[str] = None
    created_by_user_id: Optional[int] = None
    recipient_count: int = 0
    created_at: datetime
    updated_at: datetime


class RecipientListPaginationResponse(BaseModel):
    """Paginated response for recipient lists."""
    items: List[RecipientListResponse]
    total: int
    limit: int
    offset: int
