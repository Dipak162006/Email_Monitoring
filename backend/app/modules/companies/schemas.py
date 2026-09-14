from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.modules.companies.models import CompanyRole


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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyMemberAdd(BaseModel):
    """Request schema for inviting/adding an existing user to a company."""
    email: EmailStr
    role: CompanyRole = CompanyRole.MEMBER
