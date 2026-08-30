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
        load_json,
        result_map,
        result_items,
        verify_freeze,
        write_json,
    )
    from validate_contract import validate_documents
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        FrozenStateError,
        canonical_path,
        checks_from_spec,
        load_json,
        result_map,
        result_items,
        verify_freeze,
        write_json,
    )
    from .validate_contract import validate_documents


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


def _quality_gates(contract: dict[str, Any], target: Any) -> dict[str, dict[str, Any]]:
    expected = _expected_check_map(contract, "target")
    actual = result_map(target, "checks")
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
        gates[gate_name] = {
            "configured": bool(configured),
            "checks": sorted(configured),
            "observed": sorted(observed),
            "passed": bool(configured) and not failed,
            "failed": sorted(failed),
        }
    return gates


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
        case_id for case_id in required_cases if case_id in parity_cases and not parity_cases[case_id].get("passed", False)
    )
    missing_surfaces = sorted(surface_id for surface_id in required_surfaces if surface_id not in covered_surfaces)
    return {
        "required_surfaces": sorted(required_surfaces),
        "covered_surfaces": sorted(covered_surfaces),
        "missing_surfaces": missing_surfaces,
        "required_cases": sorted(required_cases),
        "missing_cases": missing_cases,
        "failed_cases": failed_cases,
        "all_required_surfaces_covered": not missing_surfaces,
        "all_required_cases_present": not missing_cases,
        "all_required_cases_passed": not failed_cases,
    }


