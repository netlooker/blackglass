# Blackglass Retrieve — Agent Playbook

Pure agent-readable instructions for fetching one URL through a local Blackglass HTTP service. Harness-agnostic: drop this into any agent that can read markdown instructions (Claude Code, OpenCode, Codex, Antigravity, Cursor, Continue, custom system prompts, MCP `instructions` field, etc.). The body below is the entire contract — no harness-specific frontmatter, no tool registration, no required SDK.

Base URL: `${BLACKGLASS_URL:-http://127.0.0.1:8010}`. The agent should respect this environment variable when set.

---

## When to use this playbook

Trigger this procedure when the user asks to retrieve, scrape, render, or "blackglass" a single webpage — phrasings like:

- "blackglass <url>"
- "fetch <url>"
- "render <url> for me"
- "what's on <url>"
- "scrape this page: <url>"

Do **not** trigger for multi-page crawling, link-following, search, or scheduled repeats. This playbook is single-URL.

## Inputs

Parse the user's request:

- The URL is mandatory. If none is provided, ask the user — do not invent.
- Optional flags (accept in any order):
  - `--mode auto|http_only|render_only` — default `auto`
  - `--html` — include HTML in the output (default: omit; just report byte length)
  - `--timeout <seconds>` — default `60`
  - `--max-chars <n>` — truncate the *shown* text to N chars (default `4000`)

## Steps

### 1. Health check

```bash
curl -fsS --max-time 2 "${BLACKGLASS_URL:-http://127.0.0.1:8010}/health"
```

If this fails or times out, tell the user Blackglass isn't reachable at the configured URL and **stop**. Offer (do not run) one of these, depending on what's available in the working directory:

- `just container-up` — when `Justfile` and `docker` are both present
- `just run` — when only `Justfile` is present (foreground process; suggest a separate terminal)
- `uv run blackglass --config config.example.toml` — manual fallback

Wait for the user to confirm or start it themselves, then resume from step 2.

If the health body shows `cloakbrowser_available: false` and the user asked for `--mode render_only`, warn them up front — the request will fail with a no-backend warning.

### 2. Retrieve

One POST to `/retrieve`. Use `mode=auto` (or the user's override) and list both backends so render fallback engages when the HTTP path looks restricted:

```bash
curl -fsS -X POST "${BLACKGLASS_URL:-http://127.0.0.1:8010}/retrieve" \
  -H 'content-type: application/json' \
  -d '{
    "url": "<url>",
    "mode": "<mode>",
    "preferred_backends": ["scrapling_http", "cloakbrowser"],
    "respect_robots": true,
    "timeout_seconds": <timeout>,
    "max_body_bytes": 5000000,
    "wait_until": "domcontentloaded"
  }'
```

`/retrieve` never throws on retrieval failure — it returns HTTP 200 with `status: "failed"` and warnings populated. Always read the body; never infer success from the HTTP status alone.

### 3. Render the outcome

Show the user, in this order:

1. **One-line status:** `<status> via <backend> (rendered=<bool>, status_code=<code>, <duration_ms>ms)`
2. **Final URL** if different from the requested URL (often signals an anti-bot redirect or login wall).
3. **Warnings** (bulleted) if `warnings` is non-empty. Translate the structured tokens into plain English:
   - `http_status_triggered_render_fallback: 403` → "HTTP 403 triggered browser fallback"
   - `bot_restriction_content_triggered_render_fallback` → "bot/captcha content detected — switched to browser"
   - `low_text_triggered_render_fallback` → "too little text on HTTP path — switched to browser"
   - `app_shell_triggered_render_fallback` → "SPA shell detected — switched to browser"
   - `render_fallback_failed_returning_http_result` → "browser fallback failed; HTTP result returned"
   - `render_fallback_not_available: <reason>` → "fallback wanted but no browser backend enabled"
   - `max_chars_clamped_to_20000` (MCP transport only) → "max_chars capped at 20 000"
4. **Extracted text**, truncated to `--max-chars`. Show `… [truncated, <total> chars total]` at the cut.
5. If `--html` was passed, also report HTML byte length and (optionally) the first ~500 chars.
6. **Footer:** `artifact_id: <id>`

### 4. Failure handling

If `status: "blocked"`:

- Surface whichever of `policy.denylist_matched`, `policy.local_network_blocked`, `policy.backend_allowed` is the cause.
- For `local_network_blocked`, explain it's the `deny_local_networks` protection. Do not suggest disabling it without a clear, reviewed reason from the user.
- Do not retry.

If `status: "failed"`:

- Show all warnings.
- Suggest one targeted next step: a different `--mode`, a longer `--timeout`, or enabling the browser backend in `config.toml`. Do not auto-retry.

## Hard rules

- **Single URL per invocation.** If the user gives multiple URLs, do them one at a time and ask before continuing past the first.
- **HTTP(S) only.** Never call `/retrieve` with `file://`, `javascript:`, `data:`, or other non-HTTP(S) schemes — they will 422 anyway, but reject earlier.
- **Don't weaken policy to "make it work."** Specifically, never silently flip `deny_local_networks` or `respect_robots` in the user's config. Those are policy choices that need their deliberate consent.
- **Don't persist.** The returned `artifact_id` is reserved for the upcoming persistence milestone; today Blackglass writes nothing to disk. If the user wants the body saved, do it explicitly via your own filesystem tool, not by claiming Blackglass did it.
- **No crawling, no link-following, no scheduling.** Out of scope for this playbook. Point at the user's recurring-task tool of choice if asked.
