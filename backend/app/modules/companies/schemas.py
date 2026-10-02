from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.modules.companies.models import CompanyRole, InvitationStatus


class CompanyCreate(BaseModel):
    """Request schema for creating a new company organization."""
    name: str = Field(min_length=1, max_length=255, description="Company organization name")


class CompanyRead(BaseModel):
    """Response schema for public company information."""
    id: int
    name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyWithRoleRead(CompanyRead):
    """Response schema for company information including the user's role."""
    role: CompanyRole


class CompanyMemberRead(BaseModel):
    """Response schema for a company member's information."""
    id: int
    company_id: int
    user_id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: CompanyRole
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyMemberAdd(BaseModel):
    """Request schema for inviting/adding an existing user to a company."""
    email: EmailStr
    role: CompanyRole = CompanyRole.MEMBER


class CompanyMemberRoleUpdate(BaseModel):
    """Request schema for updating a company member's role."""
    role: CompanyRole


class CompanyInvitationCreate(BaseModel):
    """Request schema for creating a new workspace invitation."""
    email: EmailStr
    role: CompanyRole = CompanyRole.MEMBER


class CompanyInvitationRead(BaseModel):
    """Response schema for a company invitation."""
    id: int
    company_id: int
    company_name: Optional[str] = None
    invited_email: EmailStr
    invited_user_id: Optional[int] = None
    inviter_user_id: int
    inviter_email: Optional[str] = None
    inviter_name: Optional[str] = None
    role: CompanyRole
    status: InvitationStatus
    created_at: datetime
    accepted_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserInvitationRead(BaseModel):
    """Response schema for an invitation viewed by the invited user."""
    id: int
    company_id: int
    company_name: str
    role: CompanyRole
    inviter_email: str
    inviter_name: Optional[str] = None
    status: InvitationStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


