from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """Schema for user registration request."""
    email: EmailStr = Field(description="Unique email address for user login")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password (min 8 characters)")
    full_name: Optional[str] = Field(default=None, max_length=255, description="Full display name")


class UserLogin(BaseModel):
    """Schema for user login request."""
    email: EmailStr = Field(description="Registered login email")
    password: str = Field(description="User password")


class Token(BaseModel):
    """Schema for JWT authentication response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")


class TokenPayload(BaseModel):
    """Schema representing the decoded JWT payload."""
    sub: str
    iat: int
    exp: int
    type: str


class UserProfileUpdate(BaseModel):
    """Schema for updating personal profile information."""
    full_name: str = Field(min_length=1, max_length=255, description="Full display name")

    model_config = ConfigDict(extra="forbid")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Full name cannot be empty or whitespace only")
        if len(trimmed) > 255:
            raise ValueError("Full name must not exceed 255 characters")
        return trimmed


class UserPasswordChange(BaseModel):
    """Schema for authenticated user password change request."""
    current_password: str = Field(min_length=1, description="Current plaintext password")
    new_password: str = Field(min_length=8, max_length=128, description="New plaintext password (8-128 characters)")

    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    """Generic message response schema."""
    message: str


class UserRead(BaseModel):
    """Schema for returning public user information (no sensitive fields)."""
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
