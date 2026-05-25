# Blackglass Retrieve — Agent Playbook Adoption Guide

[`PLAYBOOK.md`](PLAYBOOK.md) is a harness-agnostic instruction set. Any agentic tool that can read markdown instructions can execute it. This guide is the human-facing companion: what the playbook does, the one prerequisite, and how to wire it into the agent of your choice.

## What it does

The playbook tells an agent to:

1. Health-check a local Blackglass HTTP service.
2. POST a single URL to `/retrieve` with `mode=auto` and both backends listed, so Blackglass starts on the cheap HTTP path and escalates to a browser-rendered fetch when the response looks restricted, app-shell-like, or too thin.
3. Render the response back to the user: status line, warnings (translated to plain English), extracted text (truncated), and artifact id.

It is deliberately a **single-URL** procedure. No crawling, no link-following, no scheduling.

## Prerequisite (one-time)

The playbook needs a reachable Blackglass HTTP service. Pick one:

```bash
just container-up   # Docker: starts blackglass on :8010 and blackglass-mcp on :8011
# or
just run            # Local foreground process
```

If you're pointing the playbook at a non-default location, export `BLACKGLASS_URL` in the environment your agent inherits:

```bash
export BLACKGLASS_URL=http://blackglass.internal:8010
```

The playbook reads it on every invocation.

## Wiring per harness

The playbook content is the same everywhere. Only the file location, filename, and (sometimes) a small wrapper header differ. Pick the recipe that matches your tool.

### Claude Code (`claude` CLI)

Claude Code reads skills from `~/.claude/skills/<name>/SKILL.md` (user-level) or `<project>/.claude/skills/<name>/SKILL.md` (project-level). It expects YAML frontmatter at the top.

Create `~/.claude/skills/blackglass-retrieve/SKILL.md` containing a small frontmatter header followed by the playbook body:

```bash
mkdir -p ~/.claude/skills/blackglass-retrieve

{
  cat <<'EOF'
---
name: blackglass-retrieve
description: Use the local Blackglass HTTP service to fetch one URL with policy-aware HTTP/render fallback. Invoke when the user asks to retrieve, scrape, render, or "blackglass" a webpage. Single-URL only.
---

EOF
  cat /path/to/blackglass/skills/blackglass-retrieve/PLAYBOOK.md
} > ~/.claude/skills/blackglass-retrieve/SKILL.md
```

Invoke from a Claude Code session with `/blackglass-retrieve <url>`. Restart the session if the skill doesn't appear.

### OpenCode

OpenCode reads agent instructions from `AGENTS.md` files (project-level) and from configured rule paths. To register the playbook:

- **Project-scoped:** append `PLAYBOOK.md`'s content to `AGENTS.md` under a heading like `## Blackglass retrieval`, or reference it: `See [skills/blackglass-retrieve/PLAYBOOK.md](skills/blackglass-retrieve/PLAYBOOK.md) when the user asks to fetch a URL.`
- **User-scoped:** drop a copy under your OpenCode config directory (commonly `~/.config/opencode/rules/`) — check `opencode --help` for the exact path on your install.

Trigger naturally in chat ("blackglass <url>", "fetch <url>") — OpenCode's agent matches on the playbook's "When to use" heading.

### Codex CLI

Codex reads project guidance from `AGENTS.md` at repo root and user guidance from `~/.codex/AGENTS.md`. Wire the playbook by either:

- Adding a short pointer in `AGENTS.md`: `When the user asks to retrieve a URL, follow skills/blackglass-retrieve/PLAYBOOK.md.`
- Or pasting the full playbook body under an `## URL retrieval (Blackglass)` section in `AGENTS.md`.

The pointer form is easier to keep in sync; the paste form works when the agent can't read sibling files.

### Antigravity

Antigravity reads agent rules from its workspace settings (typically `.antigravity/` or the IDE-level rules pane). Add a new rule whose body is the playbook content, with a title like "Blackglass URL retrieval" and a trigger description matching the "When to use" heading. Use the workspace-rule path for repo-bound use and the user-rule path for global access.

### Cursor / Continue / Windsurf and similar "rules" tools

These tools all support project-scoped instruction files (`.cursor/rules/`, `.continuerules`, `.windsurfrules`, etc.). The recipe is the same:

```bash
mkdir -p .cursor/rules            # adjust per-tool
cp skills/blackglass-retrieve/PLAYBOOK.md .cursor/rules/blackglass-retrieve.md
```

