"""Discover and load skills from attempt_2/skills/."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass
class Skill:
    name: str
    path: Path
    description: str
    content: str


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    return meta


def list_skills() -> list[Skill]:
    skills: list[Skill] = []
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        content = skill_file.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        description = meta.get("description", "")
        if not description:
            first_heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            description = first_heading.group(1) if first_heading else skill_dir.name
        skills.append(
            Skill(
                name=skill_dir.name,
                path=skill_file,
                description=description,
                content=content,
            )
        )
    return skills


def skill_names_catalog() -> str:
    skills = list_skills()
    if not skills:
        return "(none available)"
    lines = [f"- {skill.name}: {_trunc_description(skill.description)}" for skill in skills]
    return "\n".join(lines)


def _trunc_description(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def get_skill_by_name(name: str | None) -> Skill | None:
    if not name or not name.strip():
        return None
    normalized = name.strip().lower()
    for skill in list_skills():
        if skill.name.lower() == normalized:
            return skill
    return None
