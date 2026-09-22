"""Remove secrets from anything before it is written to disk."""
from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"
SENSITIVE_KEYS = {"password", "token", "authorization", "x-api-key", "api_key", "apikey", "access_token"}
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")


class Redactor:
    """Masks known secret values anywhere, plus any value stored under a sensitive key."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        self._secrets = sorted({s for s in (secrets or []) if s and len(s) >= 6}, key=len, reverse=True)

    def add(self, secret: str) -> None:
        if secret and len(secret) >= 6 and secret not in self._secrets:
            self._secrets = sorted([*self._secrets, secret], key=len, reverse=True)

    def text(self, value: str) -> str:
        out = BEARER_RE.sub(f"Bearer {MASK}", value)
        for secret in self._secrets:
            out = out.replace(secret, MASK)
        return out

    def __call__(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {k: (MASK if str(k).lower() in SENSITIVE_KEYS and v else self(v)) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self(v) for v in obj]
        return obj
