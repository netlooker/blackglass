from __future__ import annotations

from importlib.util import find_spec

from typing import Annotated

from fastapi import APIRouter, Body, Request

from blackglass.config import Settings, settings_summary
from blackglass.retrieval import retrieve
from blackglass.schemas import HealthResponse, RetrieveRequest, RetrieveResponse

router = APIRouter()


RETRIEVE_EXAMPLE = {
    "url": "https://example.com/article",
    "mode": "auto",
    "preferred_backends": ["scrapling_http", "cloakbrowser"],
    "respect_robots": True,
    "timeout_seconds": 20,
    "max_body_bytes": 3000000,
    "wait_until": "domcontentloaded",
}


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    operation_id="getHealth",
    summary="Check service health",
    description="Return readiness, configured artifact directory, and optional backend availability.",
)
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        ready=True,
        artifact_dir=str(settings.retrieval.artifact_dir),
        browser_available=find_spec("playwright") is not None,
        cloakbrowser_available=find_spec("cloakbrowser") is not None,
        scrapling_available=find_spec("scrapling") is not None,
        config_loaded=settings.config_path is not None,
        config=settings_summary(settings),
    )


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    tags=["retrieval"],
    operation_id="retrieveUrl",
    summary="Retrieve one URL",
    description=(
        "Validate and execute a policy-aware one-URL retrieval request. "
        "The current skeleton returns provenance without performing live retrieval."
    ),
    responses={
        422: {
            "description": "Request validation error.",
        },
    },
)
def retrieve_route(
    payload: Annotated[
        RetrieveRequest,
        Body(
            openapi_examples={
                "auto": {
                    "summary": "Automatic HTTP-first retrieval",
                    "description": "Try lightweight retrieval first and allow browser-capable fallback when configured.",
                    "value": RETRIEVE_EXAMPLE,
                }
            }
        ),
    ],
    request: Request,
) -> RetrieveResponse:
    settings: Settings = request.app.state.settings
    return retrieve(payload, settings)
