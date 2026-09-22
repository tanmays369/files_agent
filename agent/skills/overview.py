"""A12: contradiction detector.

On Keystone the Drive screen, /api/drive/records/overview and /api/drive/files/*
count only files with entity_type='Drive' (0), while the record list has 15
files in Drive folders (bug F3). This skill reports both and explains why.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from agent.safe_reads import where
from agent.skills.common import Skill, SkillContext, ev


def run(ctx: SkillContext, args: dict[str, Any]) -> dict[str, Any]:
    status, overview = ctx.session.request("GET", "/api/drive/records/overview")
    ov_total = ((overview or {}).get("files") or {}).get("total") if status == 200 and isinstance(overview, dict) else None
    files = ctx.files()
    in_folders = [f for f in files if f.get("folder_id")]
    drive_marked = where(files, entity_type="Drive")
    per_folder = Counter(ctx.folder_name(f["folder_id"]) for f in in_folders)
    disagree = ov_total is not None and ov_total != len(in_folders)
    action = "overview_unavailable" if ov_total is None else ("contradiction" if disagree else "consistent")
    ctx.record(skill="drive_overview", action=action, status="info",
               confidence="strong", details={"overview_total": ov_total, "records_total": len(files),
                                             "in_folders": len(in_folders), "entity_type_drive": len(drive_marked)},
               evidence=[ev("overview", f"/api/drive/records/overview files.total = {ov_total}"),
                         ev("record_list", f"FileAttachment rows = {len(files)}, in Drive folders = {len(in_folders)}"),
                         ev("drive_marked", f"rows with entity_type 'Drive' = {len(drive_marked)}")])
    lines = [f"The record list holds {len(files)} files; {len(in_folders)} of them are in Drive folders "
             f"({', '.join(f'{n}: {c}' for n, c in sorted(per_folder.items()))})."]
    if ov_total is None:
        lines.append(f"I could not read the storage overview (HTTP {status}), so I can't compare it; "
                     "the numbers above come from the record list.")
    elif disagree:
        why = (f"because they only count files marked entity_type 'Drive' ({len(drive_marked)} here)"
               if ov_total == len(drive_marked) else "for a reason I could not confirm from the records")
        lines.append(f"The Drive screen and the storage overview report {ov_total}, {why}. "
                     "I used the record list, which shows what is actually in the folders.")
    else:
        lines.append(f"The storage overview agrees ({ov_total}).")
    return {"overview_total": ov_total, "records_total": len(files), "in_folders": len(in_folders),
            "per_folder": dict(per_folder), "contradiction": disagree, "answer_text": " ".join(lines)}


SKILL = Skill(
    name="drive_overview",
    description="Count files in Drive and explain any disagreement between the Drive screen/overview and the record list. Read-only.",
    input_schema={"type": "object", "properties": {}},
    run=run,
)
