"""Freeze source evidence and all deterministic parity assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        SCHEMA_VERSION,
        TOOL_VERSION,
        git_revision,
        sha256_bytes,
        sha256_file,
        tree_digest,
        load_json,
        write_json,
    )
    from validate_contract import validate_files
except ImportError:  # pragma: no cover
    from .common import (
        ConfigError,
        EXIT_INVALID,
        EXIT_OK,
        SCHEMA_VERSION,
        TOOL_VERSION,
        git_revision,
        sha256_bytes,
        sha256_file,
        tree_digest,
        load_json,
        write_json,
    )
    from .validate_contract import validate_files


def _required_file(path_value: str, label: str) -> Path:
    path = Path(path_value).resolve()
    if not path.exists() or not path.is_file():
        raise ConfigError(f"{label} 不存在或不是文件: {path}")
    return path


def _file_entry(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def freeze(
    root: Path,
    contract_path: Path,
    corpus_path: Path,
    evaluator_path: Path,
    output_path: Path,
    judge_validation_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    contract_path = _required_file(str(contract_path), "contract")
    corpus_path = _required_file(str(corpus_path), "corpus")
    evaluator_path = _required_file(str(evaluator_path), "evaluator")
    if judge_validation_path is not None:
        judge_validation_path = _required_file(str(judge_validation_path), "judge-validation")
        judge_validation = load_json(judge_validation_path)
        if not isinstance(judge_validation, dict) or not (
            judge_validation.get("positive_control") is True
            and judge_validation.get("negative_control") is True
        ):
            raise ConfigError("judge-validation 必须证明 positive_control 和 negative_control 均为 true")
    contract, corpus, errors = validate_files(contract_path, corpus_path)
    if errors:
        raise ConfigError("Contract/Corpus 无法冻结:\n- " + "\n- ".join(errors))
    files = {
        "contract": _file_entry(contract_path),
        "corpus": _file_entry(corpus_path),
        "evaluator": _file_entry(evaluator_path),
    }
    if judge_validation_path is not None:
        files["judge_validation"] = _file_entry(judge_validation_path)
    checks = contract.get("checks", []) if isinstance(contract, dict) else []
    normalization_policy = {
        "surface_comparators": {
            surface["id"]: surface.get("compare", {})
            for surface in contract.get("public_surfaces", [])
            if isinstance(surface, dict) and isinstance(surface.get("id"), str)
        },
        "contract_normalization": contract.get("normalization_policy", {}),
    }
    check_specification_digest = sha256_bytes(
        json.dumps(checks, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": {
            "root": str(root),
            "revision": git_revision(root),
            "tree_digest": tree_digest(root),
        },
        "files": files,
        "normalization_policy": normalization_policy,
        "check_specification_digest": check_specification_digest,
        "policy": {
            "source_revision_change": "invalidate-and-rebuild-evidence",
            "required_case_removal": "forbidden-without-explicit-reapproval",
            "evaluator_change": "invalidate-and-rebuild-evidence",
        },
    }
    write_json(output_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze Migration Skill evidence")
    parser.add_argument("--root", required=True, help="source repository root")
    parser.add_argument("--contract", required=True, help="migration.json")
    parser.add_argument("--corpus", required=True, help="parity-corpus.json")
    parser.add_argument("--evaluator", required=True, help="evaluator script")
    parser.add_argument("--output", required=True, help="freeze-manifest.json")
    parser.add_argument("--judge-validation", help="optional judge validation artifact")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    freeze(
        Path(args.root),
        Path(args.contract),
        Path(args.corpus),
        Path(args.evaluator),
        Path(args.output),
        Path(args.judge_validation) if args.judge_validation else None,
    )
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
