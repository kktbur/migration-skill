"""Freeze source evidence and the complete deterministic verifier bundle."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        FREEZE_SCHEMA_VERSION,
        TOOL_VERSION,
        _bundle_files,
        canonical_path,
        git_revision,
        sha256_bytes,
        sha256_file,
        tree_digest,
        load_json,
        relative_posix_path,
        relative_reference_path,
        write_json,
    )
    from validate_contract import validate_files
    from validate_judge import validate_artifact, validate_judge
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        FREEZE_SCHEMA_VERSION,
        TOOL_VERSION,
        _bundle_files,
        canonical_path,
        git_revision,
        sha256_bytes,
        sha256_file,
        tree_digest,
        load_json,
        relative_posix_path,
        relative_reference_path,
        write_json,
    )
    from .validate_contract import validate_files
    from .validate_judge import validate_artifact, validate_judge


def _required_file(path_value: str, label: str) -> Path:
    path = Path(path_value).resolve()
    if not path.exists() or not path.is_file():
        raise ConfigError(f"{label} 不存在或不是文件: {path}")
    return path


def _file_entry(path: Path, workspace_root: Path | None = None) -> dict[str, str]:
    return {
        "path": relative_posix_path(path, workspace_root) if workspace_root is not None else str(path),
        "sha256": sha256_file(path),
    }


def _bundle_entries(root: Path, workspace_root: Path | None = None) -> dict[str, dict[str, str]]:
    paths = _bundle_files(root)
    return {label: _file_entry(path, workspace_root) for label, path in paths.items()}


def _workspace_root(
    explicit: Path | None,
    output_path: Path,
    root: Path,
    contract_path: Path,
    corpus_path: Path,
    evaluator_path: Path,
    judge_path: Path,
    verifier_root: Path,
) -> Path:
    if explicit is not None:
        workspace = explicit.resolve()
    else:
        candidates = [
            root,
            contract_path,
            corpus_path,
            evaluator_path,
            judge_path,
            verifier_root,
            output_path.parent.resolve(),
        ]
        try:
            import os

            workspace = Path(os.path.commonpath([str(item) for item in candidates])).resolve()
        except ValueError as exc:
            raise ConfigError("无法推导统一 workspace root；请显式提供 --workspace-root") from exc
    if not workspace.exists() or not workspace.is_dir():
        raise ConfigError(f"workspace root 不存在或不是目录: {workspace}")
    return workspace


def _revalidate_judge_artifact(
    artifact: dict[str, Any],
    source_root: Path,
    source_revision: str | None,
    artifact_path: Path | None = None,
) -> None:
    """Recompute the Judge artifact so a forged pair of flags cannot freeze."""

    artifact_path_value = artifact.get("artifact_path")
    if artifact_path is None and isinstance(artifact_path_value, str):
        artifact_path = canonical_path(artifact_path_value)

    def artifact_file_path(value: str, label: str) -> Path:
        if artifact.get("path_mode") == "relative":
            workspace_value = artifact.get("workspace_root", ".")
            if artifact_path is None or not isinstance(workspace_value, str) or Path(value).is_absolute():
                raise ConfigError(f"{label} 的 portable path 无效")
            workspace = (artifact_path.parent / workspace_value).resolve()
            return _required_file(str((workspace / value).resolve()), label)
        return _required_file(value, label)

    positive_path = artifact_file_path(artifact["positive_result_path"], "judge positive result")
    mutation_plan_path = artifact_file_path(artifact["mutation_plan_path"], "mutation plan")
    workspace_root = None
    if artifact.get("path_mode") == "relative":
        workspace_value = artifact.get("workspace_root")
        if artifact_path is None or not isinstance(workspace_value, str):
            raise ConfigError("portable judge-validation 缺少 workspace root")
        workspace_root = (artifact_path.parent / workspace_value).resolve()
    if sha256_file(positive_path) != artifact["positive_result_sha256"]:
        raise ConfigError("judge-validation positive result 摘要不匹配")
    if sha256_file(mutation_plan_path) != artifact["mutation_plan_sha256"]:
        raise ConfigError("judge-validation mutation plan 摘要不匹配")
    with tempfile.TemporaryDirectory(prefix="migration-judge-") as temporary:
        recomputed_path = Path(temporary) / "judge-validation.json"
        recomputed = validate_judge(
            positive_path,
            mutation_plan_path,
            recomputed_path,
            source_revision=source_revision,
            source_root=source_root,
            workspace_root=workspace_root,
            artifact_base=artifact_path.parent if artifact_path is not None else None,
        )
    if recomputed != artifact:
        raise ConfigError("judge-validation 不是由当前 positive result/mutation plan 重新验证得到的 artifact")


def freeze(
    root: Path,
    contract_path: Path,
    corpus_path: Path,
    evaluator_path: Path,
    output_path: Path,
    judge_validation_path: Path | None = None,
    verifier_root: Path | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    contract_path = _required_file(str(contract_path), "contract")
    corpus_path = _required_file(str(corpus_path), "corpus")
    evaluator_path = _required_file(str(evaluator_path), "evaluator")
    if judge_validation_path is None:
        raise ConfigError("v2 freeze 必须提供 validate_judge.py 生成的 judge-validation artifact")
    judge_validation_path = _required_file(str(judge_validation_path), "judge-validation")
    judge_validation = load_json(judge_validation_path)
    judge_errors = validate_artifact(judge_validation)
    if judge_errors:
        raise ConfigError("judge-validation 无效:\n- " + "\n- ".join(judge_errors))

    contract, corpus, errors = validate_files(contract_path, corpus_path)
    if errors:
        raise ConfigError("Contract/Corpus 无法冻结:\n- " + "\n- ".join(errors))
    actual_revision = git_revision(root)
    actual_tree_digest = tree_digest(root)
    if judge_validation.get("source_revision") != actual_revision:
        raise ConfigError("judge-validation 的 source_revision 与当前 Source 不一致")
    if judge_validation.get("source_tree_digest") != actual_tree_digest:
        raise ConfigError("judge-validation 的 source_tree_digest 与当前 Source 不一致")
    _revalidate_judge_artifact(judge_validation, root, actual_revision, judge_validation_path)

    bundle_root = (verifier_root or evaluator_path.parent).resolve()
    output_path = output_path.resolve()
    workspace = _workspace_root(
        workspace_root.resolve() if workspace_root is not None else None,
        output_path,
        root,
        contract_path,
        corpus_path,
        evaluator_path,
        judge_validation_path,
        bundle_root,
    )
    bundle_files = _bundle_entries(bundle_root, workspace)
    if relative_posix_path(evaluator_path, workspace) not in {entry["path"] for entry in bundle_files.values()}:
        raise ConfigError("evaluator 必须属于 verifier bundle")
    if not all(
        relative_posix_path(path, workspace) == path.relative_to(workspace).as_posix()
        for path in (root, contract_path, corpus_path, evaluator_path, judge_validation_path, bundle_root)
    ):
        raise ConfigError("冻结资产必须位于 workspace root 内")
    files = {
        "contract": _file_entry(contract_path, workspace),
        "corpus": _file_entry(corpus_path, workspace),
        "evaluator": _file_entry(evaluator_path, workspace),
        "judge_validation": _file_entry(judge_validation_path, workspace),
    }
    checks = contract.get("checks", []) if isinstance(contract, dict) else []
    check_specification = {
        "checks": checks,
        "environment": contract.get("environment", {}) if isinstance(contract, dict) else {},
        "completion_gates": contract.get("completion_gates", {}) if isinstance(contract, dict) else {},
    }
    normalization_policy = {
        "surface_comparators": {
            surface["id"]: surface.get("compare", {})
            for surface in contract.get("public_surfaces", [])
            if isinstance(surface, dict) and isinstance(surface.get("id"), str)
        },
        "contract_normalization": contract.get("normalization_policy", {}),
    }
    check_specification_digest = sha256_bytes(
        json.dumps(check_specification, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    manifest = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "path_mode": "relative",
        "portable": True,
        "workspace_root": relative_reference_path(workspace, output_path.parent),
        "tool_version": TOOL_VERSION,
        "source": {
            "root": relative_posix_path(root, workspace),
            "revision": actual_revision,
            "tree_digest": actual_tree_digest,
        },
        "files": files,
        "verifier_bundle": {
            "root": relative_posix_path(bundle_root, workspace),
            "tool_version": TOOL_VERSION,
            "files": bundle_files,
        },
        "normalization_policy": normalization_policy,
        "check_specification": check_specification,
        "check_specification_digest": check_specification_digest,
        "judge_validation": {
            "artifact_type": judge_validation.get("artifact_type"),
            "valid": judge_validation.get("valid"),
            "source_revision": judge_validation.get("source_revision"),
        },
        "policy": {
            "source_revision_change": "invalidate-and-rebuild-evidence",
            "required_case_removal": "forbidden-without-explicit-reapproval",
            "required_operation_removal": "forbidden-without-explicit-reapproval",
            "evaluator_change": "invalidate-and-rebuild-evidence",
            "verifier_bundle_change": "invalidate-and-rebuild-evidence",
        },
    }
    write_json(output_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze Migration Skill evidence and verifier bundle")
    parser.add_argument("--root", required=True, help="source repository root")
    parser.add_argument("--contract", required=True, help="migration.json")
    parser.add_argument("--corpus", required=True, help="parity-corpus.json")
    parser.add_argument("--evaluator", required=True, help="evaluator script")
    parser.add_argument("--output", required=True, help="freeze-manifest.json")
    parser.add_argument("--judge-validation", required=True, help="validate_judge.py artifact")
    parser.add_argument("--verifier-root", help="directory whose Python files form the frozen verifier bundle")
    parser.add_argument("--workspace-root", help="root used for portable relative manifest paths")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    freeze(
        Path(args.root),
        Path(args.contract),
        Path(args.corpus),
        Path(args.evaluator),
        Path(args.output),
        Path(args.judge_validation),
        Path(args.verifier_root) if args.verifier_root else None,
        Path(args.workspace_root) if args.workspace_root else None,
    )
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
