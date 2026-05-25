set dotenv-load := false

default:
    @just --list

test:
    uv run --extra dev --extra retrieval pytest

coverage:
    uv run --extra dev --extra retrieval pytest --cov --cov-report=term-missing

compile:
    uv run --extra dev --extra retrieval python -m compileall src tests

run:
    uv run blackglass --config config.example.toml

mcp:
    uv run blackglass-mcp --config config.example.toml

mcp-http:
    uv run blackglass-mcp --config config.container.toml --transport streamable-http --host 127.0.0.1 --port 8011 --path /mcp

container-build:
    docker compose build blackglass

container-test:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'docker compose down' EXIT
    docker compose build blackglass-test
    docker compose run --rm blackglass-test

container-up:
    docker compose up -d blackglass blackglass-mcp

container-down:
    docker compose down

container-logs:
    docker compose logs -f blackglass blackglass-mcp

health:
    curl -fsS http://127.0.0.1:8010/health

retrieve-smoke:
    curl -fsS -X POST http://127.0.0.1:8010/retrieve \
      -H 'content-type: application/json' \
      -d '{"url":"https://example.com/article","mode":"auto","preferred_backends":["scrapling_http","cloakbrowser"],"respect_robots":true,"timeout_seconds":20,"max_body_bytes":3000000,"wait_until":"domcontentloaded"}'

container-smoke: container-up
    @for i in $(seq 1 20); do \
      if curl -fsS http://127.0.0.1:8010/health >/dev/null; then \
        just health; \
        just retrieve-smoke; \
        exit 0; \
      fi; \
      sleep 1; \
    done; \
    docker compose logs blackglass; \
    exit 1

integration:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose build blackglass blackglass-mcp
    docker compose up -d blackglass blackglass-mcp
    trap 'docker compose down' EXIT
    for _ in $(seq 1 30); do
      if curl -fsS http://127.0.0.1:8010/health >/dev/null; then
        break
      fi
      sleep 1
    done
    just health
    just retrieve-smoke
    uv run python scripts/mcp_smoke.py

check: compile coverage
