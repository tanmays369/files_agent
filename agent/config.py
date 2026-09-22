"""Configuration: .env loading, instance URLs, verified ids and limits.

No secret is hard-coded here. Passwords and API keys come from `.env` (see
`.env.example`) or the process environment, which always wins.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
RUNS_DIR = REPO_ROOT / "runs"

INSTANCES = {
    "keystone": "https://class.agentswitch.theschoolofai.in",
    "suryodaya": "https://agentswitch.theschoolofai.in",
}
WRITE_BUSINESS = "keystone"  # live writes are only ever allowed here

# Keystone ids, verified live on 22 Sept 2026.
KEYSTONE_INCOMING_FOLDER = "6f8a3ed1-f2df-46a7-8dcb-275e9494c799"
KEYSTONE_SEAT_ID = "a9e75bbc-cf2c-4d03-bb96-9cc6d57d9754"

# The 9 Incoming rows. Live writes can never touch any other file id.
KEYSTONE_INCOMING_ALLOWLIST = frozenset({
    "680e8af6-15f3-49c6-b70b-987316fa5775",  # Cert_MillCert_SS304_Heat90114.pdf
    "8018a70b-47d5-472b-88b6-b1ced1ced8b0",  # IMG_20260814_093214.jpg
    "b45cecdd-9f14-491a-a0ee-2826d3fabb15",  # J-KNOB-09_RevA.dxf
    "82f83d94-5a46-4df3-9ee1-61e8b3c79d6e",  # PO_4471_ApexMetals_signed (1).pdf
    "732439a0-7f36-4d31-ac3b-f406c41c00bd",  # PO_4471_ApexMetals_signed.pdf
    "60f685c9-bcb5-43a3-a403-18b7e9d76368",  # Untitled.pdf
    "81857de6-e6e9-41c5-9da8-67cb5d1903c1",  # W9_JMillerWelding_2026.pdf
    "b1d3894c-12e9-4ee1-b1da-82c7191ed4a0",  # scan0042.pdf
    "1ee27946-7064-42e1-afce-376068a545bf",  # timesheet_week33.xlsx
})

# The only write tools the agent may call.
WRITE_TOOLS = frozenset({"FileAttachment.update", "AgentSession.create", "AgentEscalation.create"})

# MCP tools the agent needs; checked at start-up (value = required args).
REQUIRED_TOOLS = {
    "FileAttachment.list": [],
    "FileAttachment.get": ["id"],
    "FileAttachment.update": ["id"],
    "DriveFolder.list": [],
    "Item.list": [],
    "Party.list": [],
    "DriveAccessLog.list": [],
    "AgentSession.create": [],
    "AgentEscalation.create": ["session_id", "reason"],
    "AgentEscalation.list": [],
}

# Read-only MCP tools the model may call directly (keeps the prompt small).
EXPOSED_READ_TOOLS = (
    "FileAttachment.list", "FileAttachment.get", "DriveFolder.list", "Item.list",
    "Party.list", "DriveAccessLog.list", "AgentEscalation.list", "tools.search",
)


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse KEY=VALUE lines. The process environment overrides the file."""
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **{k: v for k, v in os.environ.items() if k.startswith(("AS_", "ANTHROPIC_"))}}


@dataclass(frozen=True)
class Settings:
    business: str
    base_url: str
    email: str
    password: str
    anthropic_api_key: str
    model: str
    max_turns: int
    max_mcp_calls: int
    max_usd: float
    price_in_per_mtok: float
    price_out_per_mtok: float
    allow_writes: bool
    actor_kind: str

    def secrets(self) -> list[str]:
        return [s for s in (self.password, self.anthropic_api_key) if s]


def get_settings(business: str = "keystone", env: dict[str, str] | None = None) -> Settings:
    if business not in INSTANCES:
        raise ValueError(f"Unknown business {business!r}; use one of {sorted(INSTANCES)}")
    explicit_env = env
    env = load_env() if env is None else env
    actor_kind = env.get("AS_ACTOR_KIND", "").strip()
    if actor_kind and actor_kind not in ("user", "system"):
        raise ValueError("AS_ACTOR_KIND must be 'user', 'system' or blank ('agent' is not allowed by the platform)")
    return Settings(
        business=business,
        base_url=INSTANCES[business],
        email=env.get("AS_EMAIL", "team20@theschoolofai.in"),
        password=env.get(f"AS_{business.upper()}_PASSWORD", ""),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
        model=env.get("AS_MODEL", "claude-sonnet-5"),
        max_turns=int(env.get("AS_MAX_TURNS", "12")),
        max_mcp_calls=int(env.get("AS_MAX_MCP_CALLS", "80")),  # a 9-file tidy uses ~28; ~3 per file moved
        max_usd=float(env.get("AS_MAX_USD", "0.50")),
        price_in_per_mtok=float(env.get("AS_PRICE_IN_PER_MTOK", "3.0")),
        price_out_per_mtok=float(env.get("AS_PRICE_OUT_PER_MTOK", "15.0")),
        # The second write switch is read from the live shell only, never from .env, so it can't stay on by accident.
        allow_writes=(os.environ if explicit_env is None else explicit_env).get("AS_ALLOW_WRITES", "0") == "1",
        actor_kind=actor_kind,
    )
