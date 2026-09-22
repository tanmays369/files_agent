"""Append-only JSONL trace. Every event is redacted before it touches the disk."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.redact import Redactor


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Trace:
    """Writes one JSON object per line and keeps a redacted in-memory copy."""

    def __init__(self, path: Path | None, redactor: Redactor) -> None:
        self.path = path
        self.redact = redactor
        self.events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **data: Any) -> dict[str, Any]:
        event = self.redact({"t": now_iso(), "kind": kind, **data})
        self.events.append(event)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == kind]

    def attach(self, path: Path, header: dict[str, Any]) -> None:
        """Start writing to `path`: the header (manifest) first, then any events buffered so far."""
        path.parent.mkdir(parents=True, exist_ok=True)
        first = self.redact({"t": now_iso(), "kind": "manifest", **header})
        with path.open("w", encoding="utf-8") as fh:
            for event in [first, *self.events]:
                fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        self.events.insert(0, first)
        self.path = path


def read_trace(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
