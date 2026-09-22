"""Read-only fixture capture (T1.6) and loading.

  python -m harness capture keystone

Saves one dated snapshot of everything the agent reads, so the fake server can
replay it offline. Titles of files owned by apps this seat can't open (e-sign
offer letters, contracts) are replaced with placeholders before saving.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.auth import Session
from agent.catalog import Catalog
from agent.config import REPO_ROOT, get_settings
from agent.http import HttpTransport
from agent.mcp_client import McpClient
from agent.privacy import sanitise_file
from agent.redact import Redactor
from agent.safe_reads import list_all
from agent.trace import Trace

FIXTURE_ROOT = REPO_ROOT / "harness" / "fixtures"
ITEM_FIELDS = ("id", "code", "name", "_display", "status", "design_file_id", "design_bom_id", "company_id", "_permissions", "_readonly_fields")
PARTY_FIELDS = ("id", "_display", "name", "company_id")
ME_FIELDS = ("id", "email", "name", "roles", "allowed_apps", "company_id")


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: row.get(f) for f in fields if f in row}


def capture(business: str, out_root: Path = FIXTURE_ROOT) -> Path:
    settings = get_settings(business)
    trace = Trace(None, Redactor(settings.secrets()))
    session = Session(HttpTransport(settings.base_url), settings.email, settings.password, trace)
    session.login()
    mcp = McpClient(session, trace)
    mcp.initialize()
    tools = mcp.list_tools()
    _status, overview = session.request("GET", "/api/drive/records/overview")
    _status, office = session.request("GET", "/api/agent/office")
    seat = [s for s in (office or {}).get("seats", []) if s.get("seat_number") == 20] if isinstance(office, dict) else []
    people = mcp.call("endpoint.people_directory", {}) if "endpoint.people_directory" in {t["name"] for t in tools} else {}
    can_list = Catalog.from_tools(tools).can_list
    fixture = {
        "business": business,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "me": _pick(session.me(), ME_FIELDS),
        "tools": tools,
        "tables": {
            "FileAttachment": [sanitise_file(r, can_list) for r in list_all(mcp, "FileAttachment.list")],
            "DriveFolder": list_all(mcp, "DriveFolder.list"),
            "Item": [_pick(r, ITEM_FIELDS) for r in list_all(mcp, "Item.list")],
            "Party": [_pick(r, PARTY_FIELDS) for r in list_all(mcp, "Party.list")],
            "DriveAccessLog": list_all(mcp, "DriveAccessLog.list"),
            "AgentEscalation": [], "AgentSession": [],
        },
        "people_directory": ((people or {}).get("result") or {}).get("items", []),
        "rest": {"/api/drive/records/overview": overview, "/api/agent/office": {"seats": seat}},
    }
    return save(fixture, out_root / business / datetime.now().strftime("%Y-%m-%d"))


def save(fixture: dict[str, Any], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    body = json.dumps(fixture, indent=1, ensure_ascii=False, sort_keys=True)
    (folder / "fixture.json").write_text(body, encoding="utf-8")
    manifest = {
        "business": fixture["business"], "captured_at": fixture["captured_at"],
        "counts": {k: len(v) for k, v in fixture["tables"].items()} | {"tools": len(fixture["tools"])},
        "tool_hash": Catalog.from_tools(fixture["tools"]).hash(),
        "fixture_hash": hashlib.sha256(json.dumps(_stable(fixture), sort_keys=True).encode()).hexdigest()[:16],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder


def _stable(fixture: dict[str, Any]) -> dict[str, Any]:
    """Content that should hash the same when nothing on the platform changed."""
    return {k: v for k, v in fixture.items() if k not in ("captured_at", "rest")}


def latest_dir(business: str, root: Path = FIXTURE_ROOT) -> Path:
    dated = sorted(p for p in (root / business).glob("*") if (p / "fixture.json").exists())
    if not dated:
        raise FileNotFoundError(f"No fixture for {business}. Run: python -m harness capture {business}")
    return dated[-1]


def load(business: str, fixture_dir: Path | None = None) -> dict[str, Any]:
    folder = fixture_dir or latest_dir(business)
    data = json.loads((folder / "fixture.json").read_text(encoding="utf-8"))
    data["_dir"] = str(folder)
    data["_manifest"] = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return data
