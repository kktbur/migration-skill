"""Evaluate one bounded migration milestone without requiring final completion."""

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
        FrozenStateError,
        canonical_path,
        checks_from_spec,
        git_revision,
        load_json,
        result_map,
        sha256_file,
        tree_digest,
        verify_freeze,
        write_json,
    )
    from evaluate_migration import _new_source_regressions
    from validate_contract import validate_documents
    from validate_plan import validate_plan
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        FrozenStateError,
        canonical_path,
        checks_from_spec,
        git_revision,
        load_json,
        result_map,
        sha256_file,
        tree_digest,
        verify_freeze,
        write_json,
    )
    from .evaluate_migration import _new_source_regressions
    from .validate_contract import validate_documents
    from .validate_plan import validate_plan


def _status(item: dict[str, Any]) -> str:
    value = item.get("status", "failed")
    return value if isinstance(value, str) else "failed"


def _ids(value: Any, label: str) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], [f"{label} 必须是字符串数组"]
    invalid = [str(item) for item in value if not isinstance(item, str) or not item]
    if invalid:
        return [], [f"{label} 包含无效 id"]
    return list(dict.fromkeys(value)), []


def _required_check_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in checks_from_spec(contract, "target")
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _check_gate(
    check_ids: list[str],
    target: Any,
    expected_checks: dict[str, dict[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    try:
        actual = result_map(target, "checks")
    except ConfigError as exc:
        return False, {"required": check_ids, "passed": [], "failed": check_ids, "error": str(exc)}
    missing = [check_id for check_id in check_ids if check_id not in actual]
    failed = [check_id for check_id in check_ids if check_id in actual and _status(actual[check_id]) != "passed"]
    unknown = [check_id for check_id in check_ids if check_id not in expected_checks]
    failures = sorted(set([*missing, *failed, *unknown]))
    return not failures, {
        "required": sorted(check_ids),
        "passed": sorted(check_id for check_id in check_ids if check_id in actual and _status(actual[check_id]) == "passed"),
        "missing": sorted(missing),
        "failed": sorted(failed),
        "unknown": sorted(unknown),
        "all_passed": not failures,
    }


def _case_gate(case_ids: list[str], parity: Any) -> tuple[bool, dict[str, Any]]:
    try:
        actual = result_map(parity, "cases")
    except ConfigError as exc:
        return False, {"required": case_ids, "passed": [], "failed": case_ids, "error": str(exc)}
    missing = [case_id for case_id in case_ids if case_id not in actual]
    failed = [case_id for case_id in case_ids if case_id in actual and actual[case_id].get("passed") is not True]
    passed = [case_id for case_id in case_ids if case_id in actual and actual[case_id].get("passed") is True]
    failures = sorted(set([*missing, *failed]))
    return not failures, {
        "required": sorted(case_ids),
        "passed": sorted(passed),
        "missing": sorted(missing),
        "failed": sorted(failed),
        "all_passed": not failures,
    }


def _judge_valid(freeze: Any) -> bool:
    if not isinstance(freeze, dict) or freeze.get("intact") is not True:
        return False
    if isinstance(freeze.get("judge"), dict) and freeze["judge"].get("valid") is True:
        return True
    manifest = freeze.get("manifest")
    if not isinstance(manifest, dict):
        return False
    judge = manifest.get("judge_validation")
    return isinstance(judge, dict) and judge.get("valid") is True


def _target_identity(target: Any) -> dict[str, Any]:
    root_value = target.get("root") if isinstance(target, dict) else None
    if not isinstance(root_value, str):
        return {"root": None, "revision": None, "tree_digest": None}
    root = canonical_path(root_value)
    if not root.exists() or not root.is_dir():
        return {"root": str(root), "revision": None, "tree_digest": None}
    return {"root": str(root), "revision": git_revision(root), "tree_digest": tree_digest(root)}


def _frozen_source(freeze: dict[str, Any]) -> dict[str, Any]:
    manifest = freeze.get("manifest", {})
    source = manifest.get("source", {}) if isinstance(manifest, dict) else {}
    return source if isinstance(source, dict) else {}


def _plan_milestone(plan: dict[str, Any], milestone_id: str) -> dict[str, Any] | None:
    milestones = plan.get("milestones", [])
    if not isinstance(milestones, list):
        return None
    for milestone in milestones:
        if isinstance(milestone, dict) and milestone.get("id") == milestone_id:
            return milestone
    return None


def evaluate_milestone(
    baseline: Any,
    source: Any,
    target: Any,
    parity: Any,
    contract: dict[str, Any],
    corpus: dict[str, Any],
    plan: dict[str, Any],
    state: dict[str, Any],
    freeze: dict[str, Any],
    milestone_id: str,
    *,
    plan_digest: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic acceptance candidate for exactly one milestone."""

    plan_errors = validate_plan(plan, contract, corpus)
    milestone = _plan_milestone(plan, milestone_id)
    if milestone is None:
        plan_errors = [*plan_errors, f"不存在 milestone: {milestone_id}"]
        milestone = {"id": milestone_id, "depends_on": [], "required_cases": [], "required_checks": []}

    required_cases, case_errors = _ids(milestone.get("required_cases", []), "required_cases")
    required_checks, check_errors = _ids(milestone.get("required_checks", []), "required_checks")
    protected_cases, protected_case_errors = _ids(state.get("protected_cases", []), "state.protected_cases")
    protected_checks, protected_check_errors = _ids(state.get("protected_checks", []), "state.protected_checks")
    completed, completed_errors = _ids(state.get("completed_milestones", []), "state.completed_milestones")
    plan_errors.extend([*case_errors, *check_errors, *protected_case_errors, *protected_check_errors, *completed_errors])

    required_case_gate, required_case_result = _case_gate(required_cases, parity)
    protected_case_gate, protected_case_result = _case_gate(protected_cases, parity)
    expected_checks = _required_check_map(contract)
    required_check_gate, required_check_result = _check_gate(required_checks, target, expected_checks)
    protected_check_gate, protected_check_result = _check_gate(protected_checks, target, expected_checks)

    source_regressions = _new_source_regressions(baseline, source)
    baseline_status = baseline.get("status") if isinstance(baseline, dict) else None
    baseline_reliable = baseline_status in {"captured_clean", "captured_with_inherited_failures"}
    frozen_source = _frozen_source(freeze)
    baseline_identity_matches = (
        isinstance(baseline, dict)
        and baseline.get("revision") == frozen_source.get("revision")
        and baseline.get("tree_digest") == frozen_source.get("tree_digest")
    )
    no_required_gaps = not state.get("required_gaps", [])
    dependencies = milestone.get("depends_on", []) if isinstance(milestone, dict) else []
    dependencies_met = isinstance(dependencies, list) and all(item in completed for item in dependencies)
    state_schema_valid = state.get("schema_version") == 2
    all_conditions = {
        "plan_valid": not plan_errors,
        "state_schema_valid": state_schema_valid,
        "freeze_intact": freeze.get("intact") is True,
        "judge_valid": _judge_valid(freeze),
        "baseline_reliable": baseline_reliable,
        "baseline_identity_matches": baseline_identity_matches,
        "no_new_source_regression": not source_regressions,
        "dependencies_met": dependencies_met,
        "milestone_required_cases": required_case_gate,
        "protected_cases": protected_case_gate,
        "milestone_required_checks": required_check_gate,
        "protected_checks": protected_check_gate,
        "no_required_gaps": no_required_gaps,
    }
    eligible = all(all_conditions.values())
    proof_cases = sorted(set([*protected_cases, *required_cases]))
    proof_checks = sorted(set([*protected_checks, *required_checks]))
    target_identity = _target_identity(target)
    total = len(all_conditions)
    passed = sum(1 for value in all_conditions.values() if value)
    return {
        "schema_version": 1,
        "artifact_type": "milestone-result-v1",
        "status": "eligible" if eligible else "rejected",
        "eligible": eligible,
        "ratchet_eligible": eligible,
        "milestone_id": milestone_id,
        "milestone": milestone,
        "plan_digest": plan_digest,
        "plan_errors": sorted(set(plan_errors)),
        "required_conditions": all_conditions,
        "gate_failures": sorted(
            [name for name, value in all_conditions.items() if not value]
            + [f"source-regression:{item}" for item in source_regressions]
        ),
        "required_cases": required_case_result,
        "protected_cases": protected_case_result,
        "required_checks": required_check_result,
        "protected_checks": protected_check_result,
        "proof_set": {"cases": proof_cases, "checks": proof_checks},
        "future_cases_not_required": sorted(
            case.get("id")
            for case in corpus.get("cases", [])
            if isinstance(case, dict)
            and case.get("required", True)
            and isinstance(case.get("id"), str)
            and case["id"] not in proof_cases
        ),
        "source_regressions": source_regressions,
        "inherited_failures": list(baseline.get("inherited_failures", [])) if isinstance(baseline, dict) else [],
        "target": target_identity,
        "freeze_intact": freeze.get("intact") is True,
        "judge_valid": _judge_valid(freeze),
        "migration_score": round(passed / total, 4) if total else 0.0,
        "score_is_informational_only": True,
    }


def _resolve_frozen_file(manifest_path: Path, freeze: dict[str, Any], label: str) -> Path:
    resolved = freeze.get("resolved_files", {})
    if isinstance(resolved, dict) and isinstance(resolved.get(label), str):
        return canonical_path(resolved[label])
    files = freeze.get("manifest", {}).get("files", {})
    entry = files.get(label) if isinstance(files, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise FrozenStateError(f"freeze manifest 缺少冻结 {label}")
    value = entry["path"]
    return canonical_path(value if Path(value).is_absolute() else manifest_path.parent / value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one Migration Skill milestone")
    parser.add_argument("--baseline", required=True, help="baseline.json")
    parser.add_argument("--source", required=True, help="source-checks.json")
    parser.add_argument("--target", required=True, help="target-checks.json")
    parser.add_argument("--parity", required=True, help="parity-result.json")
    parser.add_argument("--contract", required=True, help="frozen migration.json")
    parser.add_argument("--plan", required=True, help="migration-plan.json")
    parser.add_argument("--state", required=True, help="state.json")
    parser.add_argument("--manifest", required=True, help="freeze-manifest.json")
    parser.add_argument("--milestone-id", required=True, help="milestone ID")
    parser.add_argument("--output", required=True, help="milestone-result.json")
    parser.add_argument("--workspace-root", help="relocation workspace root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = canonical_path(args.manifest)
    freeze = verify_freeze(manifest_path, workspace_root=Path(args.workspace_root) if args.workspace_root else None)
    contract_path = _resolve_frozen_file(manifest_path, freeze, "contract")
    corpus_path = _resolve_frozen_file(manifest_path, freeze, "corpus")
    contract = load_json(contract_path)
    corpus = load_json(corpus_path)
    plan = load_json(args.plan)
    state = load_json(args.state)
    if not isinstance(contract, dict) or not isinstance(corpus, dict) or not isinstance(plan, dict) or not isinstance(state, dict):
        raise ConfigError("contract、corpus、plan、state 顶层必须是对象")
    errors = validate_documents(contract, corpus)
    if errors:
        raise ConfigError("Contract/Corpus 无法评估:\n- " + "\n- ".join(errors))
    plan_errors = validate_plan(plan, contract, corpus)
    if plan_errors:
        raise ConfigError("Migration plan 无法评估:\n- " + "\n- ".join(plan_errors))
    report = evaluate_milestone(
        load_json(args.baseline),
        load_json(args.source),
        load_json(args.target),
        load_json(args.parity),
        contract,
        corpus,
        plan,
        state,
        freeze,
        args.milestone_id,
        plan_digest=sha256_file(args.plan),
    )
    write_json(args.output, report)
    return EXIT_OK if report["eligible"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
