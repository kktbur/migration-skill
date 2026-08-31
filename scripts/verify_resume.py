"""Verify the last accepted target checkpoint before a new edit begins."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

try:
    from common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        FrozenStateError,
        canonical_path,
        git_revision,
        load_json,
        sha256_file,
        tree_digest,
        verify_freeze,
        write_json,
    )
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_FAILED,
        EXIT_INVALID,
        EXIT_OK,
        FrozenStateError,
        canonical_path,
        git_revision,
        load_json,
        sha256_file,
        tree_digest,
        verify_freeze,
        write_json,
    )


def _invalid(reason: str, **details: Any) -> dict[str, Any]:
    return {"schema_version": 1, "status": "invalidated", "valid": False, "reason": reason, **details}


def verify_resume(
    state_path: Path,
    target_root: Path,
    manifest_path: Path,
    output_path: Path,
    *,
    workspace_root: Path | None = None,
    freeze_checker: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return whether it is safe to start editing the target again.

    ``freeze_checker`` is an offline seam for callers that already verified a
    manifest. The command-line path always uses the real freeze verifier.
    """

    state_path = canonical_path(state_path)
    target_root = canonical_path(target_root)
    manifest_path = canonical_path(manifest_path)
    state = load_json(state_path)
    if not isinstance(state, dict):
        raise ConfigError("state.json 顶层必须是对象")
    if state.get("schema_version") != 2:
        report = _invalid("unsupported-state-schema", state_schema_version=state.get("schema_version"))
        write_json(output_path, report)
        return report
    if not target_root.exists() or not target_root.is_dir():
        report = _invalid("target-root-missing", target_root=str(target_root))
        write_json(output_path, report)
        return report

    try:
        freeze = (
            freeze_checker(manifest_path)
            if freeze_checker is not None
            else verify_freeze(manifest_path, workspace_root=workspace_root)
        )
    except FrozenStateError as exc:
        report = _invalid("freeze-invalid", error=str(exc), freeze_intact=False)
        write_json(output_path, report)
        return report
    if not isinstance(freeze, dict) or freeze.get("intact") is not True:
        report = _invalid("freeze-invalid", freeze_intact=False)
        write_json(output_path, report)
        return report

    manifest = freeze.get("manifest", {})
    source = manifest.get("source", {}) if isinstance(manifest, dict) else {}
    if state.get("source_revision") is not None and state.get("source_revision") != source.get("revision"):
        report = _invalid(
            "source-revision-mismatch",
            expected_source_revision=source.get("revision"),
            actual_state_source_revision=state.get("source_revision"),
            freeze_intact=True,
        )
        write_json(output_path, report)
        return report

    checkpoint = state.get("last_accepted_checkpoint")
    if checkpoint is None:
        report = {
            "schema_version": 1,
            "status": "not_started",
            "valid": True,
            "freeze_intact": True,
            "checkpoint": None,
            "target_root": str(target_root),
        }
        write_json(output_path, report)
        return report
    if not isinstance(checkpoint, dict):
        report = _invalid("checkpoint-is-not-object", freeze_intact=True)
        write_json(output_path, report)
        return report

    expected_digest = checkpoint.get("target_tree_digest")
    expected_revision = checkpoint.get("target_revision")
    if not isinstance(expected_digest, str) or not expected_digest:
        report = _invalid("checkpoint-missing-target-digest", checkpoint=checkpoint, freeze_intact=True)
        write_json(output_path, report)
        return report
    actual_digest = tree_digest(target_root)
    actual_revision = git_revision(target_root)
    digest_matches = actual_digest == expected_digest
    revision_matches = actual_revision == expected_revision
    manifest_digest = checkpoint.get("freeze_manifest_sha256")
    manifest_matches = manifest_digest is None or manifest_digest == sha256_file(manifest_path)
    valid = digest_matches and revision_matches and manifest_matches
    report = {
        "schema_version": 1,
        "status": "ready" if valid else "invalidated",
        "valid": valid,
        "freeze_intact": True,
        "checkpoint": checkpoint,
        "last_accepted_milestone": checkpoint.get("milestone_id"),
        "target_root": str(target_root),
        "expected_target_tree_digest": expected_digest,
        "actual_target_tree_digest": actual_digest,
        "target_tree_digest_matches": digest_matches,
        "expected_target_revision": expected_revision,
        "actual_target_revision": actual_revision,
        "target_revision_matches": revision_matches,
        "expected_freeze_manifest_sha256": manifest_digest,
        "actual_freeze_manifest_sha256": sha256_file(manifest_path),
        "freeze_manifest_matches": manifest_matches,
    }
    if not valid:
        report["reason"] = "target-or-freeze-changed"
    write_json(output_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the pre-edit Migration Skill resume gate")
    parser.add_argument("--state", required=True, help="state.json")
    parser.add_argument("--target-root", required=True, help="target repository root")
    parser.add_argument("--manifest", required=True, help="freeze-manifest.json")
    parser.add_argument("--output", required=True, help="resume preflight result JSON")
    parser.add_argument("--workspace-root", help="relocation workspace root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_resume(
        Path(args.state),
        Path(args.target_root),
        Path(args.manifest),
        Path(args.output),
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
    )
    return EXIT_OK if report["valid"] else EXIT_FAILED


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
