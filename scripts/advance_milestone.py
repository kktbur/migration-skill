"""Atomically accept a verified migration milestone checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        git_revision,
        load_json,
        sha256_bytes,
        tree_digest,
        write_json,
    )
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        git_revision,
        load_json,
        sha256_bytes,
        tree_digest,
        write_json,
    )


def _result_digest(result: dict[str, Any]) -> str:
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def _milestone_present(items: list[Any], milestone_id: str) -> bool:
    return any(
        item == milestone_id
        or (isinstance(item, dict) and item.get("id", item.get("milestone_id")) == milestone_id)
        for item in items
    )


def advance(
    state_path: Path,
    result_path: Path,
    milestone_id: str,
    target_root: Path,
    *,
    expected_target_revision: str | None = None,
    expected_target_tree_digest: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    state_path = state_path.resolve()
    result_path = result_path.resolve()
    target_root = target_root.resolve()
    state = load_json(state_path)
    result = load_json(result_path)
    if not isinstance(state, dict):
        raise ConfigError("state.json 顶层必须是对象")
    if not isinstance(result, dict):
        raise ConfigError("migration-result.json 顶层必须是对象")
    if not isinstance(milestone_id, str) or not milestone_id or "\x00" in milestone_id:
        raise ConfigError("milestone_id 必须是非空字符串")
    if not target_root.exists() or not target_root.is_dir():
        raise ConfigError(f"target root 不存在或不是目录: {target_root}")
    if result.get("ratchet_eligible") is not True:
        report = {
            "status": "rejected",
            "milestone_id": milestone_id,
            "reason": "migration result is not ratchet eligible",
            "result_status": result.get("status"),
        }
        if output_path:
            write_json(output_path, report)
        return report

    target_revision = git_revision(target_root)
    target_digest = tree_digest(target_root)
    if expected_target_revision is not None and target_revision != expected_target_revision:
        raise ConfigError("target revision 与实际状态不一致")
    if expected_target_tree_digest is not None and target_digest != expected_target_tree_digest:
        raise ConfigError("target tree digest 与实际状态不一致")

    score = result.get("migration_score", 0.0)
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ConfigError("migration-result.migration_score 必须是数字")
    previous = state.get("last_accepted_checkpoint")
    if previous is not None and not isinstance(previous, dict):
        raise ConfigError("state.last_accepted_checkpoint 缺少可比较的 checkpoint 对象")
    if isinstance(previous, dict):
        previous_score = previous.get("verification_score", 0.0)
        if not isinstance(previous_score, (int, float)) or isinstance(previous_score, bool):
            raise ConfigError("旧 checkpoint.verification_score 无效")
        if score < previous_score:
            report = {
                "status": "rejected",
                "milestone_id": milestone_id,
                "reason": "verification score regressed",
                "previous_score": previous_score,
                "current_score": score,
            }
            if output_path:
                write_json(output_path, report)
            return report
        if previous.get("milestone_id") == milestone_id:
            if previous.get("result_digest") == _result_digest(result) and previous.get("target_tree_digest") == target_digest:
                report = {"status": "already_accepted", "milestone_id": milestone_id, "checkpoint": previous}
                if output_path:
                    write_json(output_path, report)
                return report
            report = {
                "status": "rejected",
                "milestone_id": milestone_id,
                "reason": "milestone already has a different accepted checkpoint",
            }
            if output_path:
                write_json(output_path, report)
            return report

    completed = state.get("completed_milestones", [])
    if not isinstance(completed, list):
        raise ConfigError("state.completed_milestones 必须是数组")
    completed_copy = list(completed)
    if not _milestone_present(completed_copy, milestone_id):
        completed_copy.append(milestone_id)
    checkpoint = {
        "id": f"checkpoint-{milestone_id}",
        "milestone_id": milestone_id,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "result_digest": _result_digest(result),
        "target_root": str(target_root),
        "target_revision": target_revision,
        "target_tree_digest": target_digest,
        "verification_score": float(score),
        "result_status": result.get("status"),
    }
    next_state = dict(state)
    next_state["completed_milestones"] = completed_copy
    next_state["last_accepted_checkpoint"] = checkpoint
    next_state["last_result_digest"] = checkpoint["result_digest"]
    next_state["verification_score"] = checkpoint["verification_score"]
    write_json(state_path, next_state)
    report = {"status": "accepted", "milestone_id": milestone_id, "checkpoint": checkpoint}
    if output_path:
        write_json(output_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Advance a Migration Skill milestone checkpoint")
    parser.add_argument("--state", required=True, help="state.json")
    parser.add_argument("--result", required=True, help="migration-result.json")
    parser.add_argument("--milestone-id", required=True, help="bounded milestone ID")
    parser.add_argument("--target-root", required=True, help="target repository root")
    parser.add_argument("--target-revision", help="optional expected target Git revision")
    parser.add_argument("--target-tree-digest", help="optional expected target tree digest")
    parser.add_argument("--output", help="optional checkpoint result JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = advance(
        Path(args.state),
        Path(args.result),
        args.milestone_id,
        Path(args.target_root),
        expected_target_revision=args.target_revision,
        expected_target_tree_digest=args.target_tree_digest,
        output_path=Path(args.output) if args.output else None,
    )
    if not args.output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_OK if report["status"] in {"accepted", "already_accepted"} else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
