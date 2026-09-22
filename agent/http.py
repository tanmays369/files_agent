"""Tiny HTTP transport (standard library only) with retry and backoff.

A transport exposes `request(method, path, token=None, body=None) -> (status, data)`.
`harness.fake_server.FakeServer` implements the same interface, so the agent
cannot tell whether it is talking to the live platform or to the offline replay.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

RETRY_STATUSES = {429, 500, 502, 503, 504}


class TransportError(Exception):
    """The platform could not be reached after retries."""


class HttpTransport:
    def __init__(self, base_url: str, timeout: float = 60.0, retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def request(self, method: str, path: str, token: str | None = None, body: Any = None,
                idempotent: bool = True) -> tuple[int, Any]:
        """Send one request. A non-idempotent request (a write) is retried only on 429, which means
        "not processed". After a 5xx or a timeout the write may already have happened, so resending it
        could create a second escalation or session that this seat can never remove."""
        headers = {"Accept": "application/json"}
        data = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        last_error = ""
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.status, _decode(resp.read())
            except urllib.error.HTTPError as err:
                retryable = err.code in RETRY_STATUSES if idempotent else err.code == 429
                if not retryable or attempt == self.retries:
                    return err.code, _decode(err.read())
                last_error = f"HTTP {err.code}"
            except OSError as err:  # URLError, timeouts, connection reset/aborted (HTTPError is handled above)
                last_error = f"{type(err).__name__}: {err}"
                if not idempotent or attempt == self.retries:
                    raise TransportError(f"{method} {path} failed: {last_error}") from err
            time.sleep(2 ** attempt)
        raise TransportError(f"{method} {path} failed: {last_error}")


def _decode(raw: bytes) -> Any:
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return text
