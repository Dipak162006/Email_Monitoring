from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.modules.domains.models import DomainVerificationStatus

# RFC 1035 / RFC 1123 label regex: 1 to 63 alphanumeric or hyphen characters, not starting or ending with hyphen
LABEL_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
# DKIM selector regex: 1 to 100 alphanumeric, hyphen, underscore, or dot characters
SELECTOR_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,98}[a-zA-Z0-9])?$")


def normalize_domain_name(value: str) -> str:
    """Deterministically normalizes and validates a domain name string.
    
    Rules:
    1. Trim surrounding whitespace.
    2. Convert to lowercase.
    3. Remove an optional trailing dot.
    4. Reject email addresses containing '@'.
    5. Reject URL protocols (e.g., http://, https://).
    6. Reject paths and slashes ('/' or '\\').
    7. Reject values shorter than 3 characters.
    8. Reject values longer than 255 characters.
    9. Reject bare hostnames without a dot (e.g., localhost).
    10. Validate legitimate hostname/domain-label structure (RFC 1035/1123).
    """
    if not isinstance(value, str):
        raise ValueError("Domain name must be a string")

    # 1. Trim surrounding whitespace
    domain = value.strip()

    # 4. Reject email addresses containing '@'
    if "@" in domain:
        raise ValueError("Domain name must not contain '@' (email addresses are not permitted)")

    # 5. Reject URL protocols
    if domain.lower().startswith(("http://", "https://", "ftp://", "mailto:")) or "://" in domain:
        raise ValueError("Domain name must not include a URL protocol")

    # 6. Reject paths and slashes
    if "/" in domain or "\\" in domain:
        raise ValueError("Domain name must not contain path slashes")

    # 2. Convert to lowercase
    domain = domain.lower()

    # 3. Remove optional trailing dot
    if domain.endswith("."):
        domain = domain[:-1]

    # 7. Reject values shorter than 3 characters
    if len(domain) < 3:
        raise ValueError("Domain name is too short (minimum 3 characters)")

    # 8. Reject values longer than 255 characters
    if len(domain) > 255:
        raise ValueError("Domain name is too long (maximum 255 characters)")

    # 9. Reject bare hostnames without a dot
    if "." not in domain:
        raise ValueError("Domain name must contain at least one dot (bare hostnames are not allowed)")

    # 10. Validate legitimate hostname/domain-label structure
    labels = domain.split(".")
    for label in labels:
        if not label:
            raise ValueError("Domain name cannot contain empty labels")
        if len(label) > 63:
            raise ValueError("Domain label exceeds maximum length of 63 characters")
        if not LABEL_REGEX.match(label):
            raise ValueError(
                f"Domain label '{label}' contains invalid characters (must be alphanumeric and hyphens, cannot start or end with a hyphen)"
            )

    # Reject purely numeric TLDs (e.g. 192.168.1.1)
    if labels[-1].isdigit():
        raise ValueError("Top-level domain cannot be purely numeric")

    return domain


def validate_dkim_selector(v: Optional[str]) -> Optional[str]:
    """Validate and clean optional DKIM selector configuration."""
    if v is None:
        return None
    trimmed = v.strip()
    if not trimmed:
        return None
    if len(trimmed) > 100:
        raise ValueError("DKIM selector must not exceed 100 characters")
    if not SELECTOR_REGEX.match(trimmed):
        raise ValueError(
            "DKIM selector contains invalid characters (must be alphanumeric, dot, underscore, or hyphen; cannot start or end with a separator)"
        )
    return trimmed


class DomainCreate(BaseModel):
    """Request schema for creating a new sending domain."""
    domain_name: str = Field(..., description="Fully qualified domain name (FQDN)")
    dkim_selector: Optional[str] = Field(default=None, description="DKIM key selector (optional)")

    @field_validator("domain_name")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        return normalize_domain_name(v)

    @field_validator("dkim_selector")
    @classmethod
    def validate_selector(cls, v: Optional[str]) -> Optional[str]:
        return validate_dkim_selector(v)


class DomainUpdate(BaseModel):
    """Request schema for updating domain configuration.
    
    Domain name is strictly immutable after creation.
    """
    dkim_selector: Optional[str] = Field(default=None, description="DKIM key selector")

    model_config = ConfigDict(extra="forbid")

    @field_validator("dkim_selector")
    @classmethod
    def validate_selector(cls, v: Optional[str]) -> Optional[str]:
        return validate_dkim_selector(v)


class DomainRead(BaseModel):
    """Response schema for domain details and DNS verification status."""
    id: int
    company_id: int
    domain_name: str
    verification_status: DomainVerificationStatus
    spf_status: DomainVerificationStatus
    dkim_status: DomainVerificationStatus
    dmarc_status: DomainVerificationStatus
    mx_status: DomainVerificationStatus
    dkim_selector: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    verification_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
