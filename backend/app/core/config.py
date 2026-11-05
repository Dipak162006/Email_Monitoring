import os
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    PROJECT_NAME: str = "Email Monitoring System"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production-32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_KEY: str = "dev-encryption-key-32-chars-long!"

    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_async_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            # Render/Heroku compatibility: normalise postgres:// or postgresql:// to postgresql+asyncpg://
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("DATABASE_SYNC_URL", mode="before")
    @classmethod
    def assemble_sync_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            # Render/Heroku compatibility: normalise postgres:// or postgresql:// to postgresql+psycopg://
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "email_monitoring"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/email_monitoring"
    DATABASE_SYNC_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/email_monitoring"

    # Redis & Celery
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False
    SYNC_INTERVAL_MINUTES: int = 5
    MAX_SYNC_RETRIES: int = 3
    SYNC_RETRY_BACKOFF_SECONDS: int = 60
    MAX_CAMPAIGN_DELIVERY_RETRIES: int = 3
    CAMPAIGN_RETRY_BACKOFF_SECONDS: int = 60

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_ATTACHMENT_SIZE_BYTES: int = 25 * 1024 * 1024  # 25MB

    # Email Engagement Tracking (Groundwork for tracking URLs; requires HTTPS in production)
    TRACKING_BASE_URL: Optional[str] = None

    # Cross-Backend Tracking Alignment (T1.5: Server-to-server authenticated issuance)
    TRACKING_INTERNAL_SECRET: Optional[str] = None
    TRACKING_SERVICE_URL: Optional[str] = None
    TRACKING_CLIENT_TIMEOUT_SECONDS: float = 3.0

    @model_validator(mode="after")
    def validate_and_sync_runtime_settings(self) -> "Settings":
        # Derive sync database URL if DATABASE_URL was set to remote instance but sync URL was not explicitly configured
        if "localhost" not in self.DATABASE_URL and "localhost" in self.DATABASE_SYNC_URL:
            self.DATABASE_SYNC_URL = self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

        # Derive Celery broker/backend from REDIS_URL if remote Redis is configured but Celery URLs remain default
        if "localhost" not in self.REDIS_URL:
            if "localhost" in self.CELERY_BROKER_URL:
                self.CELERY_BROKER_URL = self.REDIS_URL
            if "localhost" in self.CELERY_RESULT_BACKEND:
                self.CELERY_RESULT_BACKEND = self.REDIS_URL

        is_prod = (self.APP_ENV or "").strip().lower() in ("production", "prod")
        url = (self.TRACKING_BASE_URL or "").strip()
        if is_prod:
            if not url:
                raise ValueError("TRACKING_BASE_URL is required in production environments and must use HTTPS.")
            if not url.startswith("https://"):
                raise ValueError(f"TRACKING_BASE_URL must use HTTPS in production. Got: {self.TRACKING_BASE_URL}")
        elif url and not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"TRACKING_BASE_URL must start with http:// or https://. Got: {self.TRACKING_BASE_URL}")
        return self

    def get_tracking_base_url(self) -> str:
        """Centralized resolver for public tracking base URL without trailing slash.
        
        In production, strictly requires a configured HTTPS URL.
        In development/testing, falls back to http://localhost:8000 when unset.
        """
        if self.TRACKING_BASE_URL and self.TRACKING_BASE_URL.strip():
            return self.TRACKING_BASE_URL.strip().rstrip("/")
        if (self.APP_ENV or "").strip().lower() in ("production", "prod"):
            raise ValueError("TRACKING_BASE_URL is not configured for production.")
        return "http://localhost:8000"

    def get_tracking_service_url(self) -> Optional[str]:
        """Centralized resolver for internal tracking service URL without trailing slash."""
        if self.TRACKING_SERVICE_URL and self.TRACKING_SERVICE_URL.strip():
            return self.TRACKING_SERVICE_URL.strip().rstrip("/")
        return None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
