"""Capture the source baseline before any migration edits are accepted."""

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
        checks_from_spec,
        git_revision,
        load_json,
        now_environment_summary,
        run_check,
        summarize_results,
        tree_digest,
        write_json,
    )
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        checks_from_spec,
        git_revision,
        load_json,
        now_environment_summary,
        run_check,
        summarize_results,
        tree_digest,
        write_json,
    )


def capture(root: Path, spec: Any, profile: str, output_limit: int = 20000) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    revision_before = git_revision(root)
    digest_before = tree_digest(root)
    checks = checks_from_spec(spec, profile)
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for check in checks:
        check_id = check.get("id")
        if check_id in seen:
            raise ConfigError(f"checks 包含重复 id: {check_id}")
        seen.add(check_id)
        results.append(run_check(root, check, {}, output_limit))
    digest_after = tree_digest(root)
    revision_after = git_revision(root)
    summary = summarize_results(results)
    inherited_failures = [
        result["id"] for result in results if result.get("status") != "passed"
    ]
    return {
        "schema_version": 1,
        "profile": profile,
        "root": str(root),
        "revision": revision_before,
        "revision_after_checks": revision_after,
        "tree_digest": digest_before,
        "tree_digest_after_checks": digest_after,
        "source_changed_during_baseline": digest_before != digest_after or revision_before != revision_after,
        "checks": results,
        "results": results,
        "summary": summary,
        "inherited_failures": inherited_failures,
        "runner": now_environment_summary(),
        "policy": "Existing failures are recorded as inherited; later evaluation checks only for new regressions.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a Migration Skill source baseline")
    parser.add_argument("--root", required=True, help="source repository root")
    parser.add_argument("--spec", required=True, help="migration.json or check-spec JSON")
    parser.add_argument("--output", required=True, help="baseline JSON output")
    parser.add_argument("--profile", choices=("source", "target"), default="source")
    parser.add_argument("--output-limit", type=int, default=20000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_limit <= 0:
        raise ConfigError("--output-limit 必须是正整数")
    spec = load_json(args.spec)
    report = capture(Path(args.root), spec, args.profile, args.output_limit)
    write_json(args.output, report)
    return EXIT_OK if report["summary"]["all_required_passed"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)

