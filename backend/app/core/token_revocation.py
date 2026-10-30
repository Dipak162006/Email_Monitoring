import hashlib
import time
from typing import Dict, Optional
import jwt
from app.core.config import settings
from app.core.redis import get_redis_client

# In-memory fallback dictionary for token revocation: {token_identifier: exp_timestamp}
_fallback_revoked_tokens: Dict[str, float] = {}


def get_token_identifier(token: str, payload: Optional[dict] = None) -> str:
    """Return a unique identifier for a token.
    Uses 'jti' if available in the payload or token, otherwise computes SHA-256 hash.
    """
    if payload and "jti" in payload:
        return str(payload["jti"])
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        if "jti" in unverified:
            return str(unverified["jti"])
    except Exception:
        pass
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def revoke_refresh_token(token: str) -> None:
    """Revoke a refresh token server-side so it cannot be used again."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        exp = unverified.get("exp")
        token_id = unverified.get("jti") or hashlib.sha256(token.encode("utf-8")).hexdigest()
    except Exception:
        exp = None
        token_id = hashlib.sha256(token.encode("utf-8")).hexdigest()

    now = time.time()
    ttl = int(exp - now) if exp and exp > now else (settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    if ttl <= 0:
        ttl = 300

    # 1. Update in-memory fallback
    _fallback_revoked_tokens[token_id] = now + ttl

    # 2. Update Redis
    try:
        redis = get_redis_client()
        await redis.set(f"revoked_refresh:{token_id}", "revoked", ex=ttl)
    except Exception:
        # Fallback dictionary is active
        pass


async def is_refresh_token_revoked(token: str) -> bool:
    """Check whether a refresh token has been revoked."""
    token_id = get_token_identifier(token)

    # 1. Check in-memory fallback first
    now = time.time()
    if token_id in _fallback_revoked_tokens:
        exp = _fallback_revoked_tokens[token_id]
        if exp > now:
            return True
        else:
            del _fallback_revoked_tokens[token_id]

    # 2. Check Redis
    try:
        redis = get_redis_client()
        exists = await redis.exists(f"revoked_refresh:{token_id}")
        return bool(exists)
    except Exception:
        return False

