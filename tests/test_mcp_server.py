from blackglass.config import Settings
import asyncio

from blackglass.mcp_server import (
    _build_request,
    _compact_response,
    _profile_backends,
    _profile_mode,
    create_mcp,
)
from blackglass.retrieval import retrieve
from blackglass.schemas import RetrievalBackend, RetrievalMode


class FakePage:
    status = 200
    url = "https://example.com/article"
    headers = {"content-type": "text/html"}
    body = b"<html><body>hello world</body></html>"
    encoding = "utf-8"

    def get_all_text(self) -> str:
        return "hello world"


def test_profile_mappings_are_small_model_friendly() -> None:
    assert _profile_mode("auto") == RetrievalMode.AUTO
    assert _profile_mode("http") == RetrievalMode.HTTP_ONLY
    assert _profile_mode("render") == RetrievalMode.RENDER_ONLY
    assert _profile_backends("auto") == [
        RetrievalBackend.SCRAPLING_HTTP,
        RetrievalBackend.CLOAKBROWSER,
    ]
    assert _profile_backends("http") == [RetrievalBackend.SCRAPLING_HTTP]
    assert _profile_backends("render") == [
        RetrievalBackend.CLOAKBROWSER,
        RetrievalBackend.SCRAPLING_DYNAMIC,
    ]


def test_create_mcp_accepts_explicit_http_binding() -> None:
    mcp = create_mcp(Settings(), host="0.0.0.0", port=8011, path="/mcp")

    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 8011
    assert mcp.settings.streamable_http_path == "/mcp"


def test_mcp_tool_registry_exposes_only_agent_friendly_tools() -> None:
    async def run() -> None:
        tools = await create_mcp(Settings()).list_tools()
        assert sorted(tool.name for tool in tools) == ["health", "retrieve"]

    asyncio.run(run())


def test_mcp_health_tool_returns_structured_status() -> None:
    async def run() -> None:
        _content, structured = await create_mcp(Settings()).call_tool("health", {})
        assert structured["ready"] is True
        assert set(structured["backends"]) == {"browser", "cloakbrowser", "scrapling"}
        assert structured["policy"]["deny_local_networks"] is True

    asyncio.run(run())


def test_mcp_retrieve_request_uses_settings_defaults() -> None:
    settings = Settings()

    request = _build_request(
        settings=settings,
        url="https://example.com/article",
        profile="auto",
        respect_robots=None,
        timeout_seconds=None,
        max_body_bytes=None,
        wait_until="domcontentloaded",
    )

    assert str(request.url) == "https://example.com/article"
    assert request.mode == RetrievalMode.AUTO
    assert request.timeout_seconds == settings.retrieval.timeout_seconds
    assert request.max_body_bytes == settings.retrieval.max_body_bytes
    assert request.respect_robots is True


def test_compact_response_omits_html_by_default(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())
    settings = Settings()
    request = _build_request(
        settings=settings,
        url="https://example.com/article",
        profile="auto",
        respect_robots=None,
        timeout_seconds=None,
        max_body_bytes=None,
        wait_until="domcontentloaded",
    )
    response = retrieve(request, settings)
    response.html = "<html>" + ("x" * 5000) + "</html>"
    response.text = "hello world"

    compact = _compact_response(
        response,
        include_html=False,
        include_text=True,
        max_chars=100,
    )

    assert "html" not in compact
    assert compact["text"] == "hello world"
    assert compact["artifact_id"].startswith("bg_")


def test_compact_response_includes_truncated_html_when_requested(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())
    settings = Settings()
    request = _build_request(
        settings=settings,
        url="https://example.com/article",
        profile="auto",
        respect_robots=None,
        timeout_seconds=None,
        max_body_bytes=None,
        wait_until="domcontentloaded",
    )
    response = retrieve(request, settings)
    response.html = "<html>" + ("x" * 5000) + "</html>"

    compact = _compact_response(
        response,
        include_html=True,
        include_text=False,
        max_chars=100,
    )

    assert "text" not in compact
    assert str(compact["html"]).endswith("\n...[truncated]")
    assert len(str(compact["html"])) < 130


def test_compact_response_clamps_max_chars(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())
    settings = Settings()
    request = _build_request(
        settings=settings,
        url="https://example.com/article",
        profile="auto",
        respect_robots=None,
        timeout_seconds=None,
        max_body_bytes=None,
        wait_until="domcontentloaded",
    )
    response = retrieve(request, settings)
    response.text = "x" * 30_000

    compact = _compact_response(
        response,
        include_html=False,
        include_text=True,
        max_chars=100_000,
    )

    assert str(compact["text"]).endswith("\n...[truncated]")
    assert len(str(compact["text"])) == 20_015
    assert "max_chars_clamped_to_20000" in compact["warnings"]
