"""Shared audit-log helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_audit_entry(audit_path: Path, entry: dict[str, Any]) -> None:
    """Append a JSON-lines entry to an audit log file."""
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
