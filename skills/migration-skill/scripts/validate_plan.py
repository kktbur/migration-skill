"""Validate the bounded migration plan used by v1.2 milestone gates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from common import ConfigError, EXIT_INVALID, EXIT_OK, checks_from_spec, load_json, write_json
except ImportError:  # pragma: no cover
    from .common import ConfigError, EXIT_INVALID, EXIT_OK, checks_from_spec, load_json, write_json


PLAN_SCHEMA_VERSION = 1
_MILESTONE_FIELDS = {
    "id",
    "name",
    "depends_on",
    "required_cases",
    "required_checks",
    "scope",
    "files",
    "expected_behavior",
    "acceptance",
    "verification_command",
    "rollback_boundary",
}


def _string_list(value: Any, label: str, errors: list[str], *, allow_empty: bool = True) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item or "\x00" in item for item in value):
        errors.append(f"{label} 必须是字符串数组")
        return []
    if not allow_empty and not value:
        errors.append(f"{label} 不能为空")
    return list(value)


def _unique(values: list[str], label: str, errors: list[str]) -> None:
    if len(values) != len(set(values)):
        errors.append(f"{label} 包含重复项")


def validate_plan(
    plan: Any,
    contract: dict[str, Any] | None = None,
    corpus: dict[str, Any] | None = None,
) -> list[str]:
    """Return all migration-plan errors without executing project code."""

    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["migration-plan.json 顶层必须是对象"]
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        errors.append(f"migration-plan.json.schema_version 必须为 {PLAN_SCHEMA_VERSION}")
    milestones = plan.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        errors.append("migration-plan.json.milestones 必须是非空数组")
        return errors

    milestone_ids: list[str] = []
    dependencies: dict[str, list[str]] = {}
    cases_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(corpus, dict) and isinstance(corpus.get("cases"), list):
        cases_by_id = {
            item.get("id"): item
            for item in corpus["cases"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    target_check_ids: set[str] = set()
    if isinstance(contract, dict):
        try:
            target_check_ids = {
                item["id"]
                for item in checks_from_spec(contract, "target")
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        except ConfigError as exc:
            errors.append(f"无法读取 target checks: {exc}")

    for index, milestone in enumerate(milestones):
        label = f"milestones[{index}]"
        if not isinstance(milestone, dict):
            errors.append(f"{label} 必须是对象")
            continue
        unknown = set(milestone) - _MILESTONE_FIELDS
        if unknown:
            errors.append(f"{label} 包含未知字段: {sorted(unknown)}")
        milestone_id = milestone.get("id")
        if not isinstance(milestone_id, str) or not milestone_id or "\x00" in milestone_id:
            errors.append(f"{label}.id 必须是非空字符串")
            continue
        if milestone_id in milestone_ids:
            errors.append(f"milestones 包含重复 id: {milestone_id}")
        milestone_ids.append(milestone_id)
        if "name" in milestone and (
            not isinstance(milestone.get("name"), str) or not milestone.get("name")
        ):
            errors.append(f"{label}.name 必须是非空字符串")
        depends_on = _string_list(milestone.get("depends_on"), f"{label}.depends_on", errors)
        required_cases = _string_list(milestone.get("required_cases"), f"{label}.required_cases", errors)
        required_checks = _string_list(milestone.get("required_checks"), f"{label}.required_checks", errors)
        _unique(depends_on, f"{label}.depends_on", errors)
        _unique(required_cases, f"{label}.required_cases", errors)
        _unique(required_checks, f"{label}.required_checks", errors)
        dependencies[milestone_id] = depends_on
        for field in ("scope", "files", "acceptance"):
            if field in milestone:
                _string_list(milestone.get(field), f"{label}.{field}", errors)
        if "expected_behavior" in milestone and not isinstance(
            milestone.get("expected_behavior"), (str, list, dict)
        ):
            errors.append(f"{label}.expected_behavior 类型无效")
        if "verification_command" in milestone and not isinstance(
            milestone.get("verification_command"), (str, list)
        ):
            errors.append(f"{label}.verification_command 类型无效")
        if "rollback_boundary" in milestone and not isinstance(
            milestone.get("rollback_boundary"), (str, list)
        ):
            errors.append(f"{label}.rollback_boundary 类型无效")
        if cases_by_id:
            for case_id in required_cases:
                case = cases_by_id.get(case_id)
                if case is None:
                    errors.append(f"{label}.required_cases 未引用 Corpus case: {case_id}")
                elif case.get("required", True) is not True:
                    errors.append(f"{label}.required_cases 只能引用 required case: {case_id}")
        if target_check_ids:
            for check_id in required_checks:
                if check_id not in target_check_ids:
                    errors.append(f"{label}.required_checks 未引用 target check: {check_id}")

    known_ids = set(milestone_ids)
    for milestone_id, depends_on in dependencies.items():
        for dependency in depends_on:
            if dependency not in known_ids:
                errors.append(f"milestone {milestone_id} 的依赖不存在: {dependency}")
            if dependency == milestone_id:
                errors.append(f"milestone {milestone_id} 不能依赖自身")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        if milestone_id in visited:
            return
        if milestone_id in visiting:
            errors.append("migration-plan 依赖图包含循环")
            return
        visiting.add(milestone_id)
        for dependency in dependencies.get(milestone_id, []):
            if dependency in dependencies:
                visit(dependency)
        visiting.remove(milestone_id)
        visited.add(milestone_id)

    for milestone_id in milestone_ids:
        visit(milestone_id)
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a bounded Migration Skill plan")
    parser.add_argument("--plan", required=True, help="migration-plan.json")
    parser.add_argument("--contract", help="optional migration.json for check references")
    parser.add_argument("--corpus", help="optional parity-corpus.json for case references")
    parser.add_argument("--output", help="optional JSON validation report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = load_json(args.plan)
    contract = load_json(args.contract) if args.contract else None
    corpus = load_json(args.corpus) if args.corpus else None
    errors = validate_plan(plan, contract, corpus)
    report = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "valid" if not errors else "invalid",
        "plan": str(Path(args.plan).resolve()),
        "errors": errors,
    }
    if args.output:
        write_json(args.output, report)
    else:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_OK if not errors else EXIT_INVALID


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
