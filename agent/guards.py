"""Write guard (T2.2). Every write in the agent goes through here.

- Plan-only is the default: nothing is written unless mode == "apply".
- File writes only to allow-listed row ids.
- Pre-read: the row must still look the way the plan expected (else StaleRow).
  Callers pass `updated_at` too, so any change by anyone since the plan skips the row.
- Permission check: `_permissions.write` and `_readonly_fields` from the row itself.
- Post-read: confirm the change landed; a mismatch means someone overwrote us.
- Every write is recorded the moment it is sent, before the confirming read, so a
  failed confirm can never hide a write that happened.
"""
from __future__ import annotations

from typing import Any, Callable

from agent.config import WRITE_TOOLS
from agent.mcp_client import McpError
from agent.trace import Trace


class WriteBlocked(Exception):
    """A write was refused before anything was sent."""


class StaleRow(Exception):
    """The row changed since it was planned; the write was skipped."""

    def __init__(self, message: str, current: dict[str, Any]) -> None:
        super().__init__(message)
        self.current = current


class WriteNotConfirmed(Exception):
    """The post-write read does not show our change (possible clobber)."""


class WriteGuard:
    def __init__(self, mcp: Any, trace: Trace, mode: str, allowlist: frozenset[str]) -> None:
        if mode not in ("plan", "apply"):
            raise ValueError("mode must be 'plan' or 'apply'")
        self.mcp = mcp
        self.trace = trace
        self.mode = mode
        self.allowlist = allowlist
        self.writes: list[dict[str, Any]] = []
        self.journal: Callable[[dict[str, Any]], None] | None = None

    @property
    def can_write(self) -> bool:
        return self.mode == "apply"

    def _reserve(self, calls: int) -> None:
        budget = getattr(self.mcp, "budget", None)
        if budget is not None:
            budget.reserve(calls)

    def _require_apply(self, what: str) -> None:
        if not self.can_write:
            self.trace.write("write_blocked", reason="plan-only", what=what)
            raise WriteBlocked(f"plan-only mode: {what} not sent")

    def update_file(self, file_id: str, changes: dict[str, Any], expect: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_apply(f"update {file_id}")
        if file_id not in self.allowlist:
            self.trace.write("write_blocked", reason="not allow-listed", file_id=file_id)
            raise WriteBlocked(f"{file_id} is not in the write allow-list")
        self._reserve(3)  # read, write, confirm: never start a write the budget would cut off
        before = self.mcp.call("FileAttachment.get", {"id": file_id})
        stale = {k: (v, before.get(k)) for k, v in (expect or {}).items() if not same_value(before.get(k), v)}
        if stale:
            self.trace.write("stale_row", file_id=file_id, changed=stale)
            raise StaleRow(f"{before.get('filename')} changed since the plan: {stale}", before)
        if not (before.get("_permissions") or {}).get("write"):
            raise WriteBlocked(f"no write permission on {file_id}")
        readonly = set(before.get("_readonly_fields") or []) & set(changes)
        if readonly:
            raise WriteBlocked(f"read-only fields {sorted(readonly)} on {file_id}")
        entry = {"tool": "FileAttachment.update", "id": file_id, "changes": changes}
        self._send("FileAttachment.update", {"id": file_id, **changes}, entry)
        try:
            after = self.mcp.call("FileAttachment.get", {"id": file_id})
        except McpError as err:
            self.trace.write("write_not_confirmed", file_id=file_id, error=str(err))
            raise WriteNotConfirmed(f"the write was sent but the confirming read failed ({err}), so it is unconfirmed") from err
        lost = {k: v for k, v in changes.items() if not same_value(after.get(k), v)}
        if lost:
            self.trace.write("write_not_confirmed", file_id=file_id, lost=lost)
            raise WriteNotConfirmed(f"our change did not stick: {', '.join(sorted(lost))} no longer hold our values "
                                    "(another seat changed the file right after our write); left as it is now")
        return {"before": before, "after": after}

    def create(self, tool: str, args: dict[str, Any]) -> Any:
        """Create an AgentSession or AgentEscalation (the only other writes allowed)."""
        self._require_apply(tool)
        if tool not in WRITE_TOOLS or tool == "FileAttachment.update":
            raise WriteBlocked(f"{tool} is not an allowed create tool")
        self._reserve(1)
        result = self._send(tool, args, {"tool": tool, "args": args})
        return result

    def _send(self, tool: str, args: dict[str, Any], entry: dict[str, Any]) -> Any:
        """Send one write and log it. If the call errors, the platform may still have applied it, so it is
        logged as `uncertain`: restore and the records then treat it as possibly ours, never as nothing."""
        try:
            result = self.mcp.call(tool, args)
        except McpError:
            self._log_write({**entry, "uncertain": True})
            raise
        self._log_write({**entry, "id": entry.get("id") or (result or {}).get("id")})
        return result

    def _log_write(self, entry: dict[str, Any]) -> None:
        """Record a write the moment it is sent; the journal (live runs) saves it to disk for restore."""
        self.writes.append(entry)
        if self.journal is not None:
            self.journal(entry)


def same_value(a: Any, b: Any) -> bool:
    """Compare field values the way the platform stores them (is_archived comes back as 0/1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return a == b
