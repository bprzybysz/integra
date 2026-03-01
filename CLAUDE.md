
Master/orchestrator agent. FastAPI + Claude Opus 4.6 + Telegram HIL + secure data lake.

## Rules

- **Never commit sensitive data** — `data/` is `.gitignored`. All user data (health, drugs, habits, history) stays encrypted at rest.
- **Async first** — use `AsyncAnthropic`, `async def`, `await`. No sync Anthropic client.
- **HIL enforcement in code** — tools marked `requires_confirmation=True` in registry MUST trigger Telegram approval before dispatch. Not prompt-level only.
- **Max 500 lines per file** — split when approaching. Use `core/`, `integrations/`, `data/` package structure.
- **Type everything** — `mypy --strict` must pass. No `Any` without justification.
- **Tests required** — every module gets a test file. Minimum: 1 happy path + 1 edge case + 1 error case.

## Multitasking — Speed & Context Separation

When a task involves multiple files or steps:

1. **Parallel reads** — read all relevant files simultaneously. Never read sequentially what you can read in parallel
2. **Parallel writes** — independent file writes/edits in one message. Sequential only when output of one informs the next
3. **Audit → Plan → Execute** — for restructuring: read everything first (no edits), present plan for approval, then execute. Never interleave reading and writing
4. **Task agents for isolation** — use Agent tool when research would flood main context. Agent returns summary, main context stays clean
5. **Don't duplicate agent work** — if you delegate research to a subagent, don't search for the same things yourself
6. **Batch operations** — group related file moves, git commands, edits into single shell calls where safe
7. **TaskCreate for 3+ steps** — use task tracking for multi-step work. Mark in_progress before starting, completed when done
8. **Suggest Haiku** for simple verify/check tasks to save cost

**Anti-patterns to avoid:**
- Reading files one-at-a-time when independent
- Re-reading a file already in context
- Asking clarifying questions answerable from files already read
- Sequential tool calls that could be parallel

## User Context

- Style: direct, imperative, no pleasantries. Match brevity
- ALL CAPS / "NOPE" = stop, diagnose, don't repeat
- Action first — do the thing, explain only when asked
- Don't auto-proceed after major deliverables — pause for review

## Validation Commands

```bash
uv run ruff check --fix .          # lint + auto-fix
uv run ruff format .               # format
uv run mypy .                      # type check
uv run pytest tests/ -v            # test
```

## Architecture

```
integra/
├── app.py              # FastAPI entrypoint, Telegram lifespan
├── core/
│   ├── orchestrator.py # Claude agentic loop (async, max 15 tool rounds)
│   ├── registry.py     # Tool schemas + dispatch map + HIL flags
│   └── config.py       # Pydantic-settings from .env
├── integrations/
│   └── telegram.py     # HIL confirm/notify via Telegram inline keyboard
└── data/
    ├── mcp_server.py   # Data MCP gateway (decrypt-on-read, audit, filtering)
    ├── ingestion.py    # Raw → structured pipeline
    └── encryption.py   # age encrypt/decrypt helpers
```

## Tool Registry Pattern

```python
TOOLS = {
    "tool_name": {
        "handler": module.handler_fn,
        "requires_confirmation": True,  # triggers HIL before dispatch
        "schema": { ... },              # Claude tool_use JSON schema
    }
}
```

## Data Lake Pattern

All sensitive data: Land (`data/raw/`) → Encrypt (`age`) → Store (`data/lake/`) → Serve via MCP.
Agent never reads raw files. MCP gateway decrypts on-demand, filters, audits.

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.13 | Runtime |
| uv | Package manager |
| FastAPI | HTTP server |
| anthropic | Claude API (async) |
| python-telegram-bot | Telegram HIL |
| pyrage | age encryption (Python) |
| ruff | Lint + format |
| mypy | Type checking (strict) |
| pytest | Testing |

## Stage Reference

Toptal KB context for upcoming stages: `tmp/context-from-toptal.md`
Full roadmap: `/Users/blaisem4/src/interviews/toptal/docs/integra-roadmap.md`
