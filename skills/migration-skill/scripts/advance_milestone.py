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
        sha256_file,
        tree_digest,
        write_json,
    )
    from validate_plan import validate_plan
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        git_revision,
        load_json,
        sha256_bytes,
        sha256_file,
        tree_digest,
        write_json,
    )
    from .validate_plan import validate_plan


def _result_digest(result: dict[str, Any]) -> str:
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def _milestone_present(items: list[Any], milestone_id: str) -> bool:
    return any(
        item == milestone_id
        or (isinstance(item, dict) and item.get("id", item.get("milestone_id")) == milestone_id)
        for item in items
    )


def _string_set(value: Any, label: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"{label} 必须是非空字符串数组")
    return set(value)


def _next_milestone(plan: dict[str, Any], completed: set[str]) -> str | None:
    milestones = plan.get("milestones", [])
    if not isinstance(milestones, list):
        return None
    for milestone in milestones:
        if isinstance(milestone, dict) and isinstance(milestone.get("id"), str) and milestone["id"] not in completed:
            return milestone["id"]
    return None


def advance(
    state_path: Path,
    result_path: Path,
    milestone_id: str,
    target_root: Path,
    *,
    expected_target_revision: str | None = None,
    expected_target_tree_digest: str | None = None,
    output_path: Path | None = None,
    plan_path: Path | None = None,
    manifest_path: Path | None = None,
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
    result_milestone_id = result.get("milestone_id")
    if result_milestone_id is not None and result_milestone_id != milestone_id:
        report = {
            "status": "rejected",
            "milestone_id": milestone_id,
            "reason": "milestone result id does not match requested milestone",
            "result_milestone_id": result_milestone_id,
        }
        if output_path:
            write_json(output_path, report)
        return report
    eligible = result.get("eligible") is True or result.get("ratchet_eligible") is True
    required_conditions = result.get("required_conditions", {})
    if not isinstance(required_conditions, dict):
        raise ConfigError("milestone result.required_conditions 必须是对象")
    if eligible and any(value is not True for value in required_conditions.values()):
        eligible = False
    proof_set = result.get("proof_set", {})
    if not isinstance(proof_set, dict):
        raise ConfigError("milestone result.proof_set 必须是对象")
    proof_cases = _string_set(proof_set.get("cases", []), "milestone result.proof_set.cases")
    proof_checks = _string_set(proof_set.get("checks", []), "milestone result.proof_set.checks")
    if not eligible:
        report = {
            "status": "rejected",
            "milestone_id": milestone_id,
            "reason": "milestone result is not eligible",
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

    reported_target = result.get("target", {})
    if isinstance(reported_target, dict):
        if "revision" in reported_target and reported_target.get("revision") != target_revision:
            raise ConfigError("milestone result 的 target revision 与实际状态不一致")
        if "tree_digest" in reported_target and reported_target.get("tree_digest") != target_digest:
            raise ConfigError("milestone result 的 target tree digest 与实际状态不一致")

    plan = None
    if plan_path is not None:
        plan = load_json(plan_path)
        if not isinstance(plan, dict):
            raise ConfigError("migration-plan.json 顶层必须是对象")
        plan_errors = validate_plan(plan)
        if plan_errors:
            raise ConfigError("Migration plan 无法接受 checkpoint:\n- " + "\n- ".join(plan_errors))
        milestones = {
            item.get("id"): item
            for item in plan.get("milestones", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        milestone = milestones.get(milestone_id)
        if milestone is None:
            raise ConfigError(f"migration-plan 不存在 milestone: {milestone_id}")
    else:
        milestone = None

    score = result.get("migration_score", 0.0)
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ConfigError("migration-result.migration_score 必须是数字")
    previous = state.get("last_accepted_checkpoint")
    if previous is not None and not isinstance(previous, dict):
        raise ConfigError("state.last_accepted_checkpoint 缺少可比较的 checkpoint 对象")
    previous_proof_cases = _string_set(state.get("protected_cases", []), "state.protected_cases")
    previous_proof_checks = _string_set(state.get("protected_checks", []), "state.protected_checks")
    if isinstance(previous, dict):
        previous_checkpoint_cases = previous.get("protected_cases")
        previous_checkpoint_checks = previous.get("protected_checks")
        if previous_checkpoint_cases is not None:
            previous_proof_cases |= _string_set(previous_checkpoint_cases, "checkpoint.protected_cases")
        if previous_checkpoint_checks is not None:
            previous_proof_checks |= _string_set(previous_checkpoint_checks, "checkpoint.protected_checks")
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

    if not previous_proof_cases.issubset(proof_cases) or not previous_proof_checks.issubset(proof_checks):
        report = {
            "status": "rejected",
            "milestone_id": milestone_id,
            "reason": "proof set regressed",
            "previous_proof_set": {
                "cases": sorted(previous_proof_cases),
                "checks": sorted(previous_proof_checks),
            },
            "current_proof_set": {"cases": sorted(proof_cases), "checks": sorted(proof_checks)},
        }
        if output_path:
            write_json(output_path, report)
        return report

    completed = state.get("completed_milestones", [])
    if not isinstance(completed, list):
        raise ConfigError("state.completed_milestones 必须是数组")
    completed_copy = list(completed)
    completed_ids = _string_set(completed_copy, "state.completed_milestones")
    if milestone is not None:
        dependencies = milestone.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ConfigError("milestone.depends_on 必须是字符串数组")
        if not set(dependencies).issubset(completed_ids):
            report = {
                "status": "rejected",
                "milestone_id": milestone_id,
                "reason": "milestone dependencies are not accepted",
                "missing_dependencies": sorted(set(dependencies) - completed_ids),
            }
            if output_path:
                write_json(output_path, report)
            return report
    if not _milestone_present(completed_copy, milestone_id):
        completed_copy.append(milestone_id)
    accepted_proof_cases = sorted(proof_cases)
    accepted_proof_checks = sorted(proof_checks)
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
        "protected_cases": accepted_proof_cases,
        "protected_checks": accepted_proof_checks,
    }
    next_state = dict(state)
    next_state["completed_milestones"] = completed_copy
    next_state["schema_version"] = 2
    next_state["protected_cases"] = accepted_proof_cases
    next_state["protected_checks"] = accepted_proof_checks
    next_state["last_accepted_checkpoint"] = checkpoint
    next_state["last_result_digest"] = checkpoint["result_digest"]
    next_state["verification_score"] = checkpoint["verification_score"]
    if result.get("plan_digest") is not None:
        next_state["plan_digest"] = result["plan_digest"]
    if manifest_path is not None:
        next_state["freeze_manifest_sha256"] = sha256_file(manifest_path)
        checkpoint["freeze_manifest_sha256"] = next_state["freeze_manifest_sha256"]
    if plan is not None:
        next_state["current_milestone"] = _next_milestone(plan, set(completed_copy))
    write_json(state_path, next_state)
    report = {
        "status": "accepted",
        "milestone_id": milestone_id,
        "checkpoint": checkpoint,
        "proof_set": {"cases": accepted_proof_cases, "checks": accepted_proof_checks},
    }
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
    parser.add_argument("--plan", help="optional migration-plan.json")
    parser.add_argument("--manifest", help="optional freeze-manifest.json for checkpoint provenance")
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
        plan_path=Path(args.plan) if args.plan else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
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
