# Blackglass

Blackglass is a standalone, policy-aware web retrieval and rendering service for agents.

It is intentionally independent of any specific agent stack, memory system, search service, or downstream extractor. Other projects call Blackglass over HTTP (or MCP) without importing its Python, browser, or retrieval dependency stack.

Blackglass owns:

- Resilient one-URL retrieval over HTTP (Scrapling) with optional browser rendering (Cloakbrowser).
- `auto` mode that starts on the cheap HTTP path and escalates to a rendered fetch when the response looks restricted, app-shell-like, or too thin.
- Policy controls: per-domain allow/deny, per-domain backend restrictions, and a local-network deny.
- Compact retrieval provenance: status, final URL, backend, rendered flag, warnings, timing, and an artifact id.

## Run Locally

```bash
just run
```

The service starts on the host and port configured in TOML. By default:

```text
http://127.0.0.1:8010
```

## Run As A Sidecar

Blackglass is containerized as a sidecar-friendly standalone service. The image keeps the browser and retrieval dependency stack out of consuming projects while exposing the same HTTP API.

```bash
just container-build
just container-up
just health
```

The compose profile mounts:

- `./config.container.toml` at `/config/blackglass.toml`
- a Docker volume at `/data/artifacts`

Container config enables Scrapling and Cloakbrowser availability but keeps policy controls explicit. Other services on the compose network reach Blackglass at `http://blackglass:8010` and the MCP sidecar at `http://blackglass-mcp:8011/mcp`.

## API

Two endpoints:

- `GET /health` — readiness, configured artifact directory, backend availability, and a compact settings summary.
- `POST /retrieve` — policy-aware one-URL retrieval with provenance.

### `/retrieve` modes

- `http_only` — Scrapling HTTP only; no rendering even if the response looks blocked.
- `render_only` — go straight to the browser backend if one is enabled.
- `auto` (default) — try the HTTP backend first, then escalate to the browser backend if the HTTP result triggers any of these heuristics:
  - HTTP error or transport failure
  - HTTP status `401`, `403`, or `429`
  - Body contains bot-restriction / verification language
  - Page looks like an app shell (sparse text plus React/Next/`#root` markers)
  - Extracted text is shorter than 200 characters

If the browser fallback itself fails, the HTTP result is returned with `render_fallback_failed_returning_http_result` in `warnings` so callers can see what happened.

### Example

```bash
curl -fsS -X POST http://127.0.0.1:8010/retrieve \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com/article","mode":"auto","preferred_backends":["scrapling_http","cloakbrowser"]}'
```

Response shape (abridged):

```json
{
  "artifact_id": "bg_7babd23fa75f40b8a3a868bc7310f601",
  "url": "https://...",
  "final_url": "https://...",
  "status": "retrieved",
  "status_code": 200,
  "content_type": "text/html",
  "backend": "cloakbrowser",
  "rendered": true,
  "html": "...",
  "text": "...",
  "warnings": ["bot_restriction_content_triggered_render_fallback"],
  "policy": {
    "allowed": true,
    "robots_allowed": null,
    "allowlist_matched": false,
    "denylist_matched": false,
    "backend_allowed": true,
    "local_network_blocked": false
  },
  "timing": {"started_at": 1779740911.45, "duration_ms": 1263}
}
```

`status` is `retrieved` (got a body or status code), `blocked` (policy denied), or `failed`. `robots_allowed` is `null` until live robots.txt checking lands.

OpenAPI is exposed by FastAPI:

- `/openapi.json`
- `/docs`

## MCP

Blackglass also exposes a compact MCP interface for agents. The tool surface is intentionally small so local and smaller LLMs can use it reliably:

- `health` — readiness, policy, and backend availability.
- `retrieve` — one-URL retrieval with compact provenance; full HTML is opt-in.

`retrieve` parameters (all optional except `url`):

| name | default | notes |
|---|---|---|
| `url` | — | Required. |
| `profile` | `auto` | `auto`, `http`, or `render`. Maps to mode + backend list. |
| `respect_robots` | from config | Per-call override. |
| `timeout_seconds`, `max_body_bytes` | from config | Per-call overrides. |
| `wait_until` | `domcontentloaded` | Browser-only navigation gate. |
| `include_html` | `false` | Opt in to receive HTML in the response. |
| `include_text` | `true` | Set false to omit extracted text. |
| `max_chars` | `2000` | Truncates `text` / `html` in the response. Hard-capped at 20 000 chars; oversized requests get a `max_chars_clamped_to_20000` warning. |

Run over stdio:

```bash
just mcp
```

Run with Streamable HTTP:

```bash
just mcp-http
```

The Streamable HTTP endpoint defaults to:

```text
http://127.0.0.1:8011/mcp
```

## Configuration

Blackglass reads configuration from, in order of precedence:

1. `--config /path/to/config.toml`
2. `BLACKGLASS_CONFIG=/path/to/config.toml`
3. Built-in defaults

See [config.example.toml](config.example.toml).

### Fields

`[server]`

| key | default | notes |
|---|---|---|
| `host` | `127.0.0.1` | |
| `port` | `8010` | |

`[policy]`

| key | default | notes |
|---|---|---|
| `respect_robots_default` | `true` | Default for the per-request `respect_robots` flag. |
| `browser_enabled` | `false` | Master gate for any browser backend. |
| `cloakbrowser_enabled` | `false` | Requires `browser_enabled = true` to take effect. |
| `deny_local_networks` | `true` | Blocks `localhost`, loopback, RFC1918, link-local. |

`[retrieval]`

| key | default | notes |
|---|---|---|
| `default_mode` | `auto` | Fallback when a request omits `mode`. |
| `default_backends` | `["scrapling_http"]` | Must be non-empty. |
| `timeout_seconds` | `20` | |
| `max_body_bytes` | `3_000_000` | |
| `artifact_dir` | `~/.blackglass/artifacts` | Reserved for the upcoming persistence milestone. |

`[domains."example.com"]` (any number; keys are lowercased on load)

| key | notes |
|---|---|
| `allow` | `true` → allowlist match, `false` → denylist (blocks the request). |
| `allowed_backends` | Optional list. If set, requests using a backend not in this list are blocked. |

## Development

Common workflows live in the [Justfile](Justfile):

```bash
just test            # pytest with the retrieval extras
just coverage        # pytest --cov --cov-report=term-missing (85% gate)
just compile         # python -m compileall src tests (via uv)
just check           # compile + coverage
```

Container workflows:

```bash
just container-build      # build the runtime image
just container-up         # start blackglass + blackglass-mcp via compose
just container-down       # tear them down
just container-logs       # tail compose logs
just container-test       # run the pytest suite inside the runtime image
just container-smoke      # bring up, hit /health, hit /retrieve
just integration          # full end-to-end: HTTP smoke + MCP smoke
```

CI runs `compile` + `pytest --cov` on every push and pull request to `main` (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Agent playbook

A harness-agnostic agent playbook for one-URL retrieval ships at [`skills/blackglass-retrieve/`](skills/blackglass-retrieve/). The [`PLAYBOOK.md`](skills/blackglass-retrieve/PLAYBOOK.md) is the single source of truth — pure markdown instructions any agent can read. The [`GUIDE.md`](skills/blackglass-retrieve/GUIDE.md) shows how to wire it into Claude Code, OpenCode, Codex, Antigravity, Cursor / Continue / Windsurf, raw system prompts, or — preferred when available — the bundled `blackglass-mcp` MCP server.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the running list of changes.

## License

MIT — see [LICENSE](LICENSE).
