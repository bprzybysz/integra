# Integra — CLAUDE.md

Master/orchestrator agent. FastAPI + Claude Opus 4.6 + Telegram HIL + secure data lake.

## Rules

- **Never commit sensitive data** — `data/` is `.gitignored`. All user data (health, drugs, habits, history) stays encrypted at rest.
- **Async first** — use `AsyncAnthropic`, `async def`, `await`. No sync Anthropic client.
- **HIL enforcement in code** — tools marked `requires_confirmation=True` in registry MUST trigger Telegram approval before dispatch. Not prompt-level only.
- **Max 500 lines per file** — split when approaching. Use `core/`, `integrations/`, `data/` package structure.
- **Type everything** — `mypy --strict` must pass. No `Any` without justification.
- **Tests required** — every module gets a test file. Minimum: 1 happy path + 1 edge case + 1 error case.

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
