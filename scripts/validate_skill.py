#!/usr/bin/env python3
"""Validate this repository's Codex Skill without third-party YAML packages."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError("SKILL.md must begin with YAML frontmatter")
    raw = text[4:].split("\n---\n", 1)[0]
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip('"\'')
    return values


def validate(skill: Path) -> None:
    skill_file = skill / "SKILL.md"
    agent_file = skill / "agents" / "openai.yaml"
    if not skill_file.is_file() or not agent_file.is_file():
        raise ValueError("skill requires SKILL.md and agents/openai.yaml")
    text = skill_file.read_text(encoding="utf-8")
    values = _frontmatter(text)
    name = values.get("name", "")
    description = values.get("description", "")
    if name != skill.name or not re.fullmatch(r"[a-z0-9-]{1,63}", name):
        raise ValueError("skill name must match its directory and naming rules")
    if len(description) < 40:
        raise ValueError("skill description is missing or insufficiently discriminating")
    if re.search(r"(?i)\b(?:todo|fixme|placeholder)\b", text):
        raise ValueError("skill contains unfinished placeholder text")
    agent = agent_file.read_text(encoding="utf-8")
    if f"${name}" not in agent or "default_prompt:" not in agent:
        raise ValueError("openai.yaml default_prompt must mention the skill")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", type=Path)
    args = parser.parse_args()
    validate(args.skill.resolve())
    print("Skill is valid!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
