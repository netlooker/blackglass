FROM ghcr.io/astral-sh/uv:0.6.6 AS uv

FROM cloakhq/cloakbrowser:latest AS base

WORKDIR /app

ENV BLACKGLASS_CONFIG=/config/blackglass.toml \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN mkdir -p /config /data/artifacts

FROM base AS runtime

RUN uv sync --frozen --no-dev --extra retrieval --extra browser

EXPOSE 8010 8011
VOLUME ["/config", "/data/artifacts"]

CMD ["blackglass", "--config", "/config/blackglass.toml"]

FROM base AS test

COPY tests ./tests

RUN uv sync --frozen --extra dev --extra retrieval --extra browser

CMD ["pytest", "--cov", "--cov-report=term-missing"]
