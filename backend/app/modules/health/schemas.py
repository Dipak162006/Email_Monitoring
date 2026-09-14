from typing import Dict, Optional
from pydantic import BaseModel


class ServiceStatus(BaseModel):
    database: str
    redis: str


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    version: str
    services: ServiceStatus
