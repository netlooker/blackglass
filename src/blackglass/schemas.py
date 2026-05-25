from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field


class RetrievalBackend(StrEnum):
    HTTP = "http"
    SCRAPLING_HTTP = "scrapling_http"
    SCRAPLING_DYNAMIC = "scrapling_dynamic"
    CLOAKBROWSER = "cloakbrowser"


class RetrievalMode(StrEnum):
    HTTP_ONLY = "http_only"
    RENDER_ONLY = "render_only"
    AUTO = "auto"


class WaitUntil(StrEnum):
    COMMIT = "commit"
    DOMCONTENTLOADED = "domcontentloaded"
    LOAD = "load"
    NETWORKIDLE = "networkidle"


class RetrievalStatus(StrEnum):
    RETRIEVED = "retrieved"
    BLOCKED = "blocked"
    FAILED = "failed"


class RetrieveRequest(BaseModel):
    url: AnyHttpUrl
    mode: RetrievalMode = RetrievalMode.AUTO
    preferred_backends: list[RetrievalBackend] = Field(
        default_factory=lambda: [RetrievalBackend.SCRAPLING_HTTP]
    )
    respect_robots: bool = True
    timeout_seconds: float = Field(default=20, gt=0, le=120)
    max_body_bytes: int = Field(default=3_000_000, gt=0, le=50_000_000)
    wait_until: WaitUntil = WaitUntil.DOMCONTENTLOADED


class PolicyDecision(BaseModel):
    allowed: bool = True
    robots_allowed: bool | None = None
    allowlist_matched: bool = False
    denylist_matched: bool = False
    backend_allowed: bool = True
    local_network_blocked: bool = False


class TimingInfo(BaseModel):
    started_at: float
    duration_ms: int = Field(ge=0)


class RetrieveResponse(BaseModel):
    artifact_id: str
    url: str
    final_url: str | None = None
    status: RetrievalStatus
    status_code: int | None = None
    content_type: str | None = None
    backend: RetrievalBackend
    rendered: bool = False
    html: str | None = None
    text: str | None = None
    warnings: list[str] = Field(default_factory=list)
    policy: PolicyDecision
    timing: TimingInfo


class HealthResponse(BaseModel):
    ready: bool
    artifact_dir: str
    browser_available: bool
    cloakbrowser_available: bool
    scrapling_available: bool
    config_loaded: bool
    config: dict[str, Any]
