"""Snapshot and restore (T2.9 / A8): the undo log for live runs on the shared tenant.

- Before the first write, snapshot the writable fields of the allow-listed rows.
- While the run writes, a write journal (writes-N.json) records exactly what we sent.
- Afterwards, restore puts back ONLY the fields we wrote, and only where the value is
  still the one we wrote. Anything another team changed is reported as a conflict and
  left alone: the agent must never become the thing that overwrites other people's work.
- Restore refuses snapshots that hold ids outside the allow-list, and keeps going when
  one row fails, so one bad row can't leave the others un-restored.

Also usable on its own:
  AS_ALLOW_WRITES=1 python -m harness restore runs/<set>/<task>/snapshot-1.json --target live --live-apply
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.guards import same_value
from agent.mcp_client import McpError

WRITABLE_FIELDS = ("folder_id", "filename", "tags", "description", "is_archived", "party_id", "entity_type", "entity_id")


class RestoreRefused(Exception):
    """The snapshot can't be trusted; nothing was restored."""


def take(mcp: Any, ids: frozenset[str] | set[str]) -> dict[str, dict[str, Any]]:
    snap = {}
    for file_id in sorted(ids):
        row = mcp.call("FileAttachment.get", {"id": file_id})
        snap[file_id] = {f: row.get(f) for f in (*WRITABLE_FIELDS, "updated_at", "updated_by")}
    return snap


def save(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def writes_path(snapshot_path: Path) -> Path:
    """snapshot-1.json -> writes-1.json (the write journal saved beside it)."""
    return snapshot_path.with_name(snapshot_path.name.replace("snapshot", "writes", 1))


class WriteJournal:
    """Every write of a live run, saved to disk the moment it is sent."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.entries: list[dict[str, Any]] = []

    def add(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        if self.path is not None:
            save(self.entries, self.path)


def diff(snap: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{file_id: {field: (snapshot_value, current_value)}} for writable fields that differ."""
    out = {}
    for file_id, original in snap.items():
        now = current.get(file_id) or {}
        changed = {f: (original.get(f), now.get(f)) for f in WRITABLE_FIELDS if not same_value(original.get(f), now.get(f))}
        if changed:
            out[file_id] = changed
    return out


def _ours(writes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{file_id: {field: the value we last wrote}} from the write journal."""
    out: dict[str, dict[str, Any]] = {}
    for w in writes:
        if w.get("tool") == "FileAttachment.update":
            out.setdefault(w["id"], {}).update(w.get("changes") or {})
    return out


def plan_restore(snap: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]],
                 writes: list[dict[str, Any]] | None, me: str | None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Split every difference into (fields we may put back, fields someone else changed).

    With the write journal: a field is ours only if we wrote it and it still holds our value.
    Without it (journal lost): a row is ours only if this seat was the last to change it.
    """
    ours = _ours(writes) if writes is not None else None
    todo: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, dict[str, Any]] = {}
    for file_id, fields in diff(snap, current).items():
        row = current.get(file_id) or {}
        for field, (old, now) in fields.items():
            if ours is not None:
                mine = field in ours.get(file_id, {}) and same_value(ours[file_id][field], now)
            else:
                mine = bool(me) and row.get("updated_by") == me
            if mine:
                todo.setdefault(file_id, {})[field] = old
            else:
                conflicts.setdefault(file_id, {})[field] = {"snapshot": old, "now": now, "updated_by": row.get("updated_by")}
    return todo, conflicts


def restore(mcp: Any, snap: dict[str, dict[str, Any]], trace: Any, *, allowlist: frozenset[str] | set[str],
            writes: list[dict[str, Any]] | None = None, me: str | None = None) -> dict[str, Any]:
    """Put back what we changed. Raises RestoreRefused (nothing done) or RuntimeError (incomplete)."""
    outside = sorted(set(snap) - set(allowlist))
    if outside:
        raise RestoreRefused(f"snapshot holds ids outside the write allow-list {outside}; nothing restored")
    todo: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, dict[str, Any]] = {}
    failed = {}
    for file_id in sorted(snap):
        try:
            # Decide from a read taken right before this row's write, not from an earlier batch read,
            # so an edit another team made meanwhile is seen as a conflict. (The platform has no
            # compare-and-set, so only a change landing inside this one round trip could slip through.)
            mine, theirs = plan_restore({file_id: snap[file_id]}, take(mcp, {file_id}), writes, me)
            conflicts.update(theirs)
            if mine:
                todo.update(mine)
                mcp.call("FileAttachment.update", {"id": file_id, **mine[file_id]})
        except McpError as err:
            failed[file_id] = str(err)
    after = take(mcp, set(todo)) if todo else {}
    remaining: dict[str, dict[str, Any]] = {}
    overtaken: set[str] = set()
    for fid, changed in diff({fid: snap[fid] for fid in todo}, after).items():
        fields = {f: v for f, v in changed.items() if f in todo[fid]}
        if not fields:
            continue
        if me and after[fid].get("updated_by") not in (None, me):  # another team changed it after our restore
            overtaken.add(fid)
            conflicts.setdefault(fid, {}).update({f: {"snapshot": old, "now": now, "updated_by": after[fid].get("updated_by")}
                                                  for f, (old, now) in fields.items()})
        else:
            remaining[fid] = fields
    report = {"restored": sorted(set(todo) - set(failed) - set(remaining) - overtaken), "failed": failed,
              "remaining": remaining, "conflicts_left_alone": conflicts}
    trace.write("restore", **report)
    if failed or remaining:
        raise RuntimeError(f"restore incomplete for {sorted(set(failed) | set(remaining))}; fix the cause, then re-run "
                           "`python -m harness restore <snapshot> --target live --live-apply`")
    return report
