import redis.asyncio as aioredis
from app.core.config import settings

# Global async redis connection pool
redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Get or initialize the async Redis client."""
    global redis_client
    if redis_client is None:
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
