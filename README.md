# integra

Master/orchestrator agent — personal AI assistant with secure data lake, Telegram HIL, and extensible tool registry.

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Copy and fill environment
cp .env.example .env

# Run
uv run uvicorn integra.app:app --reload
```

## Architecture

```
User → Telegram HIL → FastAPI → Claude Opus 4.6 → Tool Registry → [tools]
                                                                 → Data MCP → Encrypted Lake
```

## Data Lake

All sensitive data flows through: **Land** (`data/raw/`) → **Encrypt** (`age`) → **Store** (`data/lake/`) → **Serve** via MCP.

Agent never reads raw files. MCP gateway decrypts on-demand with audit logging.

## Development

```bash
uv run ruff check --fix .    # lint
uv run ruff format .         # format
uv run mypy .                # types
uv run pytest tests/ -v      # test
```
