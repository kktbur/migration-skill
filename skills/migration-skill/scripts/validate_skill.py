"""Validate the repository-local Migration Skill package with the stdlib."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


EXPECTED_REFERENCES = {
    "behavior-contract.md",
    "migration-workflow.md",
    "safety.md",
    "upstream-lineage.md",
    "verification.md",
}
EXPECTED_SCRIPTS = {
    "advance_milestone.py",
    "capture_baseline.py",
    "common.py",
    "evaluate_milestone.py",
    "compare_results.py",
    "evaluate_migration.py",
    "freeze_contract.py",
    "inventory_project.py",
    "run_checks.py",
    "run_parity.py",
    "validate_contract.py",
    "validate_judge.py",
    "validate_plan.py",
    "verify_resume.py",
}


def _frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 缺少有效 YAML frontmatter")
    return match.group(1), text[match.end() :]


def _scalar(frontmatter: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", frontmatter)
    if not match:
        raise ValueError(f"frontmatter 缺少 {key}")
    value = match.group(1).strip().strip('"').strip("'")
    if not value:
        raise ValueError(f"frontmatter.{key} 不能为空")
    return value


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return ["缺少 SKILL.md"]
    try:
        frontmatter, body = _frontmatter(skill_path.read_text(encoding="utf-8"))
        name = _scalar(frontmatter, "name")
        description = _scalar(frontmatter, "description")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append("frontmatter.name 必须是小写 kebab-case")
        if len(description) > 1024 or "<" in description or ">" in description:
            errors.append("frontmatter.description 超出长度或包含 angle brackets")
        if "[TODO:" in body or "[TODO:" in frontmatter:
            errors.append("Skill 包含未完成的 TODO 占位符")
        for match in re.finditer(r"\]\(([^)]+)\)", body):
            link = match.group(1).strip()
            if link.startswith(("http://", "https://", "#")):
                continue
            link_path = (skill_path.parent / link).resolve()
            if not link_path.is_file():
                errors.append(f"SKILL.md 链接目标不存在: {link}")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    agents = root / "agents" / "openai.yaml"
    if not agents.is_file():
        errors.append("缺少 agents/openai.yaml")
    else:
        try:
            agent_text = agents.read_text(encoding="utf-8")
            for key in ("display_name", "short_description", "default_prompt"):
                if not re.search(rf"(?m)^\s*{re.escape(key)}:\s*.+", agent_text):
                    errors.append(f"agents/openai.yaml 缺少 interface.{key}")
        except OSError as exc:
            errors.append(str(exc))

    reference_dir = root / "references"
    actual_references = {path.name for path in reference_dir.glob("*.md")} if reference_dir.is_dir() else set()
    for missing in sorted(EXPECTED_REFERENCES - actual_references):
        errors.append(f"缺少 reference: {missing}")

    script_dir = root / "scripts"
    actual_scripts = {path.name for path in script_dir.glob("*.py")} if script_dir.is_dir() else set()
    for missing in sorted(EXPECTED_SCRIPTS - actual_scripts):
        errors.append(f"缺少 deterministic script: {missing}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Migration Skill package")
    parser.add_argument("--root", required=True, help="Migration Skill package root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate(Path(args.root))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    print("Migration Skill package is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
