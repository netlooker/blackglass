from __future__ import annotations

import argparse

import uvicorn

from blackglass.app import create_app
from blackglass.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Blackglass API server.")
    parser.add_argument("--config", help="Path to a Blackglass TOML config file.")
    args = parser.parse_args()

    settings = load_settings(args.config)
    uvicorn.run(
        create_app(settings),
        host=settings.server.host,
        port=settings.server.port,
        log_level="info",
        loop="asyncio",
    )
