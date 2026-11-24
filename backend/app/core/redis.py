import sys
import urllib.parse
import redis.asyncio as aioredis
from app.core.config import settings

# Global async redis connection pool
redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Get or initialize the async Redis client."""
    global redis_client
    if redis_client is None:
        # Strict safety interlock: fail-closed if pytest resolves to DB 0
        if "pytest" in sys.modules:
            parsed = urllib.parse.urlparse(settings.REDIS_URL)
            db_part = parsed.path.lstrip("/")
            db_num = int(db_part) if db_part.isdigit() else 0
            if db_num == 0:
                raise RuntimeError(
                    "FATAL SAFETY INTERLOCK: pytest resolved Redis to protected DB 0! "
                    "Tests must use an isolated non-zero database (DB 15)."
                )

        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def check_redis_connection() -> bool:
    """Check if Redis connection is active and responsive."""
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception:
        return False

