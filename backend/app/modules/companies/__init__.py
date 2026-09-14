"""Companies and multi-tenant access module."""
from app.modules.companies.routes import router as companies_router

__all__ = ["companies_router"]
