import sys
from types import SimpleNamespace

from blackglass.config import DomainPolicy, PolicySettings, Settings
from blackglass.retrieval import _select_backend, retrieve
from blackglass.schemas import (
    RetrieveRequest,
    RetrievalBackend,
    RetrievalMode,
    RetrievalStatus,
)


LONG_TEXT = (
    "Cyberpunk books and retrieval tests need enough visible article text to avoid "
    "the automatic browser fallback heuristic. Neuromancer, Snow Crash, and other "
    "recommendations provide stable page-like content for the fast HTTP path. "
    "This fixture deliberately exceeds the configured two hundred character "
    "minimum so the service treats it as useful retrieved content."
)


class FakePage:
    status = 200
    url = "https://example.com/article"
    headers = {"content-type": "text/html; charset=utf-8"}
    body = f"<html><body><article>{LONG_TEXT}</article></body></html>".encode()
    encoding = "utf-8"

    def get_all_text(self) -> str:
        return LONG_TEXT


class ThinPage(FakePage):
    body = b"<html><body><p>short text</p></body></html>"

    def get_all_text(self) -> str:
        return "short text"


class AppShellPage(FakePage):
    body = (
        b'<html><body><div id="root"></div><script></script><script></script>'
        b"<script></script></body></html>"
    )

    def get_all_text(self) -> str:
        return ""


def _request(backends: list[RetrievalBackend]) -> RetrieveRequest:
    return RetrieveRequest(
        url="https://example.com/article",
        preferred_backends=backends,
    )


def _browser_settings() -> Settings:
    return Settings(
        policy=PolicySettings(browser_enabled=True, cloakbrowser_enabled=True)
    )


def _install_fake_cloakbrowser(monkeypatch, *, fail: bool = False) -> None:
    class FakeResponse:
        status = 200
        headers = {"content-type": "text/html"}

    class FakeLocator:
        def inner_text(self, timeout: int) -> str:
            return LONG_TEXT

    class FakeBrowserPage:
        url = "https://example.com/rendered"

        def goto(self, *args, **kwargs):
            if fail:
                raise RuntimeError("browser unavailable")
            return FakeResponse()

        def content(self) -> str:
            return f"<html><body><article>{LONG_TEXT}</article></body></html>"

        def locator(self, selector: str):
            return FakeLocator()

        def close(self) -> None:
            return None

    class FakeContext:
        def new_page(self) -> FakeBrowserPage:
            return FakeBrowserPage()

        def close(self) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        SimpleNamespace(launch_context=lambda: FakeContext()),
    )


def test_policy_blocked_retrieval_returns_blocked() -> None:
    settings = Settings(domains={"example.com": DomainPolicy(allow=False)})

    response = retrieve(_request([RetrievalBackend.SCRAPLING_HTTP]), settings)

    assert response.status == RetrievalStatus.BLOCKED
    assert response.policy.allowed is False
    assert response.warnings == ["Retrieval blocked by policy."]


def test_allowed_retrieval_returns_scrapling_content(
    monkeypatch,
) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())

    response = retrieve(_request([RetrievalBackend.SCRAPLING_HTTP]), Settings())

    assert response.status == RetrievalStatus.RETRIEVED
    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert response.backend == RetrievalBackend.SCRAPLING_HTTP
    assert response.rendered is False
    assert response.html
    assert response.text == LONG_TEXT
    assert response.warnings == []


