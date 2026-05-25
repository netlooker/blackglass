from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter, time
from typing import Any

from blackglass.artifacts import new_artifact_id
from blackglass.config import Settings
from blackglass.policy import evaluate_policy
from blackglass.schemas import (
    RetrieveRequest,
    RetrieveResponse,
    RetrievalBackend,
    RetrievalMode,
    RetrievalStatus,
    TimingInfo,
    WaitUntil,
)

MIN_TEXT_CHARS_FOR_HTTP = 200
BOT_RESTRICTION_MARKERS = (
    "access denied",
    "are you a robot",
    "blocked by network security",
    "captcha",
    "checking your browser",
    "cloudflare",
    "enable javascript",
    "too many requests",
    "unusual traffic",
    "verify you are human",
)


def retrieve(request: RetrieveRequest, settings: Settings) -> RetrieveResponse:
    started_at = time()
    monotonic_start = perf_counter()
    policy = evaluate_policy(request, settings)

    if not policy.allowed:
        backend = _select_backend(request, settings)
        result = _empty_result()
        status = RetrievalStatus.BLOCKED
        warnings = ["Retrieval blocked by policy."]
    else:
        backend, result, warnings = _retrieve_allowed(request, settings)
        status = _status_from_result(result)

    duration_ms = int((perf_counter() - monotonic_start) * 1000)
    return RetrieveResponse(
        artifact_id=new_artifact_id(),
        url=str(request.url),
        final_url=result["final_url"],
        status=status,
        status_code=result["status_code"],
        content_type=result["content_type"],
        backend=backend,
        rendered=_is_browser_backend(backend),
        html=result["html"],
        text=result["text"],
        warnings=warnings,
        policy=policy,
        timing=TimingInfo(started_at=started_at, duration_ms=duration_ms),
    )


def _retrieve_allowed(
    request: RetrieveRequest, settings: Settings
) -> tuple[RetrievalBackend, dict[str, Any], list[str]]:
    if request.mode is RetrievalMode.RENDER_ONLY:
        backend = _select_render_backend(request, settings)
        if backend is None:
            return (
                RetrievalBackend.CLOAKBROWSER,
                _empty_result(),
                ["Render requested but no browser backend is enabled or allowed."],
            )
        result = _retrieve_with_cloakbrowser(request)
        return backend, result, result["warnings"]

    http_backend = _select_http_backend(request)
    if http_backend is None:
        render_backend = _select_render_backend(request, settings)
        if render_backend is not None:
            result = _retrieve_with_cloakbrowser(request)
            return render_backend, result, result["warnings"]
        backend = _select_backend(request, settings)
        return (
            backend,
            _empty_result(),
            [f"Retrieval backend is not implemented yet: {backend}."],
        )

    http_result = _retrieve_with_scrapling_http(request)
    warnings = list(http_result["warnings"])
    if request.mode is RetrievalMode.HTTP_ONLY:
        return http_backend, http_result, warnings

    fallback_reason = _fallback_reason(http_result)
    if fallback_reason is None:
        return http_backend, http_result, warnings

    render_backend = _select_render_backend(request, settings)
    if render_backend is None:
        warnings.append(f"render_fallback_not_available: {fallback_reason}")
        return http_backend, http_result, warnings

    warnings.append(_fallback_trigger_warning(fallback_reason))
    render_result = _retrieve_with_cloakbrowser(request)
    if render_result["status_code"] is None and render_result["html"] is None:
        warnings.extend(render_result["warnings"])
        warnings.append("render_fallback_failed_returning_http_result")
        return http_backend, http_result, warnings

    return render_backend, render_result, warnings + render_result["warnings"]


def _select_backend(request: RetrieveRequest, settings: Settings) -> RetrievalBackend:
    for backend in request.preferred_backends:
        if backend is RetrievalBackend.CLOAKBROWSER and not settings.policy.cloakbrowser_enabled:
            continue
        if backend in {RetrievalBackend.SCRAPLING_DYNAMIC, RetrievalBackend.CLOAKBROWSER}:
            if not settings.policy.browser_enabled:
                continue
        return backend
    return settings.retrieval.default_backends[0]


def _select_http_backend(request: RetrieveRequest) -> RetrievalBackend | None:
    for backend in request.preferred_backends:
        if backend in {RetrievalBackend.HTTP, RetrievalBackend.SCRAPLING_HTTP}:
            return backend
    return None


def _select_render_backend(
    request: RetrieveRequest, settings: Settings
) -> RetrievalBackend | None:
    for backend in request.preferred_backends:
        if backend is RetrievalBackend.CLOAKBROWSER:
            if settings.policy.browser_enabled and settings.policy.cloakbrowser_enabled:
                return backend
    return None


def _is_browser_backend(backend: RetrievalBackend) -> bool:
    return backend in {RetrievalBackend.SCRAPLING_DYNAMIC, RetrievalBackend.CLOAKBROWSER}


def _status_from_result(result: dict[str, Any]) -> RetrievalStatus:
    if result["status_code"] is not None or result["html"] is not None:
        return RetrievalStatus.RETRIEVED
    return RetrievalStatus.FAILED


