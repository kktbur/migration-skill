"""Produce the deterministic Migration Skill completion verdict."""

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
        result_items,
        result_map,
        resolve_manifest_path,
        sha256_bytes,
        tree_digest,
        verify_freeze,
        write_json,
    )
    from validate_contract import validate_documents
    from validate_judge import validate_artifact
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
        result_items,
        result_map,
        resolve_manifest_path,
        sha256_bytes,
        tree_digest,
        verify_freeze,
        write_json,
    )
    from .validate_contract import validate_documents
    from .validate_judge import validate_artifact
    from .validate_plan import validate_plan


QUALITY_KINDS = {
    "static": {"static", "lint", "typecheck", "type-check"},
    "build": {"build", "compile"},
    "test": {"test", "tests"},
}


def _status(item: dict[str, Any]) -> str:
    value = item.get("status", "failed")
    return value if isinstance(value, str) else "failed"


def _expected_check_map(contract: dict[str, Any], profile: str) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for check in checks_from_spec(contract, profile):
        check_id = check.get("id")
        if isinstance(check_id, str):
            expected[check_id] = check
    return expected


def _new_source_regressions(baseline: Any, current: Any) -> list[str]:
    baseline_items = result_map(baseline, "checks")
    current_items = result_map(current, "checks")
    regressions: list[str] = []
    for check_id, baseline_item in baseline_items.items():
        if _status(baseline_item) == "passed":
            current_item = current_items.get(check_id)
            if current_item is None or _status(current_item) != "passed":
                regressions.append(check_id)
    for check_id, current_item in current_items.items():
        if check_id not in baseline_items and _status(current_item) != "passed":
            regressions.append(check_id)
    return sorted(set(regressions))


def _target_failures(contract: dict[str, Any], target: Any) -> tuple[list[str], dict[str, Any]]:
    expected = _expected_check_map(contract, "target")
    actual = result_map(target, "checks")
    failures: set[str] = set()
    for check_id, check in expected.items():
        if check.get("required", True) and (
            check_id not in actual or _status(actual[check_id]) != "passed"
        ):
            failures.add(check_id)
    for check_id, item in actual.items():
        if item.get("required", True) and _status(item) != "passed":
            failures.add(check_id)
    return sorted(failures), {
        "expected": sorted(expected),
        "observed": sorted(actual),
        "required_failures": sorted(failures),
    }


def _required_check_kinds(contract: dict[str, Any]) -> set[str]:
    gates = contract.get("completion_gates", {})
    if not isinstance(gates, dict) or "required_check_kinds" not in gates:
        return set()
    values = gates.get("required_check_kinds", [])
    if not isinstance(values, list):
        return set()
    return {str(value).lower() for value in values}


def _quality_gates(contract: dict[str, Any], target: Any) -> dict[str, dict[str, Any]]:
    expected = _expected_check_map(contract, "target")
    actual = result_map(target, "checks")
    required_kinds = _required_check_kinds(contract)
    gates: dict[str, dict[str, Any]] = {}
    for gate_name, kinds in QUALITY_KINDS.items():
        configured = [
            check_id
            for check_id, check in expected.items()
            if str(check.get("kind", "check")).lower() in kinds
        ]
        observed = [
            check_id
            for check_id, item in actual.items()
            if str(item.get("kind", "check")).lower() in kinds
        ]
        failed = [
            check_id
            for check_id in configured
            if check_id not in actual or _status(actual[check_id]) != "passed"
        ]
        required = gate_name in required_kinds
        gates[gate_name] = {
            "required": required,
            "configured": bool(configured),
            "checks": sorted(configured),
            "observed": sorted(observed),
            "passed": bool(configured) and not failed if required else not failed,
            "failed": sorted(failed),
            "missing_required_configuration": required and not configured,
        }
    return gates


def _operation_key(surface_id: str, operation_id: str) -> str:
    return f"{surface_id}/{operation_id}"


