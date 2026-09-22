"""Reads that avoid the platform's filter traps (T1.5).

Traps avoided (all verified 21-22 Sept 2026, bugs L2/L3/L5/F4/F5):
- `ne:` silently drops rows whose value is NULL      -> negate in code
- a comma in a filter value becomes an OR list       -> never send it; filter in code
- REST sort_order is not validated                   -> sort in code
- /api/export ignores unknown filters                -> never used
- /api/search stops at 5 results per type            -> page the entity list instead
"""
from __future__ import annotations

from typing import Any

PAGE = 500
SAFE_SERVER_FILTERS = {"id", "folder_id", "entity_id", "entity_type", "code", "file_id", "content_hash", "parent_id"}


def list_all(mcp: Any, tool: str, **filters: Any) -> list[dict[str, Any]]:
    """Page through a .list tool. Only exact, comma-free filters go to the server; all are re-checked here."""
    server = {k: v for k, v in filters.items()
              if k in SAFE_SERVER_FILTERS and v is not None and "," not in str(v) and not str(v).startswith(("ne:", "gt:", "lt:"))}
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = mcp.call(tool, {**server, "limit": PAGE, "offset": offset})
        batch = (page or {}).get("data", [])
        rows.extend(batch)
        offset += len(batch)
        if not batch or offset >= int((page or {}).get("total", 0)):
            break
    return where(rows, **filters)


def where(rows: list[dict[str, Any]], **equals: Any) -> list[dict[str, Any]]:
    """Exact equality in code; `None` means 'field is empty'."""
    return [r for r in rows if all(_same(r.get(k), v) for k, v in equals.items())]


def not_equal(rows: list[dict[str, Any]], field: str, value: Any) -> list[dict[str, Any]]:
    """Correct 'not equal': rows with an empty value are included (unlike the platform's ne:)."""
    return [r for r in rows if not _same(r.get(field), value)]


def _same(actual: Any, wanted: Any) -> bool:
    if wanted is None:
        return actual in (None, "")
    if isinstance(wanted, bool):
        return bool(actual) == wanted
    return str(actual) == str(wanted)


def folders_by_id(mcp: Any) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in list_all(mcp, "DriveFolder.list")}


def folder_named(folders: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = name.strip().lower()
    return next((f for f in folders.values() if f.get("name", "").strip().lower() == wanted), None)


def find_files_by_name(files: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """Exact filename first; otherwise a case-insensitive exact match; never a loose substring."""
    exact = [f for f in files if f.get("filename") == name]
    return exact or [f for f in files if (f.get("filename") or "").lower() == name.lower()]
