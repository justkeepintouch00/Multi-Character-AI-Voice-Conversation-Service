from typing import Literal

from pydantic import BaseModel


class ServiceHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["character-companion-backend"] = (
        "character-companion-backend"
    )


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["connected", "disconnected"]


class ProviderStatus(BaseModel):
    configured: bool


class ProviderHealthResponse(BaseModel):
    status: Literal["ok", "error"]
    groq: ProviderStatus
    typecast: ProviderStatus
