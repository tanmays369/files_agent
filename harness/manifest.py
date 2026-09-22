"""Run manifest (T4.7): the first line of every run file, so any score can be traced and reproduced."""
from __future__ import annotations

import subprocess
from typing import Any

from agent.config import REPO_ROOT
from agent.trace import now_iso


def git_state() -> dict[str, Any]:
    """The commit that produced a run. A failed git command (e.g. no commits yet) gives "no-commit", never junk."""
    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    status = git("status", "--porcelain")
    return {"commit": git("rev-parse", "--verify", "HEAD") or "no-commit", "dirty": status is None or bool(status)}


def stub_manifest(task: Any, repeat_index: int, target: str, model_kind: str) -> dict[str, Any]:
    """Header for a run whose set-up failed before the full manifest could be built."""
    return {"schema": 1, "task": task.to_dict(), "repeat_index": repeat_index, "target": target,
            "business": task.business, "model": model_kind, "git": git_state(), "allowlist": [],
            "setup_failed": True, "started_at": now_iso()}


def build_manifest(task: Any, repeat_index: int, target: str, model_kind: str, rt: Any, fixture: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema": 1,
        "task": task.to_dict(),
        "repeat_index": repeat_index,
        "target": target,
        "business": task.business,
        "model": rt.settings.model if model_kind == "anthropic" else "scripted",
        "temperature": 0.0,
        "git": git_state(),
        "tool_hash": rt.catalog.hash(),
        "fixture": {"dir": fixture.get("_dir"), "hash": fixture.get("_manifest", {}).get("fixture_hash")} if fixture else None,
        "user_id": rt.session.me().get("id"),
        "allowlist": sorted(rt.guard.allowlist),
        "started_at": now_iso(),
    }
