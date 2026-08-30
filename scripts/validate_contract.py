"""Validate the JSON Behavior Contract and its separate parity corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    from common import ConfigError, EXIT_INVALID, EXIT_OK, load_json, write_json
except ImportError:  # pragma: no cover - useful when imported as a package
    from .common import ConfigError, EXIT_INVALID, EXIT_OK, load_json, write_json


SURFACE_KINDS = {"command", "http", "library", "snapshot", "file-io"}
COMPARE_MODES = {"exact", "text", "text-normalized", "json-semantic", "exit-code", "snapshot"}
NORMALIZATION_RULES = {"crlf-to-lf", "trim-trailing-whitespace"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
FORBIDDEN_CORPUS_KEYS = {"expected", "compare", "normalization", "behavior_contract"}


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


def _validate_adapter(adapter: Any, label: str, errors: list[str]) -> None:
    if not isinstance(adapter, dict):
        _error(errors, f"{label} 必须是对象")
        return
    _string(adapter.get("kind", "harness"), f"{label}.kind", errors)
    _argv(adapter.get("argv"), f"{label}.argv", errors)
    if "shell" in adapter and adapter.get("shell") is not False:
        _error(errors, f"{label}.shell 必须为 false；Migration Skill 不执行 shell 字符串")


def _mode(value: Any, label: str, errors: list[str]) -> None:
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
        normalization = value.get("normalization")
        if normalization is not None:
            _normalization(normalization, f"{label}.normalization", errors)
        return
    _error(errors, f"{label} 必须是 true、比较模式字符串或比较配置对象")


def _normalization(value: Any, label: str, errors: list[str]) -> None:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        _error(errors, f"{label} 必须是字符串或字符串数组")
        return
    for item in values:
        if item not in NORMALIZATION_RULES:
            _error(errors, f"{label} 不支持的规则: {item}")


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
    env = check.get("env")
    if env is not None:
        if not isinstance(env, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in env.items()
        ):
            _error(errors, f"{label}.env 必须是字符串到字符串的对象")
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


def _validate_contract(contract: Any, errors: list[str]) -> None:
    if not isinstance(contract, dict):
        _error(errors, "migration.json 顶层必须是对象")
        return
    if contract.get("schema_version") != 1:
        _error(errors, "migration.json.schema_version 必须为 1")
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

    surfaces = contract.get("public_surfaces")
    surface_ids: set[str] = set()
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
        compare = surface.get("compare")
        if not isinstance(compare, dict) or not compare:
            _error(errors, f"{label}.compare 必须是非空对象")
        else:
            for field, comparator in compare.items():
                _string(field, f"{label}.compare field", errors)
                _mode(comparator, f"{label}.compare.{field}", errors)
        evidence = surface.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
            _error(errors, f"{label}.evidence 必须是字符串数组")
        else:
            for item_index, item in enumerate(evidence):
                _relative_path(item, f"{label}.evidence[{item_index}]", errors)
        confidence = surface.get("confidence", "low")
        if confidence not in CONFIDENCE_VALUES:
            _error(errors, f"{label}.confidence 不支持: {confidence}")

    _validate_checks(contract.get("checks", []), errors)
    corpus_reference = contract.get("parity_corpus")
    if corpus_reference is not None:
        _relative_path(corpus_reference, "parity_corpus", errors)


def _validate_corpus(corpus: Any, surface_ids: set[str], errors: list[str]) -> None:
    if not isinstance(corpus, dict):
        _error(errors, "parity-corpus.json 顶层必须是对象")
        return
    if corpus.get("schema_version") != 1:
        _error(errors, "parity-corpus.json.schema_version 必须为 1")
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        _error(errors, "parity-corpus.json.cases 必须是数组")
        return
    seen: set[str] = set()
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


def validate_documents(contract: Any, corpus: Any) -> list[str]:
    """Return all validation errors; an empty list means valid."""

    errors: list[str] = []
    _validate_contract(contract, errors)
    surfaces = contract.get("public_surfaces", []) if isinstance(contract, dict) else []
    surface_ids = {
        surface.get("id")
        for surface in surfaces
        if isinstance(surface, dict) and isinstance(surface.get("id"), str)
    }
    _validate_corpus(corpus, surface_ids, errors)
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