No frontmatter needed for most of these. The agent loads the rule on session start.

### Generic system prompt / custom instructions / ChatGPT custom GPT

For anything that lets you paste a system prompt or custom instruction block (OpenAI Custom GPTs, Anthropic API system prompt, raw chat front-ends, etc.):

1. Paste the contents of `PLAYBOOK.md` into the system prompt slot.
2. Make sure the agent has shell access to run `curl`. If it does not, this playbook can't be executed — see the MCP path below instead.

### MCP-capable agents (preferred when available)

If your harness speaks **MCP** (Model Context Protocol), you don't need this playbook at all — Blackglass ships an MCP server (`blackglass-mcp`) that exposes the same retrieval as a typed tool. Point your agent at the running MCP endpoint:

- **Streamable HTTP:** `http://127.0.0.1:8011/mcp` (after `just container-up` or `just mcp-http`)
- **stdio:** `blackglass-mcp --config /path/to/config.toml`

See the **MCP** section of the [main README](../../README.md) for the tool surface (`health`, `retrieve`) and parameters. The playbook is the curl-based fallback for agents that don't (yet) wire MCP servers.

## Usage examples (any harness)

Once the playbook is wired in, the agent should respond to natural-language fetch requests:

- `blackglass https://example.com/article`
- `fetch https://news.ycombinator.com via blackglass`
- `render https://reddit.com/r/printSF/... for me --max-chars 8000 --html`
- `blackglass https://internal.docs.example.com --mode render_only --timeout 90`

Supported flags (parsed by the agent from your message):

| flag | default | effect |
| --- | --- | --- |
| `--mode auto\|http_only\|render_only` | `auto` | Forces Blackglass into a single backend path. `render_only` requires the browser to be enabled in your Blackglass config. |
| `--html` | off | Include the rendered HTML byte length (and optionally a preview) in the output. |
| `--timeout <seconds>` | `60` | Per-request timeout sent to Blackglass. |
| `--max-chars <n>` | `4000` | Truncates the *shown* text. Independent of `max_body_bytes`. |

## What you get back

A typical response looks like:

```text
retrieved via cloakbrowser (rendered=true, status_code=200, 1263ms)
final_url: https://example.com/article?solution=...&js_challenge=1

warnings:
  - bot/captcha content detected — switched to browser
  - bot/captcha markers still present in rendered HTML (informational)

text (first 4000 chars):
  Skip to main content
  ...

artifact_id: bg_7babd23fa75f40b8a3a868bc7310f601
```

The warnings list is the most informative field — it tells you *why* the request took the path it did. Read it before assuming the page is what you wanted.

## When **not** to use this playbook

- **Multi-page crawls.** Single URL by design.
- **Comment trees on JS-heavy sites.** Blackglass currently waits on `domcontentloaded`; per-selector waits aren't exposed yet. If you need a comment thread, hit the site's JSON endpoint directly or wait for a per-selector wait flag.
- **Local network targets.** `deny_local_networks` is on by default; the playbook will not attempt to disable it. If you genuinely need to reach a `localhost` / RFC1918 target, change `[policy]` in your `config.toml` deliberately.
- **Search.** Blackglass retrieves; it does not search. Pair it with a search tool of your choice.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "Blackglass not reachable" | Service not started or wrong URL | Run `just container-up` (or `just run`), or set `BLACKGLASS_URL`. |
| `status: blocked`, `local_network_blocked: true` | URL is a loopback/RFC1918 host | This is the policy working. Edit `[policy] deny_local_networks` in your config only if you really mean to. |
| `status: failed`, `Browser retrieval failed: ... ERR_NAME_NOT_RESOLVED` | DNS inside the container couldn't resolve the host | Check the container's network (compose default network usually works for public hosts; corp DNS may not). |
| `render_fallback_not_available: ...` warning | HTTP path looked thin but no browser backend is enabled | Set `browser_enabled = true` and `cloakbrowser_enabled = true` in `[policy]`, then re-run. |
| Agent doesn't recognise the request | Playbook isn't loaded into the agent's context | Re-check your harness's rule/skill loading path; restart the agent session. |

## See also

- [Blackglass README](../../README.md) — service overview, modes, configuration reference.
- [Blackglass CHANGELOG](../../CHANGELOG.md) — what's implemented today and what's intentionally deferred.
- [PLAYBOOK.md](PLAYBOOK.md) — the harness-agnostic playbook itself; this is the source of truth and the only file that should change when the procedure changes.
