"""Security utilities placeholder for M1.
Full password hashing and JWT token handling will be expanded in Milestone M2.
"""
import hmac
import hashlib
from app.core.config import settings


def verify_secret_key() -> bool:
    """Verify that a valid secret key is configured."""
    return bool(settings.SECRET_KEY and len(settings.SECRET_KEY) >= 16)
