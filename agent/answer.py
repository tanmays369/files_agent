"""Answer writer (T3.2): the final answer plus a record trail, and a check of every cited id."""
from __future__ import annotations

import re
from typing import Any

from agent.records import DecisionRecord

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)


def cited_ids(text: str) -> list[str]:
    return sorted({m.lower() for m in UUID_RE.findall(text or "")})


def compose(model_text: str, records: list[DecisionRecord], seen_ids: set[str]) -> dict[str, Any]:
    """Append a record trail so every statement can be traced to a decision record."""
    trail = [f"- [{r.status}] {r.action}: {r.target_label or '-'}" + (f" ({r.target_id})" if r.target_id else "")
             for r in records if r.status != "info" or r.action in ("current_drawing", "superseded_drawing", "contradiction", "list")]
    answer = (model_text or "").strip()
    if trail:
        answer += "\n\nRecord trail:\n" + "\n".join(trail)
    ids = cited_ids(answer)
    seen = {s.lower() for s in seen_ids}
    return {"answer": answer, "cited_ids": ids, "unverified_ids": [i for i in ids if i not in seen]}
