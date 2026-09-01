"""Compare portable Source/Target parity adapter results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        compare_values,
        load_json,
        result_map,
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
        compare_values,
        load_json,
        result_map,
        verify_freeze,
        write_json,
    )
    from .validate_contract import validate_documents


MISSING = object()


def _surface_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        surface["id"]: surface
        for surface in contract.get("public_surfaces", [])
        if isinstance(surface, dict) and isinstance(surface.get("id"), str)
    }


def _observed(item: dict[str, Any]) -> Any:
    for key in ("observed", "output", "value"):
        if key in item:
            return item[key]
    metadata = {"id", "surface_id", "operation_id", "status", "required", "duration_seconds"}
    payload = {key: value for key, value in item.items() if key not in metadata}
    return payload if payload else MISSING


def _status(item: dict[str, Any]) -> str:
    value = item.get("status", "passed")
    return value if isinstance(value, str) else "failed"


def _comparator(value: Any) -> tuple[str, Any]:
    if value is True:
        return "exact", None
    if isinstance(value, str):
        return value, None
    if isinstance(value, dict):
        mode = value.get("mode")
        if not isinstance(mode, str):
            raise ConfigError("比较配置缺少 mode")
        return mode, value.get("normalization")
    raise ConfigError("无效的比较配置")


def _comparison_entries(surface: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    compare = surface.get("compare", {})
    if not isinstance(compare, dict):
        raise ConfigError(f"surface.compare 不是对象: {surface.get('id')}")
    if "whole" in compare:
        yield "__self__", compare["whole"]
        return
    if "fields" in compare:
        fields = compare["fields"]
        if not isinstance(fields, dict):
            raise ConfigError(f"surface.compare.fields 不是对象: {surface.get('id')}")
        for field, configuration in fields.items():
            yield field, configuration
        return

    # v1 compatibility. This path is intentionally not used for v2 contracts.
    if "mode" in compare:
        yield "__self__", compare
    else:
        yield from compare.items()


def _compare_surface(source_value: Any, target_value: Any, surface: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for field, configuration in _comparison_entries(surface):
        mode, normalization = _comparator(configuration)
        if field == "__self__":
            passed = source_value is not MISSING and target_value is not MISSING and compare_values(
                source_value, target_value, mode, normalization
            )
            comparisons.append(
                {"field": field, "mode": mode, "normalization": normalization, "passed": passed}
            )
            continue
        source_has = isinstance(source_value, dict) and field in source_value
        target_has = isinstance(target_value, dict) and field in target_value
        passed = (
            source_has
            and target_has
            and compare_values(source_value[field], target_value[field], mode, normalization)
        )
        comparisons.append(
            {
                "field": field,
                "mode": mode,
                "normalization": normalization,
                "source_present": source_has,
                "target_present": target_has,
                "passed": passed,
            }
        )
    return comparisons


def compare(
    source_document: Any,
    target_document: Any,
    contract: dict[str, Any],
    corpus: dict[str, Any],
    *,
    expect_mismatch: bool = False,
    expected_cases: set[str] | None = None,
) -> dict[str, Any]:
    source_results = result_map(source_document, "cases")
    target_results = result_map(target_document, "cases")
    surfaces = _surface_map(contract)
    cases = corpus.get("cases", [])
    if not isinstance(cases, list):
        raise ConfigError("parity corpus cases 必须是数组")
    comparisons: list[dict[str, Any]] = []
    source_invalid = False
    for case in cases:
        if not isinstance(case, dict):
            raise ConfigError("parity corpus case 必须是对象")
        case_id = case["id"]
        surface_id = case["surface_id"]
        operation_id = case.get("operation_id")
        required = case.get("required", True)
        surface = surfaces.get(surface_id)
        if surface is None:
            raise ConfigError(f"case 引用了未知 surface: {surface_id}")
        source_item = source_results.get(case_id)
        target_item = target_results.get(case_id)
        reason: str | None = None
        field_comparisons: list[dict[str, Any]] = []
        if source_item is None:
            passed = False
            source_invalid = source_invalid or bool(required)
            reason = "missing-source-case"
        elif _status(source_item) != "passed":
            passed = False
            source_invalid = source_invalid or bool(required)
            reason = "source-case-failed"
        elif source_item.get("surface_id") not in (None, surface_id):
            passed = False
            source_invalid = source_invalid or bool(required)
            reason = "source-surface-mismatch"
        elif operation_id is not None and source_item.get("operation_id") not in (None, operation_id):
            passed = False
            source_invalid = source_invalid or bool(required)
            reason = "source-operation-mismatch"
        elif target_item is None:
            passed = False
            reason = "missing-target-case"
        elif _status(target_item) != "passed":
            passed = False
            reason = "target-case-failed"
        elif target_item.get("surface_id") not in (None, surface_id):
            passed = False
            reason = "target-surface-mismatch"
        elif operation_id is not None and target_item.get("operation_id") not in (None, operation_id):
            passed = False
            reason = "target-operation-mismatch"
        else:
            source_value = _observed(source_item)
            target_value = _observed(target_item)
            field_comparisons = _compare_surface(source_value, target_value, surface)
            passed = bool(field_comparisons) and all(item["passed"] for item in field_comparisons)
            if not passed:
                reason = "observable-mismatch"
        comparisons.append(
            {
                "id": case_id,
                "surface_id": surface_id,
                "operation_id": operation_id,
                "required": required,
                "passed": passed,
                "reason": reason,
                "comparisons": field_comparisons,
            }
        )

    required_failed = [item["id"] for item in comparisons if item["required"] and not item["passed"]]
    optional_failed = [item["id"] for item in comparisons if not item["required"] and not item["passed"]]
    mismatch_detected = bool(required_failed or optional_failed)
    source_valid = not source_invalid
    targeted_mismatches: list[str] = []
    targeted_failures: list[str] = []
    if expected_cases:
        by_id = {item["id"]: item for item in comparisons}
        for case_id in sorted(expected_cases):
            item = by_id.get(case_id)
            if item is None:
                targeted_failures.append(case_id)
            elif item["required"] is not True or item["passed"]:
                targeted_failures.append(case_id)
            else:
                targeted_mismatches.append(case_id)
        targeted_control_passed = source_valid and not targeted_failures and bool(targeted_mismatches)
    else:
        targeted_control_passed = None

    if expect_mismatch:
        if expected_cases:
            status = "negative_control_passed" if targeted_control_passed else "negative_control_failed"
        else:
            # Kept for old callers, but validate_judge.py refuses an unscoped
            # negative control as evidence of a valid Judge.
            status = "negative_control_passed" if source_valid and mismatch_detected else "negative_control_failed"
        passed = status == "negative_control_passed"
    else:
        status = "passed" if source_valid and not required_failed else "failed"
        passed = status == "passed"
    return {
        "schema_version": 2,
        "status": status,
        "negative_control": expect_mismatch,
        "negative_control_scoped": bool(expected_cases),
        "negative_control_passed": status == "negative_control_passed" if expect_mismatch else None,
        "source_valid": source_valid,
        "cases": comparisons,
        "summary": {
            "total": len(comparisons),
            "passed": sum(1 for item in comparisons if item["passed"]),
            "failed": sum(1 for item in comparisons if not item["passed"]),
            "required_failed": required_failed,
            "optional_failed": optional_failed,
            "mismatch_detected": mismatch_detected,
            "expected_mismatch_cases": sorted(expected_cases or set()),
            "detected_mismatch_cases": targeted_mismatches,
            "targeted_mismatch_failures": targeted_failures,
            "targeted_control_passed": targeted_control_passed,
        },
        "passed": passed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Source and Target parity results")
    parser.add_argument("--source", required=True, help="source adapter result JSON")
    parser.add_argument("--target", required=True, help="target adapter result JSON")
    parser.add_argument("--contract", required=True, help="migration.json")
    parser.add_argument("--corpus", required=True, help="parity-corpus.json")
    parser.add_argument("--manifest", help="freeze-manifest.json; required after Freeze")
    parser.add_argument("--output", required=True, help="parity-result.json")
    parser.add_argument(
        "--expect-mismatch",
        action="store_true",
        help="negative control; combine with --expect-case for targeted validation",
    )
    parser.add_argument(
        "--expect-case",
        action="append",
        default=[],
        help="required case id that the mutation must make fail; repeatable",
    )
    parser.add_argument(
        "--pre-freeze",
        action="store_true",
        help="bootstrap Judge validation before a freeze manifest exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pre_freeze:
        if args.manifest:
            raise ConfigError("--pre-freeze 不能同时提供 --manifest")
        freeze_intact = False
    else:
        if not args.manifest:
            raise ConfigError("冻结后的比较必须提供 --manifest；Judge bootstrap 请使用 --pre-freeze")
        freeze_intact = verify_freeze(args.manifest)["intact"]
    contract = load_json(args.contract)
    corpus = load_json(args.corpus)
    errors = validate_documents(contract, corpus)
    if errors:
        raise ConfigError("Contract/Corpus 无法比较:\n- " + "\n- ".join(errors))
    report = compare(
        load_json(args.source),
        load_json(args.target),
        contract,
        corpus,
        expect_mismatch=args.expect_mismatch,
        expected_cases=set(args.expect_case),
    )
    report["freeze_intact"] = freeze_intact
    write_json(args.output, report)
    return EXIT_OK if report["passed"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
