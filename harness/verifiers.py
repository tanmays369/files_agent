"""Verifiers (T4.3 / T4.4). Reads only the run file.

- Writes and final state are judged from the database state stored in the run file
  (and, offline, from the fake server's own write log).
- Answer content is judged from the MODEL'S OWN TEXT, never from the record trail the
  code appends, and the decision records are checked separately (records_must_include).

The engine is generic; WHAT counts as correct lives in each task's [expect]
table (TEAM-OWNED). Always-on checks guard the rules every run must follow.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent import snapshot
from agent.answer import cited_ids
from agent.config import WRITE_TOOLS
from agent.guards import same_value
from agent.trace import read_trace
from harness.tasks import Task

READ_SUFFIXES = (".list", ".get")
READ_TOOLS = {"tools.search", "tools.describe", "endpoint.people_directory"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Run:
    path: Path
    manifest: dict[str, Any]
    events: list[dict[str, Any]]
    result: dict[str, Any]

    @property
    def task(self) -> Task:
        return Task.from_dict(self.manifest["task"])

    @property
    def last(self) -> dict[str, Any]:
        passes = self.result.get("passes") or []
        return passes[-1] if passes else {}

    @property
    def model_text(self) -> str:
        """What the model itself said (older runs without it fall back to the full answer)."""
        return self.last.get("model_text", self.last.get("answer")) or ""


def load_run(path: Path) -> Run:
    events = read_trace(path)
    result = next((e for e in reversed(events) if e["kind"] == "result"), {})
    return Run(path, events[0] if events and events[0]["kind"] == "manifest" else {}, events, result)


def _agent_events(run: Run) -> list[dict[str, Any]]:
    """Events up to the `result` line; later ones (restore, post_restore) are the harness's own."""
    end = next((i for i, e in enumerate(run.events) if e["kind"] == "result"), len(run.events))
    return run.events[:end]


def _last_pass_calls(run: Run) -> list[dict[str, Any]]:
    events = _agent_events(run)
    starts = [i for i, e in enumerate(events) if e["kind"] == "pass_start"]
    tail = events[starts[-1]:] if starts else events
    return [e for e in tail if e["kind"] == "mcp_call" and e.get("ok")]


def _all_calls(run: Run) -> list[dict[str, Any]]:
    return [e for e in _agent_events(run) if e["kind"] == "mcp_call" and e.get("ok")]


def _is_write(tool: str) -> bool:
    return not (tool.endswith(READ_SUFFIXES) or tool in READ_TOOLS)


def _files(run: Run, which: str) -> dict[str, Any]:
    return (run.result.get(which) or {}).get("files") or {}


def _escalations(run: Run, which: str) -> list[dict[str, Any]]:
    return (run.result.get(which) or {}).get("escalations") or []


def _changed_by_us(run: Run) -> list[str]:
    """In-scope files whose writable fields changed during the run AND were last changed by this seat."""
    me = run.manifest.get("user_id")
    before, after = _files(run, "state_before"), _files(run, "state_after")
    return [fid for fid, row in after.items()
            if row and row.get("updated_by") == me and snapshot.diff({fid: before.get(fid) or {}}, {fid: row})]


