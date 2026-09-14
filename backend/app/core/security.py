"""Security and cryptography utilities.
Provides password hashing via bcrypt and JWT token generation/validation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import bcrypt
import jwt
from app.core.config import settings


def get_password_hash(password: str) -> str:
    """Hash a plaintext password securely using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate a signed JWT access token for an authenticated subject."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a signed JWT token.
    
    Raises:
        jwt.ExpiredSignatureError: When the token expiration has passed.
        jwt.InvalidTokenError: When the signature or token structure is invalid.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )


def _get_fernet():
    """Derive a 32-byte Fernet key deterministically from settings.ENCRYPTION_KEY."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    key_bytes = hashlib.sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_credential(plaintext: Optional[str]) -> Optional[str]:
    """Reversibly encrypt a sensitive credential (e.g. SMTP/IMAP password) for storage at rest."""
    if not plaintext:
        return None
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credential(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a stored credential for backend SMTP/IMAP protocol usage."""
    if not ciphertext:
        return None
    try:
        fernet = _get_fernet()
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return None
