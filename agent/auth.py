"""Login, token handling and identity (T1.1)."""
from __future__ import annotations

from typing import Any

from agent.trace import Trace


class AuthError(Exception):
    """Login failed. The message never contains the password."""


class Session:
    """Holds the bearer token; logs in again once if the platform answers 401."""

    def __init__(self, transport: Any, email: str, password: str, trace: Trace) -> None:
        if not password:
            raise AuthError("No password configured: set AS_KEYSTONE_PASSWORD / AS_SURYODAYA_PASSWORD in .env")
        self.transport = transport
        self.email = email
        self._password = password
        self.trace = trace
        self._token: str | None = None
        self._me: dict[str, Any] | None = None

    def login(self) -> None:
        status, data = self.transport.request("POST", "/api/auth/login", body={"email": self.email, "password": self._password})
        if status != 200 or not isinstance(data, dict) or "token" not in data:
            self.trace.write("login", ok=False, status=status)
            raise AuthError(f"Login failed for {self.email} (HTTP {status}). Check the password in .env.")
        self._token = data["token"]
        self.trace.redact.add(self._token)
        self.trace.write("login", ok=True, status=status)

    @property
    def token(self) -> str:
        if self._token is None:
            self.login()
        assert self._token is not None
        return self._token

    def request(self, method: str, path: str, body: Any = None, idempotent: bool = True) -> tuple[int, Any]:
        status, data = self.transport.request(method, path, self.token, body, idempotent=idempotent)
        if status == 401:  # not processed, so resending is safe even for a write
            self.trace.write("relogin", path=path)
            self.login()
            status, data = self.transport.request(method, path, self.token, body, idempotent=idempotent)
        return status, data

    def me(self) -> dict[str, Any]:
        if self._me is None:
            status, data = self.request("GET", "/api/auth/me")
            if status != 200 or not isinstance(data, dict):
                raise AuthError(f"GET /api/auth/me failed (HTTP {status})")
            self._me = data
        return self._me

    def invalidate_token(self) -> None:
        """Test hook: forget the token so the next call must log in again."""
        self._token = "invalid-token"
