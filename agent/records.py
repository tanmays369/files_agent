"""Decision records (T2.1): every skill explains what it did, why, and what was missing.

The final answer is written only from these records, and the harness compares
them with the database afterwards (claims against state).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

STATUSES = ("info", "planned", "applied", "skipped", "refused", "escalated", "failed")
CONFIDENCE = ("strong", "medium", "weak", "none")


@dataclass(frozen=True)
class Evidence:
    signal: str
    detail: str
    points_to: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class DecisionRecord:
    skill: str
    action: str
    status: str
    target_id: str | None = None
    target_label: str | None = None
    confidence: str = "none"
    evidence: tuple[Evidence, ...] = ()
    missing: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: "rec-" + uuid.uuid4().hex[:8])

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {CONFIDENCE}, got {self.confidence!r}")
        if not self.skill or not self.action:
            raise ValueError("skill and action are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        evidence = tuple(Evidence(**e) for e in data.get("evidence", ()))
        rest = {k: v for k, v in data.items() if k != "evidence"}
        rest["missing"] = tuple(rest.get("missing", ()))
        return cls(evidence=evidence, **rest)


class RecordBook:
    """Append-only list of records for one agent run."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []

    def add(self, record: DecisionRecord) -> DecisionRecord:
        self._records.append(record)
        return record

    def all(self) -> list[DecisionRecord]:
        return list(self._records)

    def with_status(self, status: str) -> list[DecisionRecord]:
        return [r for r in self._records if r.status == status]

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]
