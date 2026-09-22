"""Shared skill types and the per-run context every skill receives."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from agent.privacy import sanitise_file
from agent.records import DecisionRecord, Evidence, RecordBook
from agent.safe_reads import folders_by_id, list_all


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[["SkillContext", dict[str, Any]], dict[str, Any]]


class SkillContext:
    """Everything a skill may use. Writes are only possible through `guard`."""

    def __init__(self, *, mcp: Any, session: Any, guard: Any, trace: Any, catalog: Any,
                 rules: Any, settings: Any, allowlist: frozenset[str]) -> None:
        self.mcp = mcp
        self.session = session
        self.guard = guard
        self.trace = trace
        self.catalog = catalog
        self.rules = rules
        self.settings = settings
        self.allowlist = allowlist
        self.records = RecordBook()
        self.seen_ids: set[str] = set()
        self.escalator: Any = None  # wired by agent.runtime
        self._files: list[dict[str, Any]] | None = None
        self._folders: dict[str, dict[str, Any]] | None = None

    def me(self) -> dict[str, Any]:
        return self.session.me()

    def files(self, refresh: bool = False) -> list[dict[str, Any]]:
        """Every file row; rows of apps this seat can't open come back as placeholders (leak guard)."""
        if self._files is None or refresh:
            self._files = [sanitise_file(r, self.catalog.can_list) for r in list_all(self.mcp, "FileAttachment.list")]
            self.note_ids(*(f.get("id") for f in self._files))
        return self._files

    def folders(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        if self._folders is None or refresh:
            self._folders = folders_by_id(self.mcp)
            self.note_ids(*self._folders)
        return self._folders

    def folder_name(self, folder_id: str | None) -> str:
        if not folder_id:
            return "(not in a folder)"
        return self.folders().get(folder_id, {}).get("name", folder_id)

    def note_ids(self, *ids: Any) -> None:
        self.seen_ids.update(str(i) for i in ids if i)

    def record(self, **kwargs: Any) -> DecisionRecord:
        if "evidence" in kwargs:
            kwargs["evidence"] = tuple(kwargs["evidence"])
        if "missing" in kwargs:
            kwargs["missing"] = tuple(kwargs["missing"])
        return self.records.add(DecisionRecord(**kwargs))

    @staticmethod
    def today() -> str:
        return date.today().isoformat()


def ev(signal: str, detail: str, points_to: str | None = None, source_id: str | None = None) -> Evidence:
    return Evidence(signal=signal, detail=detail, points_to=points_to, source_id=source_id)


def uploader_of(ctx: SkillContext, file_id: str) -> str | None:
    """Who uploaded a file, per DriveAccessLog. Client-written (bug L8), so a lead, not proof."""
    rows = list_all(ctx.mcp, "DriveAccessLog.list", file_id=file_id)
    upload = next((r for r in rows if r.get("action") == "upload"), None)
    if not upload:
        return None
    name, email = upload.get("actor_name"), upload.get("actor_email")
    return f"{name} ({email})" if name and email else (name or email)
