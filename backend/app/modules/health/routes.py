from fastapi import APIRouter, status
from sqlalchemy import text
from app.core.config import settings
from app.core.database import async_engine
from app.core.redis import check_redis_connection
from app.modules.health.schemas import HealthResponse, ServiceStatus

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Comprehensive system health check",
)
async def get_health() -> HealthResponse:
    """Check application health and backing service connections."""
    db_status = "disconnected"
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    redis_ok = await check_redis_connection()
    redis_status = "connected" if redis_ok else "disconnected"

    overall_status = "ok" if (db_status == "connected" and redis_status == "connected") else "degraded"

    return HealthResponse(
        status=overall_status,
        app_name=settings.PROJECT_NAME,
        environment=settings.APP_ENV,
        version="0.1.0",
        services=ServiceStatus(
            database=db_status,
            redis=redis_status,
        ),
    )


@router.get(
    "/ping",
    status_code=status.HTTP_200_OK,
    summary="Simple liveness probe",
)
async def ping() -> dict:
    """Lightweight liveness probe for load balancers and orchestrators."""
    return {"status": "pong"}
