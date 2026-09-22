"""Skill registry. Skills are deterministic, tested code; only they may write."""
from __future__ import annotations

from agent.skills import access, duplicates, find_drawing, overview, triage
from agent.skills.common import Skill, SkillContext

SKILLS: dict[str, Skill] = {s.name: s for s in [
    find_drawing.SKILL, triage.SKILL, duplicates.SKILL, overview.SKILL, *access.SKILLS,
]}

__all__ = ["SKILLS", "Skill", "SkillContext"]
