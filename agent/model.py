"""Model clients.

- AnthropicModel: the real model, via the Messages API over plain HTTPS (no SDK, no framework).
- ScriptedModel:  a deterministic stand-in for offline work and harness calibration. It routes a
  question to one skill with simple rules and returns that skill's `answer_text`. It is NOT the
  graded agent; it exists so the harness can run without an API key.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ModelError(Exception):
    pass


class AnthropicModel:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 2048, temperature: float | None = 0.0, retries: int = 3) -> None:
        if not api_key:
            raise ModelError("ANTHROPIC_API_KEY is not set in .env (use --model scripted to run offline)")
        self.api_key, self.model, self.max_tokens, self.temperature, self.retries = api_key, model, max_tokens, temperature, retries

    def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": messages, "tools": tools}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:300]
                if err.code in (429, 500, 502, 503, 529) and attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise ModelError(f"Messages API HTTP {err.code}: {detail}") from err
            except urllib.error.URLError as err:
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise ModelError(f"Messages API unreachable: {err}") from err
        raise ModelError("Messages API failed after retries")


PART = r"([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)"
ROUTES: list[tuple[str, str, Any]] = [
    (r"\b(delete|remove|trash|get rid of)\b(.*)", "remove_file", lambda m, q: {"file": _clean(m.group(2))}),
    (r"what does (.+?) (say|contain)|contents? of (.+?)\??$|quote (.+)", "file_contents",
     lambda m, q: {"file": _clean(next(g for g in (m.group(1), m.group(3), m.group(4)) if g))}),
    (r"pay ?slips?|salar|payroll|net pay|contracts?\b|\be-?sign|design (?:file|review)s?|invoices?", "explain_access",
     lambda m, q: {"request": q}),
    (r"rev(?:ision)?\s+([A-Za-z0-9]{1,3})\b.*?" + PART + r".*current", "find_drawing",
     lambda m, q: {"part_code": m.group(2), "revision": m.group(1)}),
    (r"drawing.*?\bpart\s+" + PART, "find_drawing", lambda m, q: {"part_code": m.group(1)}),
    (r"^\s*file\s+(.+?)\s+(?:into|in|to)\b", "triage_folder", lambda m, q: {"folder_name": "Incoming", "file": _clean(m.group(1))}),
    (r"\btidy\b|\btriage\b|sort (?:out )?the incoming", "triage_folder", lambda m, q: {"folder_name": "Incoming"}),
    (r"how many files", "drive_overview", lambda m, q: {}),
    (r"\blist\b.*\bfiles\b", "list_files", lambda m, q: {}),
    (r"duplicate", "find_duplicates", lambda m, q: {}),
]


def _clean(text: str) -> str:
    return re.sub(r"^(the|a|an)\s+|\s*(file)?\s*[?.!]*$", "", (text or "").strip(), flags=re.IGNORECASE).strip()


def route(question: str) -> tuple[str, dict[str, Any]] | None:
    for pattern, skill, make_args in ROUTES:
        m = re.search(pattern, question, re.IGNORECASE)
        if m:
            return skill, make_args(m, question)
    return None


class ScriptedModel:
    """Deterministic offline stand-in: one skill call, then that skill's answer_text."""

    name = "scripted"

    def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], str):
            picked = route(last["content"])
            if picked is None:
                return _text("I can't map that request to anything this Files seat can do.")
            skill, args = picked
            return {"content": [{"type": "tool_use", "id": "toolu_scripted_1", "name": skill, "input": args}],
                    "stop_reason": "tool_use", "usage": {"input_tokens": 0, "output_tokens": 0}}
        texts = []
        for block in last["content"]:
            if block.get("type") == "tool_result":
                try:
                    texts.append(json.loads(block["content"]).get("answer_text", block["content"]))
                except (ValueError, AttributeError):
                    texts.append(str(block["content"]))
        return _text("\n".join(texts) or "No result.")


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0}}
