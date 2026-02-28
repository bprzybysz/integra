#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run ruff format .
uv run ruff check --select I --fix .