def _surface_coverage(contract: dict[str, Any], corpus: dict[str, Any], parity: Any) -> dict[str, Any]:
    required_surfaces = {
        surface.get("id")
        for surface in contract.get("public_surfaces", [])
        if isinstance(surface, dict) and surface.get("required", True)
    }
    required_cases = {
        case.get("id"): case
        for case in corpus.get("cases", [])
        if isinstance(case, dict) and case.get("required", True)
    }
    covered_surfaces = {
        case.get("surface_id") for case in required_cases.values() if case.get("surface_id")
    }
    parity_cases = {
        item.get("id"): item
        for item in (parity.get("cases", []) if isinstance(parity, dict) else [])
        if isinstance(item, dict)
    }
    missing_cases = sorted(case_id for case_id in required_cases if case_id not in parity_cases)
    failed_cases = sorted(
        case_id
        for case_id in required_cases
        if case_id in parity_cases and not parity_cases[case_id].get("passed", False)
    )

    required_operations: set[str] = set()
    declared_operations: set[str] = set()
    missing_operation_declarations: list[str] = []
    for surface in contract.get("public_surfaces", []):
        if not isinstance(surface, dict) or not surface.get("required", True):
            continue
        surface_id = surface.get("id")
        operations = surface.get("operations")
        if not isinstance(operations, list) or not operations:
            missing_operation_declarations.append(str(surface_id))
            continue
        for operation in operations:
            if not isinstance(operation, dict) or not isinstance(operation.get("id"), str):
                continue
            operation_key = _operation_key(str(surface_id), operation["id"])
            declared_operations.add(operation_key)
            if operation.get("required", True):
                required_operations.add(operation_key)

    required_case_operations: dict[str, set[str]] = {}
    for case_id, case in required_cases.items():
        surface_id = case.get("surface_id")
        operation_id = case.get("operation_id")
        if isinstance(surface_id, str) and isinstance(operation_id, str):
            key = _operation_key(surface_id, operation_id)
            required_case_operations.setdefault(key, set()).add(case_id)
    covered_operations = {
        key
        for key, case_ids in required_case_operations.items()
        if any(case_id in parity_cases for case_id in case_ids)
    }
    missing_operations = sorted(
        required_operations - covered_operations
        | {_operation_key(surface_id, "<operations-not-declared>") for surface_id in missing_operation_declarations}
    )
    operation_coverage_available = not missing_operation_declarations and bool(required_surfaces) and bool(declared_operations)
    all_required_operations_covered = operation_coverage_available and not missing_operations
    missing_surfaces = sorted(
        surface_id
        for surface_id in required_surfaces
        if surface_id not in covered_surfaces or surface_id in missing_operation_declarations
    )
    return {
        "required_surfaces": sorted(required_surfaces),
        "covered_surfaces": sorted(covered_surfaces),
        "missing_surfaces": missing_surfaces,
        "required_operations": sorted(required_operations),
        "declared_operations": sorted(declared_operations),
        "covered_operations": sorted(covered_operations),
        "missing_operations": missing_operations,
        "operation_coverage_available": operation_coverage_available,
        "required_cases": sorted(required_cases),
        "missing_cases": missing_cases,
        "failed_cases": failed_cases,
        "all_required_surfaces_covered": not missing_surfaces,
        "all_required_operations_covered": all_required_operations_covered,
        "all_required_cases_present": not missing_cases,
        "all_required_cases_passed": not failed_cases,
    }


