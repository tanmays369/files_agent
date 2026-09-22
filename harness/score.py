"""Scoring (T4.6) and rescoring (T4.8). Reads only the run files; never calls the model or the platform.

A task passes only if every one of its runs passes (pass^k). Scores use the
task definition stored in each run's manifest, so rescoring is reproducible.
`expected.json` (written by `harness run` before each task starts) lists how many
runs each task should have; a run file that is missing counts as a failed run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.verifiers import load_run, verify

EXPECTED_FILE = "expected.json"


def run_files(set_dir: Path) -> list[Path]:
    return sorted(p for p in set_dir.glob("*/*.jsonl"))


def load_expected(set_dir: Path) -> dict[str, int]:
    path = set_dir / EXPECTED_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def expect_runs(set_dir: Path, task_id: str, count: int) -> None:
    """Record, before a task runs, how many run files it must leave behind."""
    set_dir.mkdir(parents=True, exist_ok=True)
    expected = {**load_expected(set_dir), task_id: count}
    (set_dir / EXPECTED_FILE).write_text(json.dumps(expected, indent=2, sort_keys=True), encoding="utf-8")


def _add_missing(set_dir: Path, tasks: dict[str, dict[str, Any]]) -> None:
    for task_id, count in load_expected(set_dir).items():
        entry = tasks.setdefault(task_id, {"runs": 0, "passed": 0, "usd": 0.0, "failures": {}})
        for n in range(1, count + 1):
            if not (set_dir / task_id / f"{n}.jsonl").exists():
                entry["runs"] += 1
                entry["failures"][f"{n}.jsonl"] = ["missing: no run file was written (the run crashed)"]


def score_set(set_dir: Path) -> dict[str, Any]:
    tasks: dict[str, dict[str, Any]] = {}
    for path in run_files(set_dir):
        run = load_run(path)
        checks = verify(run)
        failed = [f"{c.name}: {c.detail}" for c in checks if not c.ok]
        usd = sum((p.get("ledger") or {}).get("usd", 0) for p in run.result.get("passes") or [])
        entry = tasks.setdefault(path.parent.name, {"runs": 0, "passed": 0, "usd": 0.0, "failures": {}})
        entry["runs"] += 1
        entry["passed"] += int(not failed)
        entry["usd"] = round(entry["usd"] + usd, 6)
        if failed:
            entry["failures"][path.name] = failed
    _add_missing(set_dir, tasks)
    for entry in tasks.values():
        entry["pass_all"] = entry["runs"] > 0 and entry["passed"] == entry["runs"]
    total = {"tasks": len(tasks), "tasks_passing_all": sum(e["pass_all"] for e in tasks.values()),
             "usd": round(sum(e["usd"] for e in tasks.values()), 6)}
    return {"set": set_dir.name, "tasks": dict(sorted(tasks.items())), "total": total}


def write_score(set_dir: Path, score: dict[str, Any]) -> Path:
    (set_dir / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True), encoding="utf-8")
    (set_dir / "report.md").write_text(render(score), encoding="utf-8")
    return set_dir / "score.json"


def render(score: dict[str, Any]) -> str:
    lines = [f"# Score: {score['set']}", "", "| Task | Runs | Passed | pass^k | Cost (USD) |", "|---|---|---|---|---|"]
    for tid, e in score["tasks"].items():
        lines.append(f"| {tid} | {e['runs']} | {e['passed']} | {'PASS' if e['pass_all'] else 'FAIL'} | {e['usd']:.4f} |")
    t = score["total"]
    lines += ["", f"**{t['tasks_passing_all']} of {t['tasks']} tasks pass on every run.** Total cost ${t['usd']:.4f}.", ""]
    for tid, e in score["tasks"].items():
        for run_name, failed in e["failures"].items():
            lines.append(f"- {tid}/{run_name}: " + "; ".join(failed))
    return "\n".join(lines) + "\n"


def rescore(set_dir: Path) -> tuple[bool, dict[str, Any]]:
    """Recompute from disk and compare with the saved score.json."""
    fresh = score_set(set_dir)
    saved_path = set_dir / "score.json"
    saved = json.loads(saved_path.read_text(encoding="utf-8")) if saved_path.exists() else None
    return saved == json.loads(json.dumps(fresh, sort_keys=True)), fresh
