"""Health module for system monitoring and liveness probes."""
from app.modules.health.routes import router as health_router

__all__ = ["health_router"]