def _judge_state(freeze: dict[str, Any]) -> dict[str, Any]:
    manifest = freeze.get("manifest", {}) if isinstance(freeze, dict) else {}
    resolved_files = freeze.get("resolved_files", {}) if isinstance(freeze, dict) else {}
    resolved_path = resolved_files.get("judge_validation") if isinstance(resolved_files, dict) else None
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    entry = files.get("judge_validation") if isinstance(files, dict) else None
    declared_judge = manifest.get("judge_validation") if isinstance(manifest, dict) else None
    if resolved_path is None and not isinstance(entry, dict) and isinstance(declared_judge, dict):
        valid = declared_judge.get("valid") is True
        return {
            "positive_control": valid,
            "negative_control": valid,
            "valid": valid,
            "source": "declared-frozen-judge-validation",
            "errors": [] if valid else ["judge-validation.valid 不是 true"],
        }
    if not isinstance(resolved_path, str):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            return {
                "positive_control": False,
                "negative_control": False,
                "valid": False,
                "source": "missing-frozen-judge-validation",
            }
        resolved_path = entry["path"]
    if not isinstance(resolved_path, str):
        return {
            "positive_control": False,
            "negative_control": False,
            "valid": False,
            "source": "missing-frozen-judge-validation",
    }
    try:
        document = load_json(resolved_path)
    except ConfigError:
        document = {}
    errors = validate_artifact(document)
    return {
        "positive_control": isinstance(document, dict) and document.get("positive_control") is True,
        "negative_control": isinstance(document, dict) and document.get("negative_control") is True,
        "valid": not errors,
        "source": "frozen-judge-validation",
        "errors": errors,
    }


def _resume_state(state: dict[str, Any]) -> dict[str, Any]:
    """Describe resume status without comparing an in-progress target.

    Target digest validation belongs to ``verify_resume.py`` before edits. A
    final evaluation necessarily runs after the accepted checkpoint's target
    digest has changed, so repeating that comparison here would reject valid
    later milestones.
    """

    checkpoint = state.get("last_accepted_checkpoint")
    if checkpoint is None:
        return {"status": "not_started", "valid": True}
    if not isinstance(checkpoint, dict):
        return {"status": "invalid", "valid": False, "reason": "checkpoint is not an object"}
    return {
        "status": "preflight-required",
        "valid": True,
        "preflight_script": "verify_resume.py",
        "checkpoint": checkpoint,
    }


def _inherited_failures(baseline: Any) -> list[str]:
    if isinstance(baseline, dict) and isinstance(baseline.get("inherited_failures"), list):
        return sorted(str(item) for item in baseline["inherited_failures"])
    return sorted(
        str(item.get("id"))
        for item in result_items(baseline, "checks")
        if _status(item) != "passed"
    )


