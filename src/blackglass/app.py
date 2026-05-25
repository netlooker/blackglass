from fastapi import FastAPI

from blackglass.config import Settings, load_settings
from blackglass.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    app = FastAPI(
        title="Blackglass",
        version="0.1.0",
        description="Policy-aware web retrieval and rendering service for agents.",
        openapi_tags=[
            {
                "name": "health",
                "description": "Service readiness and backend availability.",
            },
            {
                "name": "retrieval",
                "description": "Policy-aware one-URL retrieval requests.",
            },
        ],
    )
    app.state.settings = app_settings
    app.include_router(router)
    return app


app = create_app()