def _retrieve_with_scrapling_http(request: RetrieveRequest) -> dict[str, Any]:
    try:
        from scrapling.fetchers import Fetcher

        page = Fetcher.get(str(request.url), timeout=request.timeout_seconds)
    except Exception as exc:
        return {
            **_empty_result(),
            "warnings": [f"HTTP retrieval failed: {type(exc).__name__}: {exc}"],
        }

    headers = _headers(page)
    body = bytes(getattr(page, "body", b"") or b"")
    warnings: list[str] = []
    if len(body) > request.max_body_bytes:
        body = body[: request.max_body_bytes]
        warnings.append(f"Response body truncated to {request.max_body_bytes} bytes.")

    html = _decode_body(body, getattr(page, "encoding", None))
    text = _extract_text(page, html)
    status_code = getattr(page, "status", None)
    content_type = _content_type(headers)

    warnings.extend(_restriction_warnings(status_code, html, text))

    return {
        "final_url": getattr(page, "url", None) or str(request.url),
        "status_code": status_code,
        "content_type": content_type,
        "html": html,
        "text": text,
        "warnings": warnings,
    }


def _retrieve_with_cloakbrowser(request: RetrieveRequest) -> dict[str, Any]:
    context = None
    page = None
    try:
        import cloakbrowser

        context = cloakbrowser.launch_context()
        page = context.new_page()
        response = page.goto(
            str(request.url),
            wait_until=_playwright_wait_until(request.wait_until),
            timeout=int(request.timeout_seconds * 1000),
        )
        status_code = response.status if response is not None else None
        headers = response.headers if response is not None else {}
        normalized_headers = {str(k).lower(): str(v) for k, v in headers.items()}
        text = _page_body_text(page)
        html, html_warnings = _page_content(page)
        text = text or _html_to_text_fallback(html or "")
        warnings = html_warnings + _restriction_warnings(status_code, html, text)
        return {
            "final_url": page.url or str(request.url),
            "status_code": status_code,
            "content_type": _content_type(normalized_headers),
            "html": html,
            "text": text,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            **_empty_result(),
            "warnings": [f"Browser retrieval failed: {type(exc).__name__}: {exc}"],
        }
    finally:
        for resource in (page, context):
            if resource is None:
                continue
            try:
                resource.close()
            except Exception:
                pass


def _empty_result() -> dict[str, Any]:
    return {
        "final_url": None,
        "status_code": None,
        "content_type": None,
        "html": None,
        "text": None,
        "warnings": [],
    }


def _headers(page: object) -> dict[str, str]:
    raw_headers = getattr(page, "headers", {}) or {}
    if not isinstance(raw_headers, Mapping):
        return {}
    return {str(key).lower(): str(value) for key, value in raw_headers.items()}


def _content_type(headers: dict[str, str]) -> str | None:
    return headers.get("content-type")


def _decode_body(body: bytes, encoding: str | None) -> str:
    if not body:
        return ""
    return body.decode(encoding or "utf-8", errors="replace")


def _extract_text(page: object, html: str) -> str | None:
    try:
        text = page.get_all_text()
    except Exception:
        text = ""
    text = str(text or "").strip()
    if text:
        return text
    return _html_to_text_fallback(html)


def _page_body_text(page: object) -> str | None:
    try:
        text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        text = ""
    text = str(text or "").strip()
    return text or None


def _page_content(page: object) -> tuple[str | None, list[str]]:
    try:
        return str(page.content() or ""), []
    except Exception as exc:
        return None, [f"Browser HTML capture failed: {type(exc).__name__}: {exc}"]


def _html_to_text_fallback(html: str) -> str | None:
    try:
        from lxml import html as lxml_html

        document = lxml_html.fromstring(html or "")
        text = document.text_content()
    except Exception:
        text = html
    text = str(text or "").strip()
    return text or None


def _restriction_warnings(
    status_code: int | None, html: str | None, text: str | None
) -> list[str]:
    warnings: list[str] = []
    if status_code in {401, 403, 429}:
        warnings.append(f"HTTP status may indicate access restriction: {status_code}.")

    haystack = f"{html or ''}\n{text or ''}".lower()
    if any(marker in haystack for marker in BOT_RESTRICTION_MARKERS):
        warnings.append("Content appears to contain bot-restriction or verification language.")
    return warnings


def _fallback_reason(result: dict[str, Any]) -> str | None:
    status_code = result["status_code"]
    html = result["html"] or ""
    text = result["text"] or ""
    warnings = result["warnings"]

    if status_code is None:
        return "http_failed"
    if status_code in {401, 403, 429}:
        return f"http_status_{status_code}"
    if any("bot-restriction" in warning for warning in warnings):
        return "bot_restriction_content"
    if _looks_like_app_shell(html, text):
        return "app_shell"
    if len(text.strip()) < MIN_TEXT_CHARS_FOR_HTTP:
        return "low_text"
    return None


def _fallback_trigger_warning(reason: str) -> str:
    if reason.startswith("http_status_"):
        return f"http_status_triggered_render_fallback: {reason.rsplit('_', 1)[-1]}"
    return f"{reason}_triggered_render_fallback"


def _looks_like_app_shell(html: str, text: str) -> bool:
    if len(text.strip()) >= MIN_TEXT_CHARS_FOR_HTTP:
        return False
    lowered = html.lower()
    script_count = lowered.count("<script")
    root_markers = ("id=\"root\"", "id=\"app\"", "data-reactroot", "__next")
    return script_count >= 3 or any(marker in lowered for marker in root_markers)


def _playwright_wait_until(wait_until: WaitUntil) -> str:
    if wait_until is WaitUntil.COMMIT:
        return "commit"
    if wait_until is WaitUntil.LOAD:
        return "load"
    if wait_until is WaitUntil.NETWORKIDLE:
        return "networkidle"
    return "domcontentloaded"
