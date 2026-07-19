#!/usr/bin/env python3
"""Validate the repository's bundled Skill metadata for CI."""

import argparse
import re
import sys
from pathlib import Path

import yaml


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillValidationError(RuntimeError):
    pass


def read_yaml_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SkillValidationError("SKILL.md 缺少 YAML frontmatter")
    raw = text[4:].split("\n---\n", 1)[0]
    value = yaml.safe_load(raw)
    if not isinstance(value, dict):
        raise SkillValidationError("SKILL.md frontmatter 必须是对象")
    return value


def validate_skill(folder):
    folder = Path(folder).resolve()
    skill_path = folder / "SKILL.md"
    if not skill_path.is_file():
        raise SkillValidationError("缺少 SKILL.md")
    metadata = read_yaml_frontmatter(skill_path)
    if set(metadata) != {"name", "description"}:
        raise SkillValidationError("frontmatter 只允许 name 和 description")
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise SkillValidationError("name 必须使用小写 kebab-case")
    if folder.name != name:
        raise SkillValidationError("Skill 目录名必须与 name 一致")
    if not isinstance(description, str) or not description.strip():
        raise SkillValidationError("description 不能为空")

    openai_path = folder / "agents" / "openai.yaml"
    if not openai_path.is_file():
        raise SkillValidationError("缺少 agents/openai.yaml")
    value = yaml.safe_load(openai_path.read_text(encoding="utf-8"))
    interface = value.get("interface", {}) if isinstance(value, dict) else {}
    short = interface.get("short_description", "")
    prompt = interface.get("default_prompt", "")
    if not isinstance(short, str) or not 8 <= len(short) <= 64:
        raise SkillValidationError("short_description 长度必须为 8—64 字符")
    if not isinstance(prompt, str) or f"${name}" not in prompt:
        raise SkillValidationError("default_prompt 必须显式包含 Skill 名称")
    return name


def main():
    parser = argparse.ArgumentParser(description="校验仓库内 Skill 元数据")
    parser.add_argument("folders", nargs="+")
    args = parser.parse_args()
    try:
        for folder in args.folders:
            print(f"✓ {validate_skill(folder)}")
    except (OSError, yaml.YAMLError, SkillValidationError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
