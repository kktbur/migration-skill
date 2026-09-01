"""Run the portable Source/Target parity adapter protocol."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        _merge_environment_specs,
        _safe_env,
        cap_text,
        expand_argv,
        load_json,
        redact_text,
        resolve_cwd,
        validate_argv,
        validate_variable_name,
        write_json,
    )
    from validate_contract import validate_documents
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        _merge_environment_specs,
        _safe_env,
        cap_text,
        expand_argv,
        load_json,
        redact_text,
        resolve_cwd,
        validate_argv,
        validate_variable_name,
        write_json,
    )
    from .validate_contract import validate_documents


def _variables(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise ConfigError(f"--var 必须使用 KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        if "\x00" in key or "\x00" in value:
            raise ConfigError(f"--var 的 KEY/VALUE 无效: {item}")
        validate_variable_name(key, "--var")
        if key in result:
            raise ConfigError(f"--var 重复: {key}")
        result[key] = value
    return result


def _surface_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        surface["id"]: surface
        for surface in contract.get("public_surfaces", [])
        if isinstance(surface, dict) and isinstance(surface.get("id"), str)
    }


def _adapter_result(stdout: str) -> tuple[str, Any, str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return "failed", None, "invalid-adapter-json"
    if not isinstance(document, dict):
        return "failed", None, "adapter-output-must-be-object"
    status = document.get("status")
    if status != "passed":
        return "failed", document.get("observed"), "adapter-status-not-passed"
    if "observed" not in document:
        return "failed", None, "adapter-output-missing-observed"
    return "passed", document["observed"], None


def _run_case(
    root: Path,
    contract: dict[str, Any],
    case: dict[str, Any],
    profile: str,
    variables: dict[str, str],
    output_limit: int,
) -> dict[str, Any]:
    surface_id = case.get("surface_id")
    surfaces = _surface_map(contract)
    surface = surfaces.get(surface_id)
    if surface is None:
        raise ConfigError(f"case 引用了未知 surface: {surface_id}")
    adapter_key = f"{profile}_adapter"
    adapter = surface.get(adapter_key)
    if not isinstance(adapter, dict):
        raise ConfigError(f"surface 缺少 {adapter_key}: {surface_id}")
    argv = expand_argv(validate_argv(adapter.get("argv"), f"{surface_id}.{adapter_key}.argv"), variables)
    cwd = resolve_cwd(root, adapter.get("cwd"))
    timeout_seconds = adapter.get("timeout_seconds", case.get("timeout_seconds", 60))
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ConfigError(f"{surface_id}.{adapter_key}.timeout_seconds 必须是正数")
    environment = _safe_env(
        _merge_environment_specs(
            contract.get("environment") if isinstance(contract, dict) else None,
            adapter.get("environment"),
        ),
        variables,
    )
    request = {
        "case_id": case["id"],
        "surface_id": surface_id,
        "operation_id": case.get("operation_id"),
        "input": case.get("input"),
    }
    # Keep the wire payload ASCII-safe. The decoded JSON value remains Unicode,
    # while ASCII JSON avoids locale-dependent stdin decoding in child
    # interpreters on Windows.
    payload = json.dumps(request, ensure_ascii=True, sort_keys=True) + "\n"
    started = time.perf_counter()
    status = "failed"
    exit_code: int | None = None
    timed_out = False
    stdout_value = ""
    stderr_value = ""
    observed: Any = None
    reason: str | None = None
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=environment,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            shell=False,
            check=False,
        )
        exit_code = completed.returncode
        stdout_value = completed.stdout or ""
        stderr_value = completed.stderr or ""
        if exit_code != 0:
            reason = "adapter-exit-code"
        else:
            status, observed, reason = _adapter_result(stdout_value)
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        timed_out = True
        reason = "timeout"
        stdout_value = exc.stdout or ""
        stderr_value = exc.stderr or ""
    except FileNotFoundError as exc:
        reason = "command-not-found"
        stderr_value = str(exc)
    except OSError as exc:
        reason = "execution-error"
        stderr_value = str(exc)
    duration = time.perf_counter() - started
    stdout_value, stdout_truncated = cap_text(stdout_value, output_limit)
    stderr_value, stderr_truncated = cap_text(stderr_value, output_limit)
    result: dict[str, Any] = {
        "id": case["id"],
        "surface_id": surface_id,
        "operation_id": case.get("operation_id"),
        "required": case.get("required", True),
        "status": status,
        "observed": observed,
        "adapter_exit_code": exit_code,
        "argv": [redact_text(item) for item in argv],
        "cwd": str(cwd),
        "timeout": timed_out,
        "stdout": redact_text(stdout_value),
        "stderr": redact_text(stderr_value),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "duration_seconds": round(duration, 6),
    }
    if reason:
        result["reason"] = reason
    return result


def _summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    required_failed = [item["id"] for item in cases if item.get("required", True) and item.get("status") != "passed"]
    return {
        "total": len(cases),
        "passed": sum(1 for item in cases if item.get("status") == "passed"),
        "failed": sum(1 for item in cases if item.get("status") == "failed"),
        "timed_out": sum(1 for item in cases if item.get("status") == "timeout"),
        "required_failed": sorted(required_failed),
        "all_required_passed": not required_failed,
    }


def run_parity(
    root: Path,
    contract: dict[str, Any],
    corpus: dict[str, Any],
    profile: str,
    variables: dict[str, str] | None = None,
    output_limit: int = 20000,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    errors = validate_documents(contract, corpus)
    if errors:
        raise ConfigError("Contract/Corpus 无法执行 parity:\n- " + "\n- ".join(errors))
    cases = corpus.get("cases", [])
    if not isinstance(cases, list):
        raise ConfigError("parity corpus cases 必须是数组")
    variables = variables or {}
    results = [_run_case(root, contract, case, profile, variables, output_limit) for case in cases]
    summary = _summary(results)
    return {
        "schema_version": 2,
        "profile": profile,
        "root": str(root),
        "cases": results,
        "summary": summary,
        "status": "passed" if summary["all_required_passed"] else "failed",
        "adapter_protocol": "stdin-case-json-v1",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Migration Skill parity adapters")
    parser.add_argument("--root", required=True, help="source or target execution root")
    parser.add_argument("--contract", required=True, help="migration.json")
    parser.add_argument("--corpus", required=True, help="parity-corpus.json")
    parser.add_argument("--profile", choices=("source", "target"), required=True)
    parser.add_argument("--output", required=True, help="parity result JSON")
    parser.add_argument("--var", action="append", help="explicit adapter variable KEY=VALUE")
    parser.add_argument("--output-limit", type=int, default=20000, help="per-stream capture limit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_limit <= 0:
        raise ConfigError("--output-limit 必须是正整数")
    contract = load_json(args.contract)
    corpus = load_json(args.corpus)
    report = run_parity(
        Path(args.root),
        contract,
        corpus,
        args.profile,
        _variables(args.var),
        args.output_limit,
    )
    write_json(args.output, report)
    return EXIT_OK if report["summary"]["all_required_passed"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
