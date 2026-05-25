# Changelog

All notable changes to Blackglass are recorded here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- `RetrieveRequest.screenshot` field and the matching `RetrieveResponse.screenshot_path` / `RetrieveResponse.trace_path` fields. Screenshot/trace capture is not implemented; the fields were misleading dead surface.
- MCP `retrieve(screenshot=…)` parameter, alongside the `screenshot_path` / `trace_path` keys in the compact MCP response.
- `PolicySettings.default_min_delay_seconds` and `DomainPolicy.{browser_enabled, cloakbrowser_enabled, min_delay_seconds}`. None of these were read at runtime; rate limiting and per-domain browser overrides are deferred until they are actually wired into the policy and retrieval paths.

### Fixed

- `PolicyDecision.robots_allowed` is now always `null` until live robots.txt checking lands. The previous behavior returned `true` whenever `respect_robots=true`, despite no robots check being performed.
- `RetrievalSettings.default_backends` now requires `min_length=1`. An empty list would previously have caused an `IndexError` in `_select_backend`.
- `Settings.domains` keys are lowercased on load via a Pydantic validator, so `[domains."Example.COM"]` correctly matches retrievals for `example.com`. Domain matching remains exact (no subdomain rollup).
- MCP `retrieve` now emits a `max_chars_clamped_to_20000` warning when callers request more characters than the hard cap, instead of silently truncating.
- `Justfile compile` runs through `uv run` instead of the bare system `python3`, keeping the compile step on the project's pinned interpreter.
- `tests/test_config.py::test_container_config_matches_sidecar_defaults` resolves `config.container.toml` relative to the test file rather than relying on the current working directory.

### Added

- Cloakbrowser-backed rendering and `auto`-mode escalation are now first-class: the auto path falls back from `scrapling_http` to `cloakbrowser` on transport failure, HTTP `401/403/429`, bot-restriction language, app-shell markers, or extracted text shorter than 200 characters. Aggregated warnings record both the trigger and any fallback failure.
- MCP server: compact `health` and `retrieve` tools over stdio or Streamable HTTP, with profile (`auto`/`http`/`render`), opt-in HTML, and configurable text/HTML truncation.
- Container deployment: multi-target `Dockerfile` (runtime + test) on top of `cloakhq/cloakbrowser`, `compose.yml` for both the HTTP and MCP sidecars, healthcheck on `/health`, and `config.container.toml`.
- Tests for domain-key lowercasing, the `min_length` guard on `default_backends`, the slimmed `DomainPolicy` field set, and the MCP `max_chars` clamp warning.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) running `compileall` + `pytest --cov` on push and PR to `main`.
- `LICENSE` (MIT) and `license = { file = "LICENSE" }` in `pyproject.toml`.
- `README.md` reference tables for every config section, an example `/retrieve` response, the auto-mode heuristic list, and a documented `just` workflow split (local vs. container).
- Harness-agnostic agent playbook at `skills/blackglass-retrieve/PLAYBOOK.md`, with a `GUIDE.md` covering wiring into Claude Code, OpenCode, Codex, Antigravity, Cursor/Continue/Windsurf, raw system prompts, and the bundled MCP server.

### Known gaps (intentionally deferred)

- Artifact persistence to `artifact_dir`. `artifact_id` is returned, but no body, headers, or rendered output is written to disk yet. The Dockerfile creates `/data/artifacts` and the compose volume mounts it in anticipation.
- Live robots.txt fetching and evaluation. The `respect_robots` request flag is accepted and stored, and `robots_allowed` is reserved in `PolicyDecision`, but no fetch happens.
- Subdomain matching in `[domains.*]` entries.
- Rate limiting / per-domain delay enforcement.
