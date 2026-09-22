"""A1: part -> current drawing, resistant to look-alike part codes (KJ-BRKT-04)."""
from __future__ import annotations

import re
from typing import Any

from agent.privacy import sanitise_file
from agent.safe_reads import list_all
from agent.skills.common import Skill, SkillContext, ev
from agent.skills.revisions import newest, parse_revision


def tag_set(tags: str | None) -> frozenset[str]:
    """Whole tags only: 'unreleased' is not 'released'."""
    return frozenset(t.strip() for t in (tags or "").lower().split(",") if t.strip())


def normalise_revision(text: Any) -> str:
    """'Rev B', 'rev-b', 'Rev. B', 'revision B', 'B' -> 'B'."""
    return re.sub(r"^REV(?:ISION)?[\s._-]*", "", str(text or "").strip().upper()).strip()


def _file_view(ctx: SkillContext, row: dict[str, Any]) -> dict[str, Any]:
    folder = ctx.folder_name(row.get("folder_id"))
    tags = tag_set(row.get("tags"))
    rev = parse_revision(row.get("filename", ""))
    superseded = bool(row.get("is_archived")) or folder.lower() == "superseded" or "superseded" in tags
    return {"id": row["id"], "filename": row.get("filename"), "folder": folder, "revision": rev.raw if rev else None,
            "revision_obj": rev, "archived": bool(row.get("is_archived")), "tags": row.get("tags"), "tag_set": tags,
            "superseded": superseded}


def _conflicts(views: list[dict[str, Any]]) -> list[str]:
    out = []
    for v in views:
        if "released" in v["tag_set"] and v["superseded"]:
            out.append(f"{v['filename']} is tagged 'released' but archived or in Superseded")
        if "superseded" in v["tag_set"] and not v["archived"]:
            out.append(f"{v['filename']} is tagged 'superseded' but not archived")
        # An odd revision name is reported, never guessed around.
        out.extend(f"{v['filename']}: {flag}" for flag in (v["revision_obj"].flags if v["revision_obj"] else ()))
    live = [v for v in views if not v["superseded"]]
    if len(live) > 1:
        out.append("more than one revision looks current: " + ", ".join(v["filename"] for v in live))
    top, problems = newest([v["revision_obj"] for v in views if v["revision_obj"]])
    out.extend(problems)
    if top and live and all(v["revision_obj"] != top for v in live):
        out.append(f"the newest revision (Rev{top.raw}) is marked superseded while an older one looks current")
    return out


def _lookalikes(items: list[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    c = code.upper()
    return [i for i in items if i.get("code") and i["code"].upper() != c and (c in i["code"].upper() or i["code"].upper() in c)]


def run(ctx: SkillContext, args: dict[str, Any]) -> dict[str, Any]:
    code = str(args.get("part_code", "")).strip()
    asked_rev = normalise_revision(args.get("revision"))
    all_items = list_all(ctx.mcp, "Item.list")
    matches = [i for i in all_items if (i.get("code") or "").upper() == code.upper()]
    others = _lookalikes(all_items, code)
    ctx.note_ids(*(i["id"] for i in matches + others))
    for other in others:
        ctx.record(skill="find_drawing", action="lookalike_part", status="info", target_id=other["id"],
                   target_label=other.get("code"), details={"name": other.get("name")},
                   evidence=[ev("exact_code", f"{other.get('code')} is a different part from {code}")])
    if not matches:
        ctx.record(skill="find_drawing", action="part_not_found", status="refused", target_label=code,
                   missing=["a part with exactly this code"])
        note = " Similar codes exist: " + ", ".join(o["code"] for o in others) + "." if others else ""
        return {"found": False, "answer_text": f"No part has the exact code {code}.{note} I did not guess."}
    if len(matches) > 1:
        ids = ", ".join(i["id"] for i in matches)
        ctx.record(skill="find_drawing", action="ambiguous_part", status="refused", target_label=code,
                   missing=["a single part with this code"], details={"item_ids": [i["id"] for i in matches]})
        return {"found": False, "answer_text": f"{len(matches)} parts share the exact code {code} ({ids}). I did not guess which one you mean."}
    item = matches[0]
    rows = list_all(ctx.mcp, "FileAttachment.list", entity_id=item["id"])
    views = [_file_view(ctx, sanitise_file(r, ctx.catalog.can_list)) for r in rows]
    ctx.note_ids(*(v["id"] for v in views))
    conflicts = _conflicts(views)
    live = [v for v in views if not v["superseded"]]
    current = live[0] if len(live) == 1 and not conflicts else None
    for v in views:
        ctx.record(skill="find_drawing", action="current_drawing" if v is current else ("superseded_drawing" if v["superseded"] else "candidate_drawing"),
                   status="info", target_id=v["id"], target_label=v["filename"],
                   confidence="strong" if v is current else "medium",
                   evidence=[ev("linked_record", f"linked to part {code} ({item['id']})", source_id=item["id"]),
                             ev("folder", v["folder"]), ev("is_archived", str(v["archived"])), ev("tags", v["tags"] or "")],
                   details={"revision": v["revision"], "folder": v["folder"]})
    for c in conflicts:
        ctx.record(skill="find_drawing", action="conflict", status="info", target_label=code, details={"conflict": c})
    return _summary(code, item, views, current, conflicts, others, asked_rev)


def _summary(code: str, item: dict[str, Any], views: list[dict[str, Any]], current: dict[str, Any] | None,
             conflicts: list[str], others: list[dict[str, Any]], asked_rev: str) -> dict[str, Any]:
    lines = []
    if current:
        lines.append(f"The current drawing for part {code} is {current['filename']} ({current['id']}), "
                     f"revision {current['revision']}, in '{current['folder']}'.")
    else:
        reason = "; ".join(conflicts) or ("every linked drawing is superseded" if views else "no drawings are linked to it")
        lines.append(f"I can't name a single current drawing for part {code}: {reason}.")
    for v in views:
        if v["superseded"]:
            lines.append(f"{v['filename']} ({v['id']}) is superseded (archived: {v['archived']}, folder '{v['folder']}').")
    if asked_rev:
        match = next((v for v in views if (v["revision"] or "").upper() == asked_rev), None)
        verdict = ("not found among this part's drawings" if not match else
                   "not current - it is superseded" if match["superseded"] else
                   "current" if match is current else
                   "found, but I can't confirm it is current: " + ("; ".join(conflicts) or "another revision also looks current"))
        lines.append(f"Revision {asked_rev}: {verdict}.")
    for o in others:
        lines.append(f"Note: {o['code']} ({o.get('name')}) is a different part, not a revision of {code}.")
    return {"found": True, "part": code, "item_id": item["id"], "current": current and {k: current[k] for k in ("id", "filename", "folder", "revision")},
            "drawings": [{k: v[k] for k in ("id", "filename", "folder", "revision", "superseded")} for v in views],
            "conflicts": conflicts, "lookalikes": [o["code"] for o in others], "answer_text": " ".join(lines)}


SKILL = Skill(
    name="find_drawing",
    description=("Find the current drawing for a part by its exact part code. Judges each linked drawing by its archived "
                 "flag, folder and tags, checks the revisions in the filenames agree, reports superseded revisions and "
                 "look-alike part codes, and names no current drawing if the signals conflict. Read-only."),
    input_schema={"type": "object", "properties": {
        "part_code": {"type": "string", "description": "Exact part code, e.g. J-BRKT-04"},
        "revision": {"type": "string", "description": "Optional revision to check, e.g. B"}},
        "required": ["part_code"]},
    run=run,
)
