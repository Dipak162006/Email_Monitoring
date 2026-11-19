"""Security and cryptography utilities.
Provides password hashing via bcrypt and JWT token generation/validation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import uuid
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


def create_refresh_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    jti: Optional[str] = None,
) -> str:
    """Generate a signed JWT refresh token for session renewal."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    token_jti = jti or uuid.uuid4().hex
    to_encode = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "refresh",
        "jti": token_jti,
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
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
    if payload.get("type") and payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type: expected access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a signed JWT refresh token.
    
    Raises:
        jwt.ExpiredSignatureError: When the token expiration has passed.
        jwt.InvalidTokenError: When the signature or token structure is invalid.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Invalid token type: expected refresh token")
    return payload


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


def create_unsubscribe_token(
    company_id: int,
    email: str,
    campaign_id: Optional[int] = None,
    recipient_id: Optional[int] = None,
    delivery_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate a signed, tamper-proof JWT token for email unsubscription.
    
    Protects recipient privacy by Fernet-encrypting email address to ensure
    no PII is visible in the URL or Base64 payload.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=365))

    clean_email = email.strip().lower() if email else ""
    enc_email = encrypt_credential(clean_email) if clean_email else None

    to_encode = {
        "company_id": company_id,
        "campaign_id": campaign_id,
        "recipient_id": recipient_id,
        "delivery_id": delivery_id,
        "type": "unsubscribe",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if enc_email:
        to_encode["enc_email"] = enc_email
    else:
        to_encode["email"] = clean_email
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_unsubscribe_token(token: str) -> dict:
    """Decode and validate a signed unsubscribe token.
    
    Raises:
        jwt.ExpiredSignatureError: When the token has expired.
        jwt.InvalidTokenError: When the token is invalid, tampered with, or of wrong type.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "unsubscribe":
        raise jwt.InvalidTokenError("Invalid token type for unsubscription")
    if "company_id" not in payload:
        raise jwt.InvalidTokenError("Missing required unsubscribe claims")

    # Securely resolve recipient email from encrypted claim or legacy plain claim
    enc_email = payload.get("enc_email")
    if enc_email:
        payload["email"] = decrypt_credential(enc_email) or enc_email
    elif "email" in payload:
        payload["email"] = payload["email"]
    else:
        payload["email"] = None

    return payload


def build_unsubscribe_url(
    company_id: int,
    email: str,
    campaign_id: Optional[int] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    recipient_id: Optional[int] = None,
    delivery_id: Optional[int] = None,
) -> str:
    """Construct the full RFC 8058 one-click unsubscribe URL with signed or opaque token."""
    unsub_token = token or create_unsubscribe_token(
        company_id=company_id,
        email=email,
        campaign_id=campaign_id,
        recipient_id=recipient_id,
        delivery_id=delivery_id,
    )
    if base_url:
        base = base_url
    else:
        tracking_base = getattr(settings, "TRACKING_BASE_URL", None)
        if tracking_base and tracking_base.strip():
            base = tracking_base.strip()
        else:
            base = getattr(settings, "BACKEND_URL", "http://localhost:8000")
    return f"{base.rstrip('/')}/api/v1/public/unsubscribe/{unsub_token}"


