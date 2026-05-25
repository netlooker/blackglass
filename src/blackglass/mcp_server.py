from __future__ import annotations

import argparse
from importlib.util import find_spec
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl, TypeAdapter

from blackglass.config import Settings, load_settings, settings_summary
from blackglass.retrieval import retrieve as run_retrieve
from blackglass.schemas import (
    RetrieveRequest,
    RetrieveResponse,
    RetrievalBackend,
    RetrievalMode,
    WaitUntil,
)

RetrievalProfile = Literal["auto", "http", "render"]


def create_mcp(
    settings: Settings | None = None,
    host: str = "127.0.0.1",
    port: int = 8011,
    path: str = "/mcp",
) -> FastMCP:
    app_settings = settings or load_settings()
    mcp = FastMCP(
        "Blackglass",
        instructions=(
            "Use Blackglass to retrieve one URL at a time under policy. "
            "Prefer compact output. Ask for HTML only when the next step needs source markup."
        ),
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool()
    def health() -> dict[str, object]:
        """Return compact Blackglass readiness and backend availability."""
        return {
            "ready": True,
            "artifact_dir": str(app_settings.retrieval.artifact_dir),
            "config_loaded": app_settings.config_path is not None,
            "backends": {
                "scrapling": find_spec("scrapling") is not None,
                "browser": find_spec("playwright") is not None,
                "cloakbrowser": find_spec("cloakbrowser") is not None,
            },
            "policy": {
                "browser_enabled": app_settings.policy.browser_enabled,
                "cloakbrowser_enabled": app_settings.policy.cloakbrowser_enabled,
                "respect_robots_default": app_settings.policy.respect_robots_default,
                "deny_local_networks": app_settings.policy.deny_local_networks,
            },
            "config": settings_summary(app_settings),
        }

    @mcp.tool()
    def retrieve(
        url: str,
        profile: RetrievalProfile = "auto",
        respect_robots: bool | None = None,
        timeout_seconds: float | None = None,
        max_body_bytes: int | None = None,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded",
        include_html: bool = False,
        include_text: bool = True,
        max_chars: int = 2000,
    ) -> dict[str, object]:
        """Retrieve a URL with compact provenance; HTML is opt-in."""
        request = _build_request(
            settings=app_settings,
            url=url,
            profile=profile,
            respect_robots=respect_robots,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
            wait_until=wait_until,
        )
        response = run_retrieve(request, app_settings)
        return _compact_response(
            response,
            include_html=include_html,
            include_text=include_text,
            max_chars=max_chars,
        )

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Blackglass MCP server.")
    parser.add_argument("--config", help="Path to a Blackglass TOML config file.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport to use.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Streamable HTTP host.")
    parser.add_argument("--port", type=int, default=8011, help="Streamable HTTP port.")
    parser.add_argument("--path", default="/mcp", help="Streamable HTTP path.")
    args = parser.parse_args()

    mcp = create_mcp(
        load_settings(args.config),
        host=args.host,
        port=args.port,
        path=args.path,
    )
    mcp.run(transport=args.transport)


def _build_request(
    settings: Settings,
    url: str,
    profile: RetrievalProfile,
    respect_robots: bool | None,
    timeout_seconds: float | None,
    max_body_bytes: int | None,
    wait_until: str,
) -> RetrieveRequest:
    backends = _profile_backends(profile)
    mode = _profile_mode(profile)
    return RetrieveRequest(
        url=_validate_url(url),
        mode=mode,
        preferred_backends=backends,
        respect_robots=(
            settings.policy.respect_robots_default
            if respect_robots is None
            else respect_robots
        ),
        timeout_seconds=timeout_seconds or settings.retrieval.timeout_seconds,
        max_body_bytes=max_body_bytes or settings.retrieval.max_body_bytes,
        wait_until=WaitUntil(wait_until),
    )


def _profile_backends(profile: RetrievalProfile) -> list[RetrievalBackend]:
    if profile == "http":
        return [RetrievalBackend.SCRAPLING_HTTP]
    if profile == "render":
        return [RetrievalBackend.CLOAKBROWSER, RetrievalBackend.SCRAPLING_DYNAMIC]
    return [RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]


def _profile_mode(profile: RetrievalProfile) -> RetrievalMode:
    if profile == "http":
        return RetrievalMode.HTTP_ONLY
    if profile == "render":
        return RetrievalMode.RENDER_ONLY
    return RetrievalMode.AUTO


MAX_COMPACT_CHARS = 20_000


def _compact_response(
    response: RetrieveResponse,
    include_html: bool,
    include_text: bool,
    max_chars: int,
) -> dict[str, object]:
    limit = max(0, min(max_chars, MAX_COMPACT_CHARS))
    warnings = list(response.warnings)
    if max_chars > MAX_COMPACT_CHARS:
        warnings.append(f"max_chars_clamped_to_{MAX_COMPACT_CHARS}")
    payload: dict[str, object] = {
        "artifact_id": response.artifact_id,
        "status": response.status,
        "url": response.url,
        "final_url": response.final_url,
        "status_code": response.status_code,
        "content_type": response.content_type,
        "backend": response.backend,
        "rendered": response.rendered,
        "warnings": warnings,
        "policy": response.policy.model_dump(),
        "timing": response.timing.model_dump(),
    }
    if include_text:
        payload["text"] = _truncate(response.text, limit)
    if include_html:
        payload["html"] = _truncate(response.html, limit)
    return payload


def _truncate(value: str | None, max_chars: int) -> str | None:
    if value is None or len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n...[truncated]"


def _validate_url(url: str) -> AnyHttpUrl:
    return TypeAdapter(AnyHttpUrl).validate_python(url)


if __name__ == "__main__":
    main()
