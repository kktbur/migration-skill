"""Validate a Judge using an actual positive run and targeted mutations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        canonical_path,
        git_revision,
        load_json,
        sha256_file,
        tree_digest,
        write_json,
    )
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        canonical_path,
        git_revision,
        load_json,
        sha256_file,
        tree_digest,
        write_json,
    )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ConfigError(f"{label} 必须是非空字符串")
    return value


def _cases(document: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ConfigError(f"{label} 必须包含 cases 数组")
    result: dict[str, dict[str, Any]] = {}
    for item in document["cases"]:
        if not isinstance(item, dict):
            raise ConfigError(f"{label}.cases 中每项必须是对象")
        case_id = _nonempty_string(item.get("id"), f"{label}.case.id")
        if case_id in result:
            raise ConfigError(f"{label} 包含重复 case id: {case_id}")
        result[case_id] = item
    return result


def _positive_control(document: Any) -> bool:
    if not isinstance(document, dict):
        return False
    if document.get("status") != "passed" or document.get("passed") is not True:
        return False
    summary = document.get("summary", {})
    if isinstance(summary, dict) and summary.get("required_failed"):
        return False
    return True


def _resolve_result(plan_path: Path, value: Any, label: str) -> Path:
    relative = _nonempty_string(value, label)
    candidate = canonical_path(relative if Path(relative).is_absolute() else plan_path.parent / relative)
    if not candidate.exists() or not candidate.is_file():
        raise ConfigError(f"{label} 不存在或不是文件: {candidate}")
    return candidate


def validate_artifact(document: Any) -> list[str]:
    """Return structural errors for a generated judge-validation artifact."""

    errors: list[str] = []
    if not isinstance(document, dict):
        return ["judge-validation 必须是对象"]
    if document.get("artifact_type") != "judge-validation-v1":
        errors.append("judge-validation.artifact_type 不受支持")
    if document.get("generated_by") != "validate_judge.py":
        errors.append("judge-validation.generated_by 不正确")
    if document.get("positive_control") is not True:
        errors.append("positive_control 未通过")
    controls = document.get("negative_controls")
    if not isinstance(controls, list) or not controls:
        errors.append("negative_controls 必须是非空数组")
    else:
        for index, control in enumerate(controls):
            if not isinstance(control, dict):
                errors.append(f"negative_controls[{index}] 必须是对象")
                continue
            for key in ("mutation_id", "expected_case", "result_sha256"):
                if not isinstance(control.get(key), str) or not control.get(key):
                    errors.append(f"negative_controls[{index}].{key} 无效")
            if control.get("detected") is not True:
                errors.append(f"negative_controls[{index}] 未检测到目标 mutation")
    if document.get("negative_control") is not True:
        errors.append("negative_control 未通过")
    if document.get("valid") is not True:
        errors.append("judge-validation.valid 不是 true")
    return errors


def validate_judge(
    positive_path: Path,
    mutation_plan_path: Path,
    output_path: Path,
    *,
    source_revision: str | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    positive_path = canonical_path(positive_path)
    mutation_plan_path = canonical_path(mutation_plan_path)
    output_path = canonical_path(output_path)
    positive = load_json(positive_path)
    plan = load_json(mutation_plan_path)
    if not isinstance(plan, dict):
        raise ConfigError("mutation-plan 顶层必须是对象")
    if plan.get("schema_version") != 1:
        raise ConfigError("mutation-plan.schema_version 必须为 1")
    controls = plan.get("negative_controls")
    if not isinstance(controls, list) or not controls:
        raise ConfigError("mutation-plan.negative_controls 必须是非空数组")
    if source_root is not None:
        source_root = canonical_path(source_root)
        if not source_root.exists() or not source_root.is_dir():
            raise ConfigError(f"source root 不存在: {source_root}")
        detected_revision = git_revision(source_root)
        detected_tree_digest = tree_digest(source_root)
    else:
        detected_revision = None
        detected_tree_digest = None
    if source_revision is None:
        source_revision = detected_revision
    elif detected_revision is not None and source_revision != detected_revision:
        raise ConfigError("指定的 source revision 与当前 Source 不一致")
    positive_ok = _positive_control(positive)
    negative_results: list[dict[str, Any]] = []
    mutation_ids: set[str] = set()
    for index, control in enumerate(controls):
        label = f"mutation-plan.negative_controls[{index}]"
        if not isinstance(control, dict):
            raise ConfigError(f"{label} 必须是对象")
        mutation_id = _nonempty_string(control.get("mutation_id", control.get("id")), f"{label}.mutation_id")
        if mutation_id in mutation_ids:
            raise ConfigError(f"mutation-plan 包含重复 mutation_id: {mutation_id}")
        mutation_ids.add(mutation_id)
        expected_case = _nonempty_string(control.get("expected_case"), f"{label}.expected_case")
        expected_operation = control.get("expected_operation")
        if expected_operation is not None:
            expected_operation = _nonempty_string(expected_operation, f"{label}.expected_operation")
        result_path = _resolve_result(mutation_plan_path, control.get("result"), f"{label}.result")
        document = load_json(result_path)
        cases = _cases(document, str(result_path))
        case = cases.get(expected_case)
        detected = True
        reason: str | None = None
        if not isinstance(document, dict) or document.get("negative_control") is not True:
            detected = False
            reason = "result-not-marked-negative-control"
        elif document.get("negative_control_scoped") is not True:
            detected = False
            reason = "negative-control-is-not-scoped"
        elif not isinstance(case, dict):
            detected = False
            reason = "expected-case-missing"
        elif case.get("required") is not True:
            detected = False
            reason = "expected-case-is-not-required"
        elif case.get("passed") is not False:
            detected = False
            reason = "expected-case-did-not-fail"
        elif expected_operation is not None and case.get("operation_id") != expected_operation:
            detected = False
            reason = "expected-operation-mismatch"
        negative_results.append(
            {
                "mutation_id": mutation_id,
                "expected_case": expected_case,
                "expected_operation": expected_operation,
                "result_path": str(result_path),
                "result_sha256": sha256_file(result_path),
                "detected": detected,
                "reason": reason,
            }
        )
    valid = positive_ok and bool(negative_results) and all(item["detected"] for item in negative_results)
    artifact = {
        "schema_version": 1,
        "artifact_type": "judge-validation-v1",
        "generated_by": "validate_judge.py",
        "source_revision": source_revision,
        "source_tree_digest": detected_tree_digest,
        "positive_control": positive_ok,
        "positive_result_path": str(positive_path),
        "positive_result_sha256": sha256_file(positive_path),
        "mutation_plan_path": str(mutation_plan_path),
        "mutation_plan_sha256": sha256_file(mutation_plan_path),
        "negative_controls": negative_results,
        "negative_control": bool(negative_results) and all(item["detected"] for item in negative_results),
        "valid": valid,
    }
    write_json(output_path, artifact)
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Migration Skill Judge with targeted mutations")
    parser.add_argument("--positive", required=True, help="positive source-vs-source compare result")
    parser.add_argument("--mutation-plan", required=True, help="mutation-plan.json")
    parser.add_argument("--root", help="optional source root used to derive revision and tree digest")
    parser.add_argument("--source-revision", help="expected source revision")
    parser.add_argument("--output", required=True, help="judge-validation.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact = validate_judge(
        Path(args.positive),
        Path(args.mutation_plan),
        Path(args.output),
        source_revision=args.source_revision,
        source_root=Path(args.root) if args.root else None,
    )
    return EXIT_OK if artifact["valid"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
