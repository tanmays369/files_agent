"""Hand-written MCP client: JSON-RPC 2.0 over POST /api/mcp (T1.2).

Rules this client enforces:
- An `error` inside the JSON-RPC envelope is a failure even though HTTP is 200.
- `result.isError == true` is also a failure.
- 401 is handled by the Session (one re-login).
- A write tool is never resent after a 5xx or a timeout (it may already have happened).
- A transport failure becomes an McpError (data_code "transport_error").
- No streaming, no batching.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from agent.auth import Session
from agent.config import WRITE_TOOLS
from agent.http import TransportError
from agent.trace import Trace

PROTOCOL_VERSION = "2025-11-25"


class McpError(Exception):
    def __init__(self, message: str, code: int | None = None, data_code: str | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data_code = data_code
        self.data = data


class McpClient:
    def __init__(self, session: Session, trace: Trace, budget: Any = None) -> None:
        self.session = session
        self.trace = trace
        self.budget = budget
        self.sanitise: Callable[[Any], Any] | None = None  # leak guard for traced results; set by agent.runtime
        self._next_id = 0
        self._tools: list[dict[str, Any]] | None = None

    def _rpc(self, method: str, params: dict[str, Any], idempotent: bool = True) -> Any:
        self._next_id += 1
        envelope = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        try:
            status, data = self.session.request("POST", "/api/mcp", envelope, idempotent=idempotent)
        except TransportError as err:
            raise McpError(f"platform unreachable: {err}", data_code="transport_error") from err
        if status != 200:
            raise McpError(f"HTTP {status} from /api/mcp", code=status)
        if not isinstance(data, dict):
            raise McpError(f"Non-JSON reply from /api/mcp: {str(data)[:120]}")
        if "error" in data:
            # JSON-RPC allows `error` and `error.data` to be any value, so never assume dicts here.
            err = data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
            extra = err.get("data") if isinstance(err.get("data"), dict) else {"detail": err.get("data")}
            raise McpError(str(err.get("message", "MCP error")), err.get("code"), extra.get("code"), extra)
        return data.get("result")

    def initialize(self) -> dict[str, Any]:
        return self._rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                        "clientInfo": {"name": "team20-files-agent", "version": "0.1"}})

    def list_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        if self._tools is None or refresh:
            result = self._rpc("tools/list", {})
            self._tools = list((result or {}).get("tools", []))
        return self._tools

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        if self.budget is not None:
            self.budget.add_call()
        try:  # a write tool is never resent after an ambiguous failure (see agent/http.py)
            result = self._rpc("tools/call", {"name": name, "arguments": args}, idempotent=name not in WRITE_TOOLS)
        except McpError as err:
            self.trace.write("mcp_call", tool=name, args=args, ok=False, error=str(err), error_code=err.data_code)
            raise
        payload = _payload(result)
        if (result or {}).get("isError"):
            self.trace.write("mcp_call", tool=name, args=args, ok=False, error=str(payload)[:500])
            raise McpError(f"{name} returned isError: {str(payload)[:200]}", data_code="is_error", data=payload)
        traced = self.sanitise(payload) if self.sanitise else payload
        self.trace.write("mcp_call", tool=name, args=args, ok=True, result=_summarise(traced))
        return payload


def _payload(result: Any) -> Any:
    """The full payload is JSON text in content[0].text; fall back to structuredContent."""
    if not isinstance(result, dict):
        return result
    for block in result.get("content") or []:
        if block.get("type") == "text":
            try:
                return json.loads(block.get("text", ""))
            except ValueError:
                return block.get("text")
    return result.get("structuredContent")


def _summarise(payload: Any) -> Any:
    """Keep traces readable: record list totals and ids, and full single objects."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return {"total": payload.get("total"), "ids": [r.get("id") for r in payload["data"][:50]]}
    return payload
