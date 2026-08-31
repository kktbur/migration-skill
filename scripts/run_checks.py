"""Run explicit check commands using argv arrays and ``shell=False``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        checks_from_spec,
        load_json,
        now_environment_summary,
        run_check,
        summarize_results,
        validate_variable_name,
        write_json,
    )
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        checks_from_spec,
        load_json,
        now_environment_summary,
        run_check,
        summarize_results,
        validate_variable_name,
        write_json,
    )


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


def run_checks(root: Path, spec: Any, profile: str, variables: dict[str, str], output_limit: int) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    checks = checks_from_spec(spec, profile)
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for check in checks:
        check_id = check.get("id")
        if check_id in seen:
            raise ConfigError(f"选中的 checks 包含重复 id: {check_id}")
        seen.add(check_id)
        results.append(
            run_check(
                root,
                check,
                variables,
                output_limit,
                spec.get("environment") if isinstance(spec, dict) else None,
            )
        )
    summary = summarize_results(results)
    return {
        "schema_version": 1,
        "profile": profile,
        "root": str(root),
        "results": results,
        "summary": summary,
        "runner": now_environment_summary(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Migration Skill checks")
    parser.add_argument("--root", required=True, help="execution root")
    parser.add_argument("--spec", required=True, help="migration.json or check-spec JSON")
    parser.add_argument("--output", required=True, help="result JSON output")
    parser.add_argument("--profile", choices=("source", "target"), default="source")
    parser.add_argument("--var", action="append", help="explicit command variable KEY=VALUE")
    parser.add_argument("--output-limit", type=int, default=20000, help="per-stream capture limit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_limit <= 0:
        raise ConfigError("--output-limit 必须是正整数")
    spec = load_json(args.spec)
    report = run_checks(Path(args.root), spec, args.profile, _variables(args.var), args.output_limit)
    write_json(args.output, report)
    return EXIT_OK if report["summary"]["all_required_passed"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