def _judge_state(state: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    judge = state.get("judge", {})
    if not isinstance(judge, dict):
        judge = {}
    frozen_files = freeze.get("manifest", {}).get("files", {}) if isinstance(freeze, dict) else {}
    frozen_judge = frozen_files.get("judge_validation") if isinstance(frozen_files, dict) else None
    if isinstance(frozen_judge, dict) and isinstance(frozen_judge.get("path"), str):
        try:
            frozen_document = load_json(frozen_judge["path"])
        except ConfigError:
            frozen_document = {}
        positive = isinstance(frozen_document, dict) and frozen_document.get("positive_control") is True
        negative = isinstance(frozen_document, dict) and frozen_document.get("negative_control") is True
        source = "frozen-judge-validation"
    else:
        positive = judge.get("positive_control") is True
        negative = judge.get("negative_control") is True
        source = "state"
    return {
        "positive_control": positive,
        "negative_control": negative,
        "valid": positive and negative,
        "source": source,
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
) -> dict[str, Any]:
    source_regressions = _new_source_regressions(baseline, source)
    target_failures, target_observation = _target_failures(contract, target)
    quality_gates = _quality_gates(contract, target)
    coverage = _surface_coverage(contract, corpus, parity)
    judge = _judge_state(state, freeze)
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
    frozen_source = freeze.get("manifest", {}).get("source", {}) if isinstance(freeze, dict) else {}
    baseline_identity_matches = (
        isinstance(baseline, dict)
        and baseline.get("revision") == frozen_source.get("revision")
        and baseline.get("tree_digest") == frozen_source.get("tree_digest")
    )
    quality_passed = all(gate["passed"] for gate in quality_gates.values())
    target_checks_passed = not target_failures
    no_required_gaps = not required_gaps
    all_required_gates = (
        freeze.get("intact", False)
        and baseline_capture_clean
        and baseline_identity_matches
        and not source_regressions
        and target_checks_passed
        and quality_passed
        and parity_passed
        and coverage["all_required_surfaces_covered"]
        and no_required_gaps
        and judge["valid"]
    )
    if not judge["valid"]:
        status = "PLAN_ONLY"
    elif source_regressions or not baseline_capture_clean or not baseline_identity_matches or required_gaps:
        status = "BLOCKED"
    elif all_required_gates:
        status = "VERIFIED"
    else:
        status = "PARTIALLY_VERIFIED"

    gate_failures: list[str] = []
    if not baseline_capture_clean:
        gate_failures.append("baseline-source-changed-during-capture")
    if not baseline_identity_matches:
        gate_failures.append("baseline-source-identity-does-not-match-freeze")
    if source_regressions:
        gate_failures.extend(f"new-source-regression:{item}" for item in source_regressions)
    if target_failures:
        gate_failures.extend(f"target-check-failed:{item}" for item in target_failures)
    for gate_name, gate in quality_gates.items():
        if not gate["passed"]:
            gate_failures.append(f"target-{gate_name}-gate-not-passed")
    if not parity_passed:
        gate_failures.append("parity-gate-not-passed")
    for surface_id in coverage["missing_surfaces"]:
        gate_failures.append(f"required-surface-uncovered:{surface_id}")
    for case_id in coverage["missing_cases"]:
        gate_failures.append(f"required-parity-case-missing:{case_id}")
    for case_id in coverage["failed_cases"]:
        gate_failures.append(f"required-parity-case-failed:{case_id}")
    gate_failures.extend(f"required-gap:{gap}" for gap in required_gaps)
    if not judge["valid"]:
        gate_failures.append("judge-validation-missing-or-invalid")
    total_gates = 10
    passed_gate_count = sum(
        bool(value)
        for value in (
            freeze.get("intact", False),
            baseline_capture_clean,
            baseline_identity_matches,
            not source_regressions,
            target_checks_passed,
            quality_passed,
            parity_passed,
            coverage["all_required_surfaces_covered"],
            no_required_gaps,
            judge["valid"],
        )
    )
    return {
        "schema_version": 1,
        "status": status,
        "source_baseline_regressed": bool(source_regressions),
        "source_regressions": source_regressions,
        "inherited_failures": _inherited_failures(baseline),
        "baseline_capture_clean": baseline_capture_clean,
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
        "gate_failures": sorted(set(gate_failures)),
        "migration_score": round(passed_gate_count / total_gates, 4),
        "score_is_informational_only": True,
        "resume": {
            "current_milestone": state.get("current_milestone"),
            "completed_milestones": state.get("completed_milestones", []),
            "last_accepted_checkpoint": state.get("last_accepted_checkpoint"),
        },
    }


def _load_frozen_documents(contract_arg: str, manifest_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    files = manifest_data.get("files", {})
    if not isinstance(files, dict) or "contract" not in files or "corpus" not in files:
        raise FrozenStateError("freeze manifest 必须冻结 contract 和 corpus")
    contract_entry = files["contract"]
    corpus_entry = files["corpus"]
    if not isinstance(contract_entry, dict) or not isinstance(corpus_entry, dict):
        raise FrozenStateError("freeze manifest 的 contract/corpus 条目无效")
    supplied_contract = canonical_path(contract_arg)
    frozen_contract_path = canonical_path(contract_entry.get("path", ""))
    if supplied_contract != frozen_contract_path:
        raise FrozenStateError("传入的 contract 不是冻结的 contract 文件")
    contract = load_json(frozen_contract_path)
    corpus = load_json(canonical_path(corpus_entry.get("path", "")))
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    freeze = verify_freeze(args.manifest)
    contract, corpus = _load_frozen_documents(args.contract, freeze["manifest"])
    errors = validate_documents(contract, corpus)
    if errors:
        raise ConfigError("Contract/Corpus 无法评估:\n- " + "\n- ".join(errors))
    state = load_json(args.state)
    if not isinstance(state, dict):
        raise ConfigError("state.json 顶层必须是对象")
    manifest_source_revision = freeze["manifest"].get("source", {}).get("revision")
    if state.get("source_revision") is not None and state.get("source_revision") != manifest_source_revision:
        raise FrozenStateError("state.json 的 source_revision 与 freeze manifest 不一致")
    report = evaluate(
        load_json(args.baseline),
        load_json(args.source),
        load_json(args.target),
        load_json(args.parity),
        contract,
        corpus,
        state,
        freeze,
    )
    write_json(args.output, report)
    return EXIT_OK if report["status"] == "VERIFIED" else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
