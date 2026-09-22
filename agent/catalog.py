"""Tool discovery at start-up (T1.3). The catalogue changes often, so never hard-code it."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from agent.config import REQUIRED_TOOLS


@dataclass(frozen=True)
class Catalog:
    tools: dict[str, dict[str, Any]]

    @classmethod
    def from_tools(cls, tools: list[dict[str, Any]]) -> "Catalog":
        return cls({t["name"]: t for t in tools})

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self.tools)

    def required_args(self, name: str) -> list[str]:
        return list((self.tools.get(name, {}).get("inputSchema") or {}).get("required") or [])

    def is_read_only(self, name: str) -> bool:
        return bool((self.tools.get(name, {}).get("annotations") or {}).get("readOnlyHint"))

    def can_list(self, entity: str) -> bool:
        """An entity is inside this seat's boundary only if its .list tool exists."""
        return f"{entity}.list" in self.tools

    def hash(self) -> str:
        """Stable fingerprint of names + input schemas, used in run manifests and pre-flight."""
        canon = sorted((n, json.dumps(t.get("inputSchema") or {}, sort_keys=True)) for n, t in self.tools.items())
        return hashlib.sha256(json.dumps(canon).encode("utf-8")).hexdigest()[:16]

    def check_required(self) -> list[str]:
        """Problems with the tools the agent depends on (empty list = all good)."""
        problems = []
        for name, args in REQUIRED_TOOLS.items():
            if name not in self.tools:
                problems.append(f"missing tool {name}")
            elif set(self.required_args(name)) - set(args):
                problems.append(f"{name} now requires {sorted(set(self.required_args(name)) - set(args))}")
        return problems

    def report(self) -> str:
        problems = self.check_required()
        head = f"{len(self.tools)} tools; hash {self.hash()}"
        return head + ("; all required tools present" if not problems else "; PROBLEMS: " + "; ".join(problems))
