"""Validate the JSON Behavior Contract and its separate parity corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        is_secret_env_name,
        load_json,
        write_json,
    )
except ImportError:  # pragma: no cover - useful when imported as a package
    from .common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        is_secret_env_name,
        load_json,
        write_json,
    )


SURFACE_KINDS = {"command", "http", "library", "snapshot", "file-io"}
COMPARE_MODES = {"exact", "text", "text-normalized", "json-semantic", "exit-code", "snapshot"}
NORMALIZATION_RULES = {"crlf-to-lf", "trim-trailing-whitespace"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
CONTRACT_SCHEMA_VERSIONS = {1, 2}
CORPUS_SCHEMA_VERSIONS = {1, 2}
FORBIDDEN_CORPUS_KEYS = {"expected", "compare", "normalization", "behavior_contract"}
CHECK_GATE_KINDS = {
    "static",
    "lint",
    "typecheck",
    "type-check",
    "build",
    "compile",
    "test",
    "tests",
    "parity",
}


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _string(value: Any, label: str, errors: list[str], *, nonempty: bool = True) -> bool:
    if not isinstance(value, str) or (nonempty and not value) or "\x00" in value:
        _error(errors, f"{label} 必须是有效字符串")
        return False
    return True


def _relative_path(value: Any, label: str, errors: list[str], *, allow_parent: bool = False) -> None:
    if not _string(value, label, errors):
        return
    if os.path.isabs(value):
        _error(errors, f"{label} 不应是绝对路径")
    parts = Path(value).parts
    if not allow_parent and ".." in parts:
        _error(errors, f"{label} 不应包含 .. 路径段")


def _argv(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        _error(errors, f"{label} 必须是非空字符串数组，不支持 shell 字符串")
        return
    for index, item in enumerate(value):
        _string(item, f"{label}[{index}]", errors)


def _environment(value: Any, label: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _error(errors, f"{label} 必须是对象")
        return
    unknown = set(value) - {"inherit", "set"}
    if unknown:
        _error(errors, f"{label} 包含未知字段: {sorted(unknown)}")
    inherit = value.get("inherit", [])
    if not isinstance(inherit, list) or any(not isinstance(item, str) or not item for item in inherit):
        _error(errors, f"{label}.inherit 必须是字符串数组")
    values = value.get("set", {})
    if not isinstance(values, dict) or any(
        not isinstance(key, str) or not key or not isinstance(item, str) for key, item in values.items()
    ):
        _error(errors, f"{label}.set 必须是字符串到字符串的对象")
    names = [item for item in inherit if isinstance(item, str)]
    names.extend(key for key in values if isinstance(key, str))
    for name in names:
        if "\x00" in name or is_secret_env_name(name):
            _error(errors, f"{label} 不允许疑似 Secret 环境变量: {name}")


def _validate_adapter(adapter: Any, label: str, errors: list[str]) -> None:
    if not isinstance(adapter, dict):
        _error(errors, f"{label} 必须是对象")
        return
    _string(adapter.get("kind", "harness"), f"{label}.kind", errors)
    _argv(adapter.get("argv"), f"{label}.argv", errors)
    if "shell" in adapter and adapter.get("shell") is not False:
        _error(errors, f"{label}.shell 必须为 false；Migration Skill 不执行 shell 字符串")
    timeout = adapter.get("timeout_seconds")
    if timeout is not None and (
        not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0
    ):
        _error(errors, f"{label}.timeout_seconds 必须是正数")
    _environment(adapter.get("environment"), f"{label}.environment", errors)


def _normalization(value: Any, label: str, errors: list[str]) -> None:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = value
    else:
        _error(errors, f"{label} 必须是字符串或字符串数组")
        return
    for item in values:
        if item not in NORMALIZATION_RULES:
            _error(errors, f"{label} 不支持的规则: {item}")


def _comparator_config(value: Any, label: str, errors: list[str]) -> None:
    if value is True:
        return
    if isinstance(value, str):
        if value not in COMPARE_MODES:
            _error(errors, f"{label} 比较模式不支持: {value}")
        return
    if isinstance(value, dict):
        mode = value.get("mode")
        if not isinstance(mode, str) or mode not in COMPARE_MODES:
            _error(errors, f"{label}.mode 必须是受支持的比较模式")
        unknown = set(value) - {"mode", "normalization"}
        if unknown:
            _error(errors, f"{label} 包含未知字段: {sorted(unknown)}")
        if "normalization" in value:
            _normalization(value.get("normalization"), f"{label}.normalization", errors)
        return
    _error(errors, f"{label} 必须是 true、比较模式字符串或比较配置对象")


def _compare(value: Any, label: str, errors: list[str], schema_version: int) -> None:
    if not isinstance(value, dict) or not value:
        _error(errors, f"{label} 必须是非空对象")
        return
    if schema_version >= 2:
        keys = set(value)
        if keys == {"whole"}:
            _comparator_config(value["whole"], f"{label}.whole", errors)
            return
        if keys == {"fields"} and isinstance(value.get("fields"), dict) and value["fields"]:
            for field, comparator in value["fields"].items():
                _string(field, f"{label}.fields field", errors)
                _comparator_config(comparator, f"{label}.fields.{field}", errors)
            return
        _error(errors, f"{label} v2 必须恰好使用 whole 或非空 fields，不能混用 mode 与 observed field")
        return

    # v1 compatibility is retained for old contracts, but v1 has no operation
    # coverage and therefore cannot by itself prove a VERIFIED migration.
    if set(value) == {"mode"} or set(value) <= {"mode", "normalization"}:
        _comparator_config(value, label, errors)
        return
    for field, comparator in value.items():
        _string(field, f"{label} field", errors)
        _comparator_config(comparator, f"{label}.{field}", errors)


def _evidence(value: Any, label: str, errors: list[str], *, required: bool = False) -> None:
    if value is None:
        value = []
    if not isinstance(value, list) or (required and not value):
        _error(errors, f"{label} 必须是非空 evidence 数组" if required else f"{label} 必须是数组")
        return
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if isinstance(item, str):
            _relative_path(item, item_label, errors)
            continue
        if isinstance(item, dict):
            _relative_path(item.get("path"), f"{item_label}.path", errors)
            _string(item.get("type"), f"{item_label}.type", errors)
            if "line" in item and (
                not isinstance(item.get("line"), int) or isinstance(item.get("line"), bool) or item.get("line") <= 0
            ):
                _error(errors, f"{item_label}.line 必须是正整数")
            continue
        _error(errors, f"{item_label} 必须是路径字符串或 path/type evidence 对象")


def _operations(surface: Any, label: str, errors: list[str], schema_version: int) -> dict[str, bool]:
    raw_operations = surface.get("operations")
    if schema_version < 2 and raw_operations is None:
        return {}
    if not isinstance(raw_operations, list) or (schema_version >= 2 and not raw_operations):
        _error(errors, f"{label}.operations 必须是非空数组")
        return {}
    operation_ids: dict[str, bool] = {}
    for index, operation in enumerate(raw_operations or []):
        operation_label = f"{label}.operations[{index}]"
        if not isinstance(operation, dict):
            _error(errors, f"{operation_label} 必须是对象")
            continue
        operation_id = operation.get("id")
        if _string(operation_id, f"{operation_label}.id", errors):
            if operation_id in operation_ids:
                _error(errors, f"{label}.operations 包含重复 id: {operation_id}")
            operation_ids[operation_id] = operation.get("required", True)
        if "required" in operation and not isinstance(operation.get("required"), bool):
            _error(errors, f"{operation_label}.required 必须是布尔值")
        _evidence(operation.get("evidence"), f"{operation_label}.evidence", errors, required=schema_version >= 2)
        if "description" in operation:
            _string(operation.get("description"), f"{operation_label}.description", errors)
    return operation_ids


def _validate_check(check: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(check, dict):
        _error(errors, f"{label} 必须是对象")
        return None
    check_id = check.get("id")
    if not _string(check_id, f"{label}.id", errors):
        check_id = None
    _argv(check.get("argv"), f"{label}.argv", errors)
    if "shell" in check and check.get("shell") is not False:
        _error(errors, f"{label}.shell 必须为 false")
    if "required" in check and not isinstance(check.get("required"), bool):
        _error(errors, f"{label}.required 必须是布尔值")
    if "profile" in check and check.get("profile") not in {"source", "target"}:
        _error(errors, f"{label}.profile 必须是 source 或 target")
    if "kind" in check and not isinstance(check.get("kind"), str):
        _error(errors, f"{label}.kind 必须是字符串")
    if "expected_exit_code" in check and (
        not isinstance(check.get("expected_exit_code"), int)
        or isinstance(check.get("expected_exit_code"), bool)
    ):
        _error(errors, f"{label}.expected_exit_code 必须是整数")
    timeout = check.get("timeout_seconds")
    if timeout is not None and (
        not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0
    ):
        _error(errors, f"{label}.timeout_seconds 必须是正数")
    cwd = check.get("cwd")
    if cwd is not None:
        _relative_path(cwd, f"{label}.cwd", errors)
    if "environment" in check and "env" in check:
        _error(errors, f"{label} 不能同时使用 environment 和旧版 env")
    _environment(check.get("environment"), f"{label}.environment", errors)
    legacy_env = check.get("env")
    if legacy_env is not None:
        if not isinstance(legacy_env, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in legacy_env.items()
        ):
            _error(errors, f"{label}.env 必须是字符串到字符串的对象")
        else:
            _environment({"set": legacy_env}, f"{label}.env", errors)
    return check_id


def _validate_checks(value: Any, errors: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, list):
        seen: set[str] = set()
        for index, check in enumerate(value):
            check_id = _validate_check(check, f"checks[{index}]", errors)
            if check_id is not None and check_id in seen:
                _error(errors, f"checks 包含重复 id: {check_id}")
            if check_id is not None:
                seen.add(check_id)
        return
    if isinstance(value, dict):
        unknown = set(value) - {"source", "target"}
        if unknown:
            _error(errors, f"checks 包含未知 profile: {sorted(unknown)}")
        for profile in ("source", "target"):
            if profile in value:
                _validate_checks(value[profile], errors)
        return
    _error(errors, "checks 必须是数组或 source/target 对象")


def _validate_completion_gates(value: Any, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _error(errors, "completion_gates 必须是对象")
        return
    unknown = set(value) - {"required_check_kinds"}
    if unknown:
        _error(errors, f"completion_gates 包含未知字段: {sorted(unknown)}")
    kinds = value.get("required_check_kinds", [])
    if not isinstance(kinds, list) or any(not isinstance(item, str) or not item for item in kinds):
        _error(errors, "completion_gates.required_check_kinds 必须是字符串数组")
    elif any(item.lower() not in CHECK_GATE_KINDS for item in kinds):
        _error(errors, "completion_gates.required_check_kinds 包含未知检查类型")


def _validate_contract(contract: Any, errors: list[str]) -> tuple[set[str], dict[str, dict[str, bool]]]:
    if not isinstance(contract, dict):
        _error(errors, "migration.json 顶层必须是对象")
        return set(), {}
    schema_version = contract.get("schema_version")
    if schema_version not in CONTRACT_SCHEMA_VERSIONS:
        _error(errors, "migration.json.schema_version 必须为 1 或 2")
        schema_version = 1
    for side in ("source", "target"):
        value = contract.get(side)
        if not isinstance(value, dict):
            _error(errors, f"{side} 必须是对象")
            continue
        _relative_path(value.get("root"), f"{side}.root", errors, allow_parent=True)
        _string(value.get("language"), f"{side}.language", errors)
        if "framework" in value:
            _string(value.get("framework"), f"{side}.framework", errors)
        if "entrypoints" in value:
            entrypoints = value.get("entrypoints")
            if not isinstance(entrypoints, list) or any(not isinstance(item, str) for item in entrypoints):
                _error(errors, f"{side}.entrypoints 必须是字符串数组")
        if "revision" in value and value.get("revision") != "AUTO":
            _string(value.get("revision"), f"{side}.revision", errors)

    _environment(contract.get("environment"), "environment", errors)
    _validate_completion_gates(contract.get("completion_gates"), errors)

    surfaces = contract.get("public_surfaces")
    surface_ids: set[str] = set()
    operations_by_surface: dict[str, dict[str, bool]] = {}
    if not isinstance(surfaces, list):
        _error(errors, "public_surfaces 必须是数组")
        surfaces = []
    for index, surface in enumerate(surfaces):
        label = f"public_surfaces[{index}]"
        if not isinstance(surface, dict):
            _error(errors, f"{label} 必须是对象")
            continue
        surface_id = surface.get("id")
        if _string(surface_id, f"{label}.id", errors):
            if surface_id in surface_ids:
                _error(errors, f"public_surfaces 包含重复 id: {surface_id}")
            surface_ids.add(surface_id)
        kind = surface.get("kind")
        if kind not in SURFACE_KINDS:
            _error(errors, f"{label}.kind 不支持: {kind}")
        if "required" in surface and not isinstance(surface.get("required"), bool):
            _error(errors, f"{label}.required 必须是布尔值")
        _validate_adapter(surface.get("source_adapter"), f"{label}.source_adapter", errors)
        _validate_adapter(surface.get("target_adapter"), f"{label}.target_adapter", errors)
        _compare(surface.get("compare"), f"{label}.compare", errors, schema_version)
        _evidence(surface.get("evidence", []), f"{label}.evidence", errors)
        confidence = surface.get("confidence", "low")
        if confidence not in CONFIDENCE_VALUES:
            _error(errors, f"{label}.confidence 不支持: {confidence}")
        if isinstance(surface_id, str):
            operations_by_surface[surface_id] = _operations(surface, label, errors, schema_version)

    _validate_checks(contract.get("checks", []), errors)
    corpus_reference = contract.get("parity_corpus")
    if corpus_reference is None:
        _error(errors, "parity_corpus 是必需字段")
    else:
        _relative_path(corpus_reference, "parity_corpus", errors)
    return surface_ids, operations_by_surface


def _validate_corpus(
    corpus: Any,
    surface_ids: set[str],
    operations_by_surface: dict[str, dict[str, bool]],
    contract_schema_version: int,
    errors: list[str],
) -> None:
    if not isinstance(corpus, dict):
        _error(errors, "parity-corpus.json 顶层必须是对象")
        return
    corpus_version = corpus.get("schema_version")
    if corpus_version not in CORPUS_SCHEMA_VERSIONS:
        _error(errors, "parity-corpus.json.schema_version 必须为 1 或 2")
        corpus_version = 1
    if contract_schema_version >= 2 and corpus_version != 2:
        _error(errors, "schema_version=2 的 Contract 必须配套 schema_version=2 的 Corpus")
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        _error(errors, "parity-corpus.json.cases 必须是数组")
        return
    seen: set[str] = set()
    required_cases_by_operation: dict[tuple[str, str], int] = {}
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            _error(errors, f"{label} 必须是对象")
            continue
        case_id = case.get("id")
        if _string(case_id, f"{label}.id", errors):
            if case_id in seen:
                _error(errors, f"parity corpus 包含重复 id: {case_id}")
            seen.add(case_id)
        surface_id = case.get("surface_id")
        if surface_id not in surface_ids:
            _error(errors, f"{label}.surface_id 未引用 public surface: {surface_id}")
        if "input" not in case:
            _error(errors, f"{label} 缺少 input")
        if "required" in case and not isinstance(case.get("required"), bool):
            _error(errors, f"{label}.required 必须是布尔值")
        forbidden = set(case) & FORBIDDEN_CORPUS_KEYS
        if forbidden:
            _error(errors, f"{label} 不应定义 Contract/比较结果字段: {sorted(forbidden)}")
        operation_id = case.get("operation_id")
        if contract_schema_version >= 2 or corpus_version >= 2:
            if not _string(operation_id, f"{label}.operation_id", errors):
                continue
            operations = operations_by_surface.get(surface_id, {})
            if operation_id not in operations:
                _error(errors, f"{label}.operation_id 未引用该 Surface 的 operation: {operation_id}")
            if case.get("required", True):
                key = (str(surface_id), operation_id)
                required_cases_by_operation[key] = required_cases_by_operation.get(key, 0) + 1

    if contract_schema_version >= 2:
        for surface, operations in operations_by_surface.items():
            for operation_id, required in operations.items():
                if required and required_cases_by_operation.get((surface, operation_id), 0) == 0:
                    _error(errors, f"required operation 缺少 required parity case: {surface}/{operation_id}")


def validate_documents(contract: Any, corpus: Any) -> list[str]:
    """Return all validation errors; an empty list means valid."""

    errors: list[str] = []
    surface_ids, operations_by_surface = _validate_contract(contract, errors)
    contract_version = contract.get("schema_version", 1) if isinstance(contract, dict) else 1
    _validate_corpus(corpus, surface_ids, operations_by_surface, contract_version, errors)
    return errors


def validate_files(contract_path: str | os.PathLike[str], corpus_path: str | os.PathLike[str]) -> tuple[Any, Any, list[str]]:
    try:
        contract = load_json(contract_path)
        corpus = load_json(corpus_path)
    except ConfigError as exc:
        return None, None, [str(exc)]
    return contract, corpus, validate_documents(contract, corpus)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Migration Skill contract and parity corpus")
    parser.add_argument("--contract", required=True, help="migration.json")
    parser.add_argument("--corpus", required=True, help="parity-corpus.json")
    parser.add_argument("--output", help="optional JSON validation report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract, corpus, errors = validate_files(args.contract, args.corpus)
    report = {
        "schema_version": 1,
        "status": "valid" if not errors else "invalid",
        "contract": str(Path(args.contract).resolve()),
        "corpus": str(Path(args.corpus).resolve()),
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
