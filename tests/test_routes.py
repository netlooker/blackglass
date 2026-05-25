from fastapi.testclient import TestClient

from blackglass.app import create_app
from blackglass.config import PolicySettings, Settings


LONG_TEXT = (
    "Cyberpunk book recommendations for agents need enough visible article content "
    "to remain on the HTTP backend during route tests. This paragraph is intentionally "
    "longer than the fallback threshold so the test verifies the normal content "
    "response rather than the thin-page browser fallback."
)


class FakePage:
    status = 200
    url = "https://example.com/article"
    headers = {"content-type": "text/html"}
    body = f"<html><body><p>{LONG_TEXT}</p></body></html>".encode()
    encoding = "utf-8"

    def get_all_text(self) -> str:
        return LONG_TEXT


def test_health_reports_skeleton_status() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["artifact_dir"]
    assert body["config_loaded"] is False
    assert set(body["config"]) >= {
        "artifact_dir",
        "browser_enabled",
        "cloakbrowser_enabled",
        "respect_robots_default",
        "domain_policy_count",
    }


def test_retrieve_validates_and_returns_content_response(monkeypatch) -> None:
    from scrapling.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: FakePage())
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/retrieve",
        json={
            "url": "https://example.com/article",
            "mode": "auto",
            "preferred_backends": ["scrapling_http", "cloakbrowser"],
            "respect_robots": True,
            "timeout_seconds": 20,
            "max_body_bytes": 3000000,
            "wait_until": "domcontentloaded",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"].startswith("bg_")
    assert body["url"] == "https://example.com/article"
    assert body["status"] == "retrieved"
    assert body["status_code"] == 200
    assert body["backend"] == "scrapling_http"
    assert body["text"] == LONG_TEXT
    assert body["policy"]["allowed"] is True
    assert body["warnings"] == []


def test_retrieve_auto_reports_cloakbrowser_after_fallback(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from scrapling.fetchers import Fetcher

    class RestrictedPage(FakePage):
        status = 403
        body = b"<html><body>You've been blocked by network security.</body></html>"

        def get_all_text(self) -> str:
            return "You've been blocked by network security."

    class FakeResponse:
        status = 200
        headers = {"content-type": "text/html"}

    class FakeLocator:
        def inner_text(self, timeout: int) -> str:
            return LONG_TEXT

    class FakeBrowserPage:
        url = "https://example.com/rendered"

        def goto(self, *args, **kwargs):
            return FakeResponse()

        def content(self) -> str:
            return f"<html><body><p>{LONG_TEXT}</p></body></html>"

        def locator(self, selector: str):
            return FakeLocator()

        def close(self) -> None:
            return None

    class FakeContext:
        def new_page(self) -> FakeBrowserPage:
            return FakeBrowserPage()

        def close(self) -> None:
            return None

    monkeypatch.setattr(Fetcher, "get", lambda *args, **kwargs: RestrictedPage())
    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        SimpleNamespace(launch_context=lambda: FakeContext()),
    )
    client = TestClient(
        create_app(
            Settings(
                policy=PolicySettings(
                    browser_enabled=True,
                    cloakbrowser_enabled=True,
                )
            )
        )
    )

    response = client.post(
        "/retrieve",
        json={
            "url": "https://example.com/article",
            "mode": "auto",
            "preferred_backends": ["scrapling_http", "cloakbrowser"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "cloakbrowser"
    assert body["rendered"] is True
    assert body["final_url"] == "https://example.com/rendered"
    assert "http_status_triggered_render_fallback: 403" in body["warnings"]


def test_retrieve_validation_failure_returns_422() -> None:
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/retrieve",
        json={"url": "not-a-url", "timeout_seconds": 20},
    )

    assert response.status_code == 422
    assert response.json()["detail"]


def test_retrieve_policy_blocked_response_for_local_url() -> None:
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/retrieve",
        json={
            "url": "http://127.0.0.1/",
            "mode": "auto",
            "preferred_backends": ["scrapling_http"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["policy"]["local_network_blocked"] is True
    assert body["warnings"] == ["Retrieval blocked by policy."]