def evaluate(
    baseline: Any,
    source: Any,
    target: Any,
    parity: Any,
    contract: dict[str, Any],
    corpus: dict[str, Any],
    state: dict[str, Any],
    freeze: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_regressions = _new_source_regressions(baseline, source)
    target_failures, target_observation = _target_failures(contract, target)
    quality_gates = _quality_gates(contract, target)
    coverage = _surface_coverage(contract, corpus, parity)
    judge = _judge_state(freeze)
    resume = _resume_state(state)
    required_gaps = state.get("required_gaps", [])
    if not isinstance(required_gaps, list):
        required_gaps = ["state.required_gaps is not a list"]
    parity_summary = parity.get("summary", {}) if isinstance(parity, dict) else {}
    parity_passed = (
        isinstance(parity, dict)
        and parity.get("status") == "passed"
        and parity.get("source_valid") is not False
        and not parity_summary.get("required_failed", [])
        and coverage["all_required_cases_present"]
        and coverage["all_required_cases_passed"]
    )
    baseline_capture_clean = not bool(
        isinstance(baseline, dict) and baseline.get("source_changed_during_baseline")
    )
    baseline_status = baseline.get("status") if isinstance(baseline, dict) else None
    baseline_capture_reliable = baseline_status in {
        "captured_clean",
        "captured_with_inherited_failures",
    }
    frozen_source = freeze.get("manifest", {}).get("source", {}) if isinstance(freeze, dict) else {}
    baseline_identity_matches = (
        isinstance(baseline, dict)
        and baseline.get("revision") == frozen_source.get("revision")
        and baseline.get("tree_digest") == frozen_source.get("tree_digest")
    )
    required_quality_gates = {
        name: gate for name, gate in quality_gates.items() if gate["required"]
    }
    quality_passed = all(gate["passed"] for gate in required_quality_gates.values())
    target_checks_passed = not target_failures
    no_required_gaps = not required_gaps
    plan_errors: list[str] = []
    milestone_ids: list[str] = []
    completed_milestones = state.get("completed_milestones", [])
    if plan is not None:
        plan_errors = validate_plan(plan, contract, corpus)
        if isinstance(plan.get("milestones"), list):
            milestone_ids = [
                item["id"]
                for item in plan["milestones"]
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        completed_set = set(completed_milestones) if isinstance(completed_milestones, list) else set()
        all_milestones_completed = not plan_errors and set(milestone_ids).issubset(completed_set)
    else:
        all_milestones_completed = True
    try:
        target_result_map = result_map(target, "checks")
    except ConfigError:
        target_result_map = {}
    proof_cases = sorted(
        case_id
        for case_id, item in ((case.get("id"), case) for case in corpus.get("cases", []))
        if isinstance(case_id, str)
        and item.get("required", True)
        and isinstance(parity, dict)
        and any(
            result.get("id") == case_id and result.get("passed") is True
            for result in parity.get("cases", [])
            if isinstance(result, dict)
        )
    )
    proof_checks = sorted(
        check_id
        for check_id, check in _expected_check_map(contract, "target").items()
        if check.get("required", True)
        and check_id in target_result_map
        and _status(target_result_map[check_id]) == "passed"
    )
    required_conditions = {
        "freeze_intact": bool(freeze.get("intact", False)),
        "baseline_capture_clean": baseline_capture_clean,
        "baseline_capture_reliable": baseline_capture_reliable,
        "baseline_identity_matches": baseline_identity_matches,
        "no_new_source_regression": not source_regressions,
        "target_required_checks": target_checks_passed,
        "required_quality_gates": quality_passed,
        "parity": parity_passed,
        "public_surface_coverage": coverage["all_required_surfaces_covered"],
        "operation_coverage": coverage["all_required_operations_covered"],
        "no_required_gaps": no_required_gaps,
        "judge_valid": judge["valid"],
        "resume_checkpoint": resume["valid"],
    }
    if plan is not None:
        required_conditions["plan_valid"] = not plan_errors
        required_conditions["all_milestones_completed"] = all_milestones_completed
    all_required_gates = all(required_conditions.values())
    if not required_conditions["freeze_intact"]:
        status = "INVALIDATED"
    elif not judge["valid"]:
        status = "PLAN_ONLY"
    elif not resume["valid"]:
        status = "INVALIDATED"
    elif plan_errors:
        status = "PLAN_ONLY"
    elif (
        source_regressions
        or not baseline_capture_clean
        or not baseline_capture_reliable
        or not baseline_identity_matches
        or required_gaps
    ):
        status = "BLOCKED"
    elif all_required_gates:
        status = "VERIFIED"
    else:
        status = "PARTIALLY_VERIFIED"

    gate_failures: list[str] = []
    for name, passed in required_conditions.items():
        if not passed:
            gate_failures.append(f"{name}-not-passed")
    if target_failures:
        gate_failures.extend(f"target-check-failed:{item}" for item in target_failures)
    for case_id in coverage["missing_cases"]:
        gate_failures.append(f"required-parity-case-missing:{case_id}")
    for case_id in coverage["failed_cases"]:
        gate_failures.append(f"required-parity-case-failed:{case_id}")
    for operation_id in coverage["missing_operations"]:
        gate_failures.append(f"required-operation-uncovered:{operation_id}")
    gate_failures.extend(f"required-gap:{gap}" for gap in required_gaps)
    total_gates = len(required_conditions)
    passed_gate_count = sum(bool(value) for value in required_conditions.values())
    return {
        "schema_version": 2,
        "status": status,
        "source_baseline_regressed": bool(source_regressions),
        "source_regressions": source_regressions,
        "inherited_failures": _inherited_failures(baseline),
        "baseline_capture_clean": baseline_capture_clean,
        "baseline_capture_reliable": baseline_capture_reliable,
        "baseline_identity_matches": baseline_identity_matches,
        "target": {
            "checks_passed": target_checks_passed,
            "required_failures": target_failures,
            "observation": target_observation,
            "quality_gates": quality_gates,
        },
        "parity": {
            "passed": parity_passed,
            "reported_status": parity.get("status") if isinstance(parity, dict) else None,
            "summary": parity_summary,
            "coverage": coverage,
        },
        "judge": judge,
        "freeze_intact": bool(freeze.get("intact")),
        "required_gaps": [str(item) for item in required_gaps],
        "plan": {
            "provided": plan is not None,
            "milestones": milestone_ids,
            "completed_milestones": list(completed_milestones) if isinstance(completed_milestones, list) else [],
            "all_milestones_completed": all_milestones_completed,
            "errors": plan_errors,
        },
        "proof_set": {"cases": proof_cases, "checks": proof_checks},
        "required_conditions": required_conditions,
        "gate_failures": sorted(set(gate_failures)),
        "migration_score": round(passed_gate_count / total_gates, 4) if total_gates else 0.0,
        "score_is_informational_only": True,
        "ratchet_eligible": all_required_gates,
        "resume": {
            "current_milestone": state.get("current_milestone"),
            "completed_milestones": state.get("completed_milestones", []),
            "last_accepted_checkpoint": state.get("last_accepted_checkpoint"),
            "checkpoint_validation": resume,
        },
    }


def _load_frozen_documents(
    contract_arg: str,
    manifest_path: str | Path,
    manifest_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    files = manifest_data.get("files", {})
    if not isinstance(files, dict) or "contract" not in files or "corpus" not in files:
        raise FrozenStateError("freeze manifest 必须冻结 contract 和 corpus")
    contract_entry = files["contract"]
    corpus_entry = files["corpus"]
    if not isinstance(contract_entry, dict) or not isinstance(corpus_entry, dict):
        raise FrozenStateError("freeze manifest 的 contract/corpus 条目无效")
    supplied_contract = canonical_path(contract_arg)
    frozen_contract_path = resolve_manifest_path(manifest_path, manifest_data, contract_entry.get("path", ""))
    if supplied_contract != frozen_contract_path:
        raise FrozenStateError("传入的 contract 不是冻结的 contract 文件")
    contract = load_json(frozen_contract_path)
    corpus = load_json(resolve_manifest_path(manifest_path, manifest_data, corpus_entry.get("path", "")))
    return contract, corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a Migration Skill migration")
    parser.add_argument("--baseline", required=True, help="baseline.json")
    parser.add_argument("--source", required=True, help="current source-checks.json")
    parser.add_argument("--target", required=True, help="target-checks.json")
    parser.add_argument("--parity", required=True, help="parity-result.json")
    parser.add_argument("--contract", required=True, help="frozen migration.json")
    parser.add_argument("--manifest", required=True, help="freeze-manifest.json")
    parser.add_argument("--state", required=True, help="state.json")
    parser.add_argument("--output", required=True, help="migration-result.json")
    parser.add_argument("--plan", help="optional migration-plan.json; required for final milestone completion")
    parser.add_argument("--workspace-root", help="relocation workspace root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    freeze = verify_freeze(args.manifest, workspace_root=Path(args.workspace_root) if args.workspace_root else None)
    contract, corpus = _load_frozen_documents(args.contract, args.manifest, freeze["manifest"])
    errors = validate_documents(contract, corpus)
    if errors:
        raise ConfigError("Contract/Corpus 无法评估:\n- " + "\n- ".join(errors))
    state = load_json(args.state)
    if not isinstance(state, dict):
        raise ConfigError("state.json 顶层必须是对象")
    manifest_source_revision = freeze["manifest"].get("source", {}).get("revision")
    if state.get("source_revision") is not None and state.get("source_revision") != manifest_source_revision:
        raise FrozenStateError("state.json 的 source_revision 与 freeze manifest 不一致")
    plan = load_json(args.plan) if args.plan else None
    if args.plan is not None and not isinstance(plan, dict):
        raise ConfigError("migration-plan.json 顶层必须是对象")
    report = evaluate(
        load_json(args.baseline),
        load_json(args.source),
        load_json(args.target),
        load_json(args.parity),
        contract,
        corpus,
        state,
        freeze,
        plan,
    )
    write_json(args.output, report)
    return EXIT_OK if report["status"] == "VERIFIED" else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
