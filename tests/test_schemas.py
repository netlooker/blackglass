import pytest
from pydantic import ValidationError

from blackglass.schemas import (
    RetrieveRequest,
    RetrievalBackend,
    RetrievalMode,
    TimingInfo,
    WaitUntil,
)


def test_documented_retrieve_payload_validates() -> None:
    request = RetrieveRequest.model_validate(
        {
            "url": "https://example.com/article",
            "mode": "auto",
            "preferred_backends": ["scrapling_http", "cloakbrowser"],
            "respect_robots": True,
            "timeout_seconds": 20,
            "max_body_bytes": 3000000,
            "wait_until": "domcontentloaded",
        }
    )

    assert str(request.url) == "https://example.com/article"
    assert request.mode == RetrievalMode.AUTO
    assert request.preferred_backends == [
        RetrievalBackend.SCRAPLING_HTTP,
        RetrievalBackend.CLOAKBROWSER,
    ]
    assert request.wait_until == WaitUntil.DOMCONTENTLOADED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "not-a-url"),
        ("mode", "crawl"),
        ("preferred_backends", ["magic_browser"]),
        ("wait_until", "forever"),
    ],
)
def test_retrieve_request_rejects_invalid_enum_and_url(
    field: str, value: object
) -> None:
    payload = {
        "url": "https://example.com/article",
        "mode": "auto",
        "preferred_backends": ["scrapling_http"],
        "wait_until": "domcontentloaded",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        RetrieveRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 0),
        ("timeout_seconds", 121),
        ("max_body_bytes", 0),
        ("max_body_bytes", 50_000_001),
    ],
)
def test_retrieve_request_enforces_bounds(field: str, value: int) -> None:
    payload = {
        "url": "https://example.com/article",
        "mode": "auto",
        "preferred_backends": ["scrapling_http"],
        field: value,
    }

    with pytest.raises(ValidationError):
        RetrieveRequest.model_validate(payload)


def test_timing_info_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        TimingInfo(started_at=1.0, duration_ms=-1)
