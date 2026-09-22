"""Leak guard (A11): rows owned by apps this seat can't open never show their titles.

A FileAttachment row whose entity_type belongs to an app outside the seat (e.g.
EsignDocument: offer letters, contracts) is replaced by a placeholder wherever
the model, a skill or a trace could see it. The row's id, entity type, size and
folder stay, so counts are still correct.
"""
from __future__ import annotations

from typing import Any, Callable

OPEN_ENTITY_TYPES = {None, "", "Drive"}
PRIVATE_FIELDS = ("description", "tags", "storage_path", "from_email", "from_name", "message_subject", "thread_id", "party_id")

CanList = Callable[[str], bool]


def is_withheld(row: dict[str, Any], can_list: CanList) -> bool:
    entity_type = row.get("entity_type")
    return entity_type not in OPEN_ENTITY_TYPES and not can_list(entity_type)


def sanitise_file(row: dict[str, Any], can_list: CanList) -> dict[str, Any]:
    if not is_withheld(row, can_list):
        return row
    placeholder = f"{row['entity_type']}-attachment-{str(row.get('id', ''))[:8]}.pdf"
    return {**row, **{f: None for f in PRIVATE_FIELDS}, "filename": placeholder, "_display": placeholder}


def sanitise_payload(payload: Any, can_list: CanList) -> Any:
    """Sanitise a FileAttachment list page or a single FileAttachment row; anything else is returned as is."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return {**payload, "data": [sanitise_file(r, can_list) if _is_file_row(r) else r for r in payload["data"]]}
    return sanitise_file(payload, can_list) if _is_file_row(payload) else payload


def _is_file_row(row: Any) -> bool:
    return isinstance(row, dict) and "entity_type" in row and "filename" in row
