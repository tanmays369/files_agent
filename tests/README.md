# tests/ — hand-written by Team 20 (Phase 5)

> **This folder is intentionally empty of test code.** The brief says *"a test written by
> Claude or Codex scores zero"*, and each hand-written test is worth 10 points. Write every test
> here yourselves and commit them yourselves; your commit history is the evidence.

## What to write (plan tasks T5.1–T5.10)

| Id | Test target | Module under test |
|---|---|---|
| T5.1 | Revision parser: letters, numbers, `AA > Z`, `Rev10 > Rev2`, ambiguous names | `agent/skills/revisions.py` |
| T5.2 | Evidence scoring: each file → tier; a description alone never files; a disagreeing description → conflict | `agent/skills/triage.py`, `filing_rules.toml` |
| T5.3 | Duplicates: hash match; a hash shared by unrelated files is rejected; name + size fallback; never "byte-verified" | `agent/skills/duplicates.py` |
| T5.4 | Guards: write outside the allow-list blocked; plan-only writes nothing; read-only field refused; stale row skipped; a failed confirm read still records the write; restore leaves another team's change alone | `agent/guards.py`, `agent/snapshot.py` |
| T5.5 | MCP client: an error inside an HTTP-200 reply raises; `isError` raises; `401` → one re-login | `agent/mcp_client.py`, `agent/auth.py` |
| T5.6 | Safe reads: the `ne:`, comma and sort-order traps avoided | `agent/safe_reads.py` |
| T5.7 | Verifiers: each check fails on a deliberately broken run | `harness/verifiers.py` |
| T5.8 | Idempotency: a second tidy makes no writes and no new escalations | `agent/skills/triage.py`, `escalate.py` |
| T5.9 | Redaction: a trace of login + a call contains no secret | `agent/redact.py`, `agent/trace.py` |
| T5.10 | Budget: an endless loop stops at the cap; a write is never started without budget for its confirm | `agent/budget.py`, `agent/guards.py` |

## Useful building blocks (already in the code, not tests)

- **Offline server:** `harness.fake_server.FakeServer.from_fixture("keystone", None, faults=(...))`
  gives you a full fake platform with the real captured data, so tests need no network.
- **A runtime on the fake server:** `agent.runtime.build("keystone", "fake", "plan", None)`
  (or `"apply"`) returns everything wired together: `rt.ctx`, `rt.guard`, `rt.mcp`, `rt.budget`.
- **Faults:** see the docstring of `harness/fake_server.py` (`moved_row`, `http401_once`,
  `error_in_200`, `planted_description`, `swap_archived`, …). One-shot faults fire only while
  `server.armed` is True. A server you build yourself starts armed, but
  `agent.runtime.build(..., transport=server)` makes its own calls (login, `initialize`, the
  allow-list read) that would use them up. So set `server.armed = False` before `build(...)` and
  `server.armed = True` after it, as the runner does.
- **Canary for the leak guard:** `extra_files=[{"filename": "Offer Letter - Canary.pdf",
  "entity_type": "EsignDocument", "folder": ""}]` plants a row this seat must never reveal.
- **Restore logic without a platform:** `agent.snapshot.plan_restore(snapshot, current, writes, me)`
  is pure; give it dicts and check what it would put back and what it leaves alone.

## How to know your tests are good

For each test, **break the code on purpose and check the test goes red**, then undo the change:

| Test | Sabotage |
|---|---|
| T5.1 | sort revisions as plain text |
| T5.2 | let a description alone choose the folder |
| T5.3 | trust a hash shared by many files |
| T5.4 | allow every id |
| T5.5 | treat HTTP 200 as success without checking for an error inside |
| T5.6 | send `ne:` to the server |
| T5.7 | make a verifier always return ok |
| T5.8 | skip the "already escalated?" check |
| T5.9 | turn redaction off |
| T5.10 | remove the cap |

Keep tests **offline, fast and deterministic**: no live platform, no model calls.

Whether `pytest` is allowed is open (staff question Q3). The standard library's `unittest` needs
nothing installed: `python -m unittest discover -s tests`.