def test_http_retrieval_failure_returns_failed_warning(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    def fail(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(Fetcher, "get", fail)

    response = retrieve(_request([RetrievalBackend.SCRAPLING_HTTP]), Settings())

    assert response.status == RetrievalStatus.FAILED
    assert response.status_code is None
    assert response.warnings == [
        "HTTP retrieval failed: RuntimeError: network unavailable",
        "render_fallback_not_available: http_failed",
    ]


def test_backend_selection_skips_browser_when_disabled() -> None:
    settings = Settings()
    request = _request(
        [RetrievalBackend.CLOAKBROWSER, RetrievalBackend.SCRAPLING_HTTP]
    )

    backend = _select_backend(request, settings)

    assert backend == RetrievalBackend.SCRAPLING_HTTP


def test_backend_selection_uses_cloakbrowser_when_enabled() -> None:
    settings = Settings(
        policy=PolicySettings(browser_enabled=True, cloakbrowser_enabled=True)
    )
    request = _request(
        [RetrievalBackend.CLOAKBROWSER, RetrievalBackend.SCRAPLING_HTTP]
    )

    backend = _select_backend(request, settings)

    assert backend == RetrievalBackend.CLOAKBROWSER


def test_rendered_flag_is_true_for_browser_backend(monkeypatch) -> None:
    _install_fake_cloakbrowser(monkeypatch)
    settings = _browser_settings()

    response = retrieve(
        RetrieveRequest(
            url="https://example.com/article",
            mode=RetrievalMode.RENDER_ONLY,
            preferred_backends=[RetrievalBackend.CLOAKBROWSER],
        ),
        settings,
    )

    assert response.rendered is True
    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert response.final_url == "https://example.com/rendered"


def test_access_restriction_status_adds_warning(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    class RestrictedPage(FakePage):
        status = 403
        body = b"<html><body>You've been blocked by network security.</body></html>"

        def get_all_text(self) -> str:
            return "You've been blocked by network security."

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: RestrictedPage())

    response = retrieve(_request([RetrievalBackend.SCRAPLING_HTTP]), Settings())

    assert response.status == RetrievalStatus.RETRIEVED
    assert response.status_code == 403
    assert "HTTP status may indicate access restriction: 403." in response.warnings
    assert (
        "Content appears to contain bot-restriction or verification language."
        in response.warnings
    )


def test_auto_good_http_content_does_not_fallback(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.SCRAPLING_HTTP
    assert response.rendered is False
    assert response.warnings == []


def test_auto_http_403_triggers_cloakbrowser_fallback(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    class RestrictedPage(FakePage):
        status = 403
        body = b"<html><body>You've been blocked by network security.</body></html>"

        def get_all_text(self) -> str:
            return "You've been blocked by network security."

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: RestrictedPage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert response.rendered is True
    assert response.status_code == 200
    assert "http_status_triggered_render_fallback: 403" in response.warnings


def test_bot_restriction_text_triggers_cloakbrowser_fallback(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    class BotPage(FakePage):
        body = b"<html><body>Please verify you are human before continuing.</body></html>"

        def get_all_text(self) -> str:
            return "Please verify you are human before continuing. " + LONG_TEXT

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: BotPage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert "bot_restriction_content_triggered_render_fallback" in response.warnings


def test_low_text_triggers_cloakbrowser_fallback(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: ThinPage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert "low_text_triggered_render_fallback" in response.warnings


def test_app_shell_triggers_cloakbrowser_fallback(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: AppShellPage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert "app_shell_triggered_render_fallback" in response.warnings


def test_http_only_never_falls_back(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: ThinPage())
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        RetrieveRequest(
            url="https://example.com/article",
            mode=RetrievalMode.HTTP_ONLY,
            preferred_backends=[
                RetrievalBackend.SCRAPLING_HTTP,
                RetrievalBackend.CLOAKBROWSER,
            ],
        ),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.SCRAPLING_HTTP
    assert response.rendered is False
    assert response.warnings == []


def test_render_only_uses_cloakbrowser_directly(monkeypatch) -> None:
    _install_fake_cloakbrowser(monkeypatch)

    response = retrieve(
        RetrieveRequest(
            url="https://example.com/article",
            mode=RetrievalMode.RENDER_ONLY,
            preferred_backends=[RetrievalBackend.CLOAKBROWSER],
        ),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert response.rendered is True
    assert response.text == LONG_TEXT


def test_render_only_without_browser_returns_failed_warning() -> None:
    response = retrieve(
        RetrieveRequest(
            url="https://example.com/article",
            mode=RetrievalMode.RENDER_ONLY,
            preferred_backends=[RetrievalBackend.CLOAKBROWSER],
        ),
        Settings(),
    )

    assert response.status == RetrievalStatus.FAILED
    assert response.backend == RetrievalBackend.CLOAKBROWSER
    assert response.warnings == [
        "Render requested but no browser backend is enabled or allowed."
    ]


def test_scrapling_dynamic_is_not_implemented_by_cloakbrowser() -> None:
    response = retrieve(
        RetrieveRequest(
            url="https://example.com/article",
            preferred_backends=[RetrievalBackend.SCRAPLING_DYNAMIC],
        ),
        Settings(policy=PolicySettings(browser_enabled=True)),
    )

    assert response.status == RetrievalStatus.FAILED
    assert response.backend == RetrievalBackend.SCRAPLING_DYNAMIC
    assert response.warnings == [
        "Retrieval backend is not implemented yet: scrapling_dynamic."
    ]


def test_browser_disabled_records_no_fallback_warning(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: ThinPage())

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        Settings(),
    )

    assert response.backend == RetrievalBackend.SCRAPLING_HTTP
    assert response.rendered is False
    assert "render_fallback_not_available: low_text" in response.warnings


def test_browser_failure_returns_http_result_with_warning(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: ThinPage())
    _install_fake_cloakbrowser(monkeypatch, fail=True)

    response = retrieve(
        _request([RetrievalBackend.SCRAPLING_HTTP, RetrievalBackend.CLOAKBROWSER]),
        _browser_settings(),
    )

    assert response.backend == RetrievalBackend.SCRAPLING_HTTP
    assert response.text == "short text"
    assert "low_text_triggered_render_fallback" in response.warnings
    assert "render_fallback_failed_returning_http_result" in response.warnings
    assert any(warning.startswith("Browser retrieval failed:") for warning in response.warnings)
