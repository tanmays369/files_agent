"""A6: duplicate detection that is honest about how sure it is.

The recorded content_hash is client-writable on Keystone rows and can't be
recomputed (no bytes are stored), so a match is reported as "duplicate per
recorded metadata", never as byte-verified. A hash shared by files with
different names or sizes is rejected as untrustworthy (Suryodaya: one hash on
21 different files).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from agent.skills.common import Skill, SkillContext, ev

COPY_SUFFIX = re.compile(r"\s*\(\d+\)(?=\.[^.]+$|$)")


def stem(filename: str) -> str:
    return COPY_SUFFIX.sub("", filename or "").strip().lower()


@dataclass(frozen=True)
class DuplicateGroup:
    original: dict[str, Any]
    copies: tuple[dict[str, Any], ...]
    basis: str  # "recorded hash + size + name" or "name + size (suspected)"


def _pick_original(rows: list[dict[str, Any]]) -> dict[str, Any]:
    plain = [r for r in rows if not COPY_SUFFIX.search(r.get("filename", ""))]
    pool = plain or rows
    return min(pool, key=lambda r: (r.get("created_at") or "", r.get("id")))


def untrustworthy_hashes(files: list[dict[str, Any]]) -> set[str]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in files:
        if f.get("content_hash"):
            by_hash[f["content_hash"]].append(f)
    return {h for h, rows in by_hash.items()
            if len({stem(r.get("filename", "")) for r in rows}) > 1 or len({r.get("size_bytes") for r in rows}) > 1}


def find_groups(files: list[dict[str, Any]]) -> list[DuplicateGroup]:
    bad = untrustworthy_hashes(files)
    buckets: dict[tuple[str, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for f in files:
        h = f.get("content_hash")
        key = ("hash", h, f.get("size_bytes")) if h and h not in bad else ("name", stem(f.get("filename", "")), f.get("size_bytes"))
        buckets[key].append(f)
    groups = []
    for (kind, _k, _size), rows in buckets.items():
        if len(rows) < 2 or (kind == "hash" and len({stem(r.get("filename", "")) for r in rows}) > 1):
            continue
        original = _pick_original(rows)
        groups.append(DuplicateGroup(original, tuple(r for r in rows if r is not original),
                                     "recorded hash + size + name" if kind == "hash" else "name + size (suspected)"))
    return groups


def run(ctx: SkillContext, args: dict[str, Any]) -> dict[str, Any]:
    files = ctx.files()
    folder_name = (args.get("folder_name") or "").strip()
    groups = find_groups(files)
    if folder_name:
        ids = {f["id"] for f in files if ctx.folder_name(f.get("folder_id")).lower() == folder_name.lower()}
        groups = [g for g in groups if g.original["id"] in ids or any(c["id"] in ids for c in g.copies)]
    bad = untrustworthy_hashes(files)
    lines = []
    for g in groups:
        for copy in g.copies:
            ctx.record(skill="find_duplicates", action="duplicate", status="info", target_id=copy["id"],
                       target_label=copy.get("filename"), confidence="medium",
                       evidence=[ev("duplicate_of", g.original.get("filename", ""), source_id=g.original["id"]), ev("basis", g.basis)],
                       details={"original_id": g.original["id"]})
            lines.append(f"{copy.get('filename')} ({copy['id']}) duplicates {g.original.get('filename')} "
                         f"({g.original['id']}), per {g.basis}; not byte-verified because no file bytes are stored.")
    if bad:
        lines.append(f"{len(bad)} content hash value(s) are shared by unrelated files, so they were not trusted.")
    return {"groups": [{"original": g.original["id"], "copies": [c["id"] for c in g.copies], "basis": g.basis} for g in groups],
            "untrusted_hashes": len(bad), "answer_text": " ".join(lines) or "No duplicates found."}


SKILL = Skill(
    name="find_duplicates",
    description="Find duplicate files (recorded hash + size + name, or name + size as 'suspected'). Read-only; never deletes.",
    input_schema={"type": "object", "properties": {"folder_name": {"type": "string", "description": "Optional folder to limit the search"}}},
    run=run,
)
