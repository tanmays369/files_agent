"""Revision parsing from filenames (T2.4 / A5).

The platform has no typed revision field, so revisions are read from names like
`J-BRKT-04_RevC_JigBracket.pdf` or `KPL-PMP-BASE-Rev2.pdf`. Letter revisions order
A < B < ... < Z < AA; numbers order numerically (Rev10 > Rev2). Anything odd is
flagged, never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REV_RE = re.compile(r"[_\-\s]Rev\.?([A-Za-z]{1,2}|\d{1,3})(?=[_\-.\s]|$)", re.IGNORECASE)
CODE_RE = re.compile(r"^(?P<code>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*?)[_\-\s]Rev", re.IGNORECASE)
CONFUSABLE_LETTERS = set("IO")


@dataclass(frozen=True)
class Revision:
    raw: str
    scheme: str  # "letter" or "number"
    ordinal: int
    flags: tuple[str, ...] = ()


def _letters_to_ordinal(letters: str) -> int:
    value = 0
    for ch in letters.upper():
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value


def parse_revision(filename: str) -> Revision | None:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    tokens = [m.group(1) for m in REV_RE.finditer(stem)]
    if not tokens:
        return None
    token = tokens[-1].upper()
    flags = []
    if len({t.upper() for t in tokens}) > 1:
        flags.append("several revision markers in the name")
    if token.isdigit():
        return Revision(token, "number", int(token), tuple(flags))
    if set(token) & CONFUSABLE_LETTERS:
        flags.append("uses I or O, which revision schemes usually skip")
    return Revision(token, "letter", _letters_to_ordinal(token), tuple(flags))


def part_code(filename: str) -> str | None:
    m = CODE_RE.match(filename)
    return m.group("code").upper() if m else None


def code_prefix(code: str) -> str:
    return code.split("-", 1)[0].upper()


def newest(revisions: list[Revision]) -> tuple[Revision | None, list[str]]:
    """Highest revision, plus problems (mixed schemes are ambiguous, so none is chosen)."""
    if not revisions:
        return None, []
    schemes = {r.scheme for r in revisions}
    if len(schemes) > 1:
        return None, ["mixed letter and number revisions in one family"]
    return max(revisions, key=lambda r: r.ordinal), []
