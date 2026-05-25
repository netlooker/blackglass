from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from blackglass.schemas import RetrievalBackend, RetrievalMode


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8010, ge=1, le=65535)


class PolicySettings(BaseModel):
    respect_robots_default: bool = True
    browser_enabled: bool = False
    cloakbrowser_enabled: bool = False
    deny_local_networks: bool = True


class RetrievalSettings(BaseModel):
    default_mode: RetrievalMode = RetrievalMode.AUTO
    default_backends: list[RetrievalBackend] = Field(
        default_factory=lambda: [RetrievalBackend.SCRAPLING_HTTP],
        min_length=1,
    )
    timeout_seconds: float = Field(default=20, gt=0)
    max_body_bytes: int = Field(default=3_000_000, gt=0)
    artifact_dir: Path = Path("~/.blackglass/artifacts")

    @field_validator("artifact_dir")
    @classmethod
    def expand_artifact_dir(cls, value: Path) -> Path:
        return value.expanduser()


class DomainPolicy(BaseModel):
    allow: bool | None = None
    allowed_backends: list[RetrievalBackend] | None = None


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    domains: dict[str, DomainPolicy] = Field(default_factory=dict)
    config_path: Path | None = None

    @field_validator("domains", mode="before")
    @classmethod
    def lowercase_domain_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {str(key).lower(): entry for key, entry in value.items()}


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_path = _resolve_config_path(config_path)
    if resolved_path is None:
        return Settings()

    with resolved_path.open("rb") as handle:
        raw = tomllib.load(handle)

    settings = Settings.model_validate(raw)
    settings.config_path = resolved_path
    return settings


def _resolve_config_path(config_path: str | Path | None) -> Path | None:
    candidate = config_path or os.getenv("BLACKGLASS_CONFIG")
    if not candidate:
        return None

    path = Path(candidate).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Blackglass config not found: {path}")
    if not path.is_file():
        raise ValueError(f"Blackglass config path is not a file: {path}")
    return path


def settings_summary(settings: Settings) -> dict[str, Any]:
    return {
        "config_path": str(settings.config_path) if settings.config_path else None,
        "artifact_dir": str(settings.retrieval.artifact_dir),
        "browser_enabled": settings.policy.browser_enabled,
        "cloakbrowser_enabled": settings.policy.cloakbrowser_enabled,
        "respect_robots_default": settings.policy.respect_robots_default,
        "domain_policy_count": len(settings.domains),
    }
