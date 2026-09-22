"""Pre-flight (T4.9): refuse a live write run if the platform drifted from the fixture."""
from __future__ import annotations

from typing import Any

from agent.config import KEYSTONE_INCOMING_ALLOWLIST
from agent.safe_reads import folder_named, folders_by_id, list_all


class PreflightFailed(Exception):
    pass


def check(rt: Any, fixture: dict[str, Any]) -> list[str]:
    """Problems found (empty list = safe to run)."""
    problems = list(rt.catalog.check_required())
    fixture_hash = (fixture.get("_manifest") or {}).get("tool_hash")
    if fixture_hash and fixture_hash != rt.catalog.hash():
        problems.append(f"tool catalogue changed (fixture {fixture_hash}, live {rt.catalog.hash()}): re-capture fixtures")
    incoming = folder_named(folders_by_id(rt.admin_mcp), "Incoming")
    if not incoming:
        return problems + ["no Incoming folder"]
    live_rows = {r["id"]: r for r in list_all(rt.admin_mcp, "FileAttachment.list", folder_id=incoming["id"])}
    if rt.settings.business == "keystone" and set(live_rows) != set(KEYSTONE_INCOMING_ALLOWLIST):
        problems.append(f"Incoming holds {sorted(set(live_rows) ^ set(KEYSTONE_INCOMING_ALLOWLIST))} beyond/instead of the 9 allow-listed files")
    baseline = {r["id"]: r for r in fixture["tables"]["FileAttachment"]}
    for file_id, row in live_rows.items():
        base = baseline.get(file_id)
        if base is None:
            problems.append(f"{file_id} is not in the fixture")
        elif row.get("updated_at") != base.get("updated_at"):
            problems.append(f"{row.get('filename')} changed since the fixture (updated_at {row.get('updated_at')})")
        elif "untriaged" not in (row.get("tags") or ""):
            problems.append(f"{row.get('filename')} is no longer tagged 'untriaged'")
    return problems


def require_ok(rt: Any, fixture: dict[str, Any]) -> None:
    problems = check(rt, fixture)
    rt.trace.write("preflight", ok=not problems, problems=problems)
    if problems:
        raise PreflightFailed("Pre-flight failed; nothing was written:\n  - " + "\n  - ".join(problems))