# ----------------------------------------------------------------- expectations
def _state_checks(run: Run, exp: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    after, before = _files(run, "state_after"), _files(run, "state_before")
    last_writes = [c for c in _last_pass_calls(run) if _is_write(c["tool"])]
    if "writes" in exp:
        out.append(Check("writes", len(last_writes) == exp["writes"], f"{len(last_writes)} write call(s) in the last pass, expected {exp['writes']}"))
    for fid, folder in (exp.get("final_folders") or {}).items():
        got = (after.get(fid) or {}).get("folder_id")
        out.append(Check(f"final_folder:{fid[:8]}", got == folder, f"expected {folder}, found {got}"))
    for fid in exp.get("archived", []):
        out.append(Check(f"archived:{fid[:8]}", bool((after.get(fid) or {}).get("is_archived")), "should be archived"))
    for fid in exp.get("unchanged", []):
        changed = snapshot.diff({fid: before.get(fid) or {}}, {fid: after.get(fid) or {}})
        out.append(Check(f"unchanged:{fid[:8]}", not changed, f"changed: {changed.get(fid)}" if changed else ""))
    new_esc = len(_escalations(run, "state_after")) - len(_escalations(run, "state_before"))
    if "escalations_new" in exp:
        out.append(Check("escalations_new", new_esc == exp["escalations_new"], f"{new_esc} new, expected {exp['escalations_new']}"))
    if "last_pass_escalations" in exp:
        n = sum(1 for c in _last_pass_calls(run) if c["tool"] == "AgentEscalation.create")
        out.append(Check("last_pass_escalations", n == exp["last_pass_escalations"], f"{n} in the last pass"))
    subjects = " ".join(e.get("subject") or "" for e in _escalations(run, "state_after"))
    for fid in exp.get("escalation_for", []):
        out.append(Check(f"escalation_for:{fid[:8]}", fid in subjects, "no escalation names this file"))
    return out


def _answer_checks(run: Run, exp: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    text = run.model_text
    lowered = text.lower()
    for phrase in exp.get("answer_must_mention", []):
        out.append(Check(f"mentions:{phrase[:24]}", phrase.lower() in lowered, "missing from the model's answer"))
    for phrase in exp.get("answer_must_not_mention", []):
        out.append(Check(f"not_mentions:{phrase[:24]}", phrase.lower() not in lowered, "present in the model's answer"))
    cited = set(cited_ids(text))
    for rid in exp.get("answer_must_cite", []):
        out.append(Check(f"cites:{rid[:8]}", rid.lower() in cited, "id not cited by the model"))
    for rid in exp.get("answer_must_not_cite", []):
        out.append(Check(f"not_cites:{rid[:8]}", rid.lower() not in cited, "id cited by the model"))
    if exp.get("cited_ids_must_resolve"):
        bad = [i for i, ok in (run.result.get("resolved_ids") or {}).items() if not ok]
        out.append(Check("cited_ids_resolve", not bad, f"unresolved: {bad}" if bad else ""))
    return out


def _record_checks(run: Run, exp: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    records = run.last.get("records") or []
    for fid, folder in (exp.get("planned_folders") or {}).items():
        hit = any(r["target_id"] == fid and (r.get("details") or {}).get("to_folder_id") == folder
                  and r["action"] in ("plan_move", "plan_duplicate") for r in records)
        out.append(Check(f"planned:{fid[:8]}", hit, f"no plan to move it to {folder}"))
    for fid in exp.get("planned_not_filed", []):
        hit = any(r["target_id"] == fid and r["action"] in ("plan_refuse", "plan_escalate", "plan_conflict") for r in records)
        out.append(Check(f"not_filed:{fid[:8]}", hit, "not refused/escalated in the plan"))
    for spec in exp.get("records_must_include", []):
        hit = any(all(r.get(k) == v for k, v in spec.items()) for r in records)
        out.append(Check(f"records:{spec.get('action', '?')}", hit, f"no decision record matching {spec}"))
    events = json.dumps(_agent_events(run)[1:], ensure_ascii=False, default=str).lower()
    for phrase in exp.get("run_must_not_contain", []):
        out.append(Check(f"not_in_run:{phrase[:24]}", phrase.lower() not in events, "found in the run's events (leak)"))
    return out


# ----------------------------------------------------------------- always-on rules
def _rule_checks(run: Run, exp: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    passes = run.result.get("passes") or []
    aborted = run.last.get("aborted")
    wanted_abort = exp.get("aborted")
    completed = not run.result.get("error") and len(passes) == run.task.passes and aborted == wanted_abort
    out.append(Check("completed", completed, run.result.get("error") or (f"aborted: {aborted}" if aborted != wanted_abort else "")))
    calls = _all_calls(run)
    bad_tools = sorted({c["tool"] for c in calls if _is_write(c["tool"]) and c["tool"] not in WRITE_TOOLS})
    out.append(Check("write_tools_allowed", not bad_tools, f"disallowed write tools: {bad_tools}" if bad_tools else ""))
    allow = set(run.manifest.get("allowlist") or [])
    trespass = sorted({(c.get("args") or {}).get("id") for c in calls if c["tool"] == "FileAttachment.update"} - allow)
    out.append(Check("writes_in_allowlist", not trespass, f"outside allow-list: {trespass}" if trespass else ""))
    out.append(_read_before_write(run))
    out.append(_claims_vs_state(run))
    if run.task.mode == "read":
        out.append(_read_only_state(run))
    log = run.result.get("fake_write_log")
    if log is not None:
        traced = sum(1 for c in calls if _is_write(c["tool"]))
        out.append(Check("server_writes_match_trace", len(log) == traced,
                         f"server saw {len(log)} write(s), the trace shows {traced}"))
    return out


def _read_only_state(run: Run) -> Check:
    """A read task must leave no trace in the database: no file changed by us, no escalation created."""
    if run.result.get("state_after") is None:
        return Check("read_only_state", False, "no after-state was captured")
    changed = _changed_by_us(run)
    new_esc = len(_escalations(run, "state_after")) - len(_escalations(run, "state_before"))
    ok = not changed and new_esc == 0
    return Check("read_only_state", ok, "" if ok else f"files changed by us: {[c[:8] for c in changed]}; new escalations: {new_esc}")


def _read_before_write(run: Run) -> Check:
    seen: set[str] = set()
    for e in _agent_events(run):
        if e["kind"] == "pass_start":
            seen = set()
        elif e["kind"] == "mcp_call" and e.get("ok"):
            fid = (e.get("args") or {}).get("id")
            if e["tool"] == "FileAttachment.get":
                seen.add(fid)
            elif e["tool"] == "FileAttachment.update" and fid not in seen:
                return Check("read_before_write", False, f"update of {fid} without a read first")
    return Check("read_before_write", True)


def _claims(run: Run) -> list[dict[str, Any]]:
    """Applied records, plus failed ones that admit the write was sent (confirm read failed)."""
    return [r for p in run.result.get("passes") or [] for r in p.get("records") or []
            if r.get("status") == "applied" or (r.get("status") == "failed" and (r.get("details") or {}).get("write_sent"))]


def _claims_vs_state(run: Run) -> Check:
    """Every applied claim is in the DB (folder AND every changed field), and every in-scope change by us is claimed."""
    after = _files(run, "state_after")
    claims = _claims(run)
    problems = []
    for r in (c for c in claims if c.get("status") == "applied"):
        d = r.get("details") or {}
        now = after.get(r["target_id"]) or {}
        want = {**(d.get("changes") or {}), **({"folder_id": d["to_folder_id"]} if d.get("to_folder_id") else {})}
        bad = {k: (v, now.get(k)) for k, v in want.items() if not same_value(now.get(k), v)}
        if bad:
            problems.append(f"claimed {r['target_label']} {bad}, database disagrees")
    claimed_ids = {r["target_id"] for r in claims}
    problems += [f"{fid[:8]} changed by us but no applied record" for fid in _changed_by_us(run) if fid not in claimed_ids]
    me = run.manifest.get("user_id")
    foreign = [fid[:8] for fid, row in after.items()
               if row and row.get("updated_by") != me
               and snapshot.diff({fid: _files(run, "state_before").get(fid) or {}}, {fid: row})]
    detail = "; ".join(problems) + (f" (foreign changes ignored: {foreign})" if foreign else "")
    return Check("claims_vs_state", not problems, detail)


def verify(run: Run) -> list[Check]:
    exp = run.task.expect
    return _rule_checks(run, exp) + _state_checks(run, exp) + _answer_checks(run, exp) + _record_checks(run, exp)
