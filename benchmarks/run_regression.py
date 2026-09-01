"""Replay published benchmark runs without a model or network dependency."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


MATRIX_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 2
# Backwards-compatible name for callers that import the matrix schema constant.
SCHEMA_VERSION = MATRIX_SCHEMA_VERSION
DEFAULT_MATRIX_NAME = "regression-matrix.json"
REQUIRED_RUN_FILES = (
    "report.json",
    "environment.json",
    "prompt.md",
    ".migration/baseline.json",
    ".migration/freeze-manifest.json",
    ".migration/migration.json",
    ".migration/migration-plan.json",
    ".migration/mutation-plan.json",
    ".migration/parity-corpus.json",
    ".migration/state.json",
    "source",
    "generated-target",
    "migration-skill/scripts",
)
SAFE_HOST_ENV_KEYS = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
}


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON: {path}: {exc}") from exc


def load_protocol_metadata(repo_root: Path) -> dict[str, Any]:
    """Load the Plugin and protocol versions used by a replay report."""

    manifest = _load_json(repo_root / ".codex-plugin" / "plugin.json")
    compatibility = _load_json(repo_root / "docs" / "plugin-compatibility.json")
    if not isinstance(manifest, dict):
        raise ValueError("Plugin manifest must be an object")
    if not isinstance(compatibility, dict):
        raise ValueError("Plugin compatibility policy must be an object")

    plugin_version = manifest.get("version")
    compatibility_plugin = compatibility.get("plugin")
    protocol = compatibility.get("protocol")
    if not isinstance(plugin_version, str) or not plugin_version:
        raise ValueError(".codex-plugin/plugin.json.version must be a non-empty string")
    if not isinstance(compatibility_plugin, dict):
        raise ValueError("docs/plugin-compatibility.json.plugin must be an object")
    if compatibility_plugin.get("version") != plugin_version:
        raise ValueError("Plugin manifest and compatibility policy versions differ")
    if not isinstance(protocol, dict):
        raise ValueError("docs/plugin-compatibility.json.protocol must be an object")

    contract_schema = protocol.get("contract_schema")
    freeze_schema = protocol.get("freeze_schema")
    if (
        not isinstance(contract_schema, int)
        or isinstance(contract_schema, bool)
        or not isinstance(freeze_schema, int)
        or isinstance(freeze_schema, bool)
    ):
        raise ValueError("protocol contract_schema and freeze_schema must be integers")

    return {
        "plugin_version": plugin_version,
        "protocol": {
            "contract_schema": contract_schema,
            "freeze_schema": freeze_schema,
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _relative_path(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a non-empty relative path")
        return
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        errors.append(f"{label} must stay relative to the benchmark run")


def _string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty string array")
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            errors.append(f"{label} must contain non-empty strings")
        else:
            result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{label} must not contain duplicate values")
    return result


PYTHON_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _validate_runtime(value: Any, label: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    requires_node = value.get("requires_node", False)
    if not isinstance(requires_node, bool):
        errors.append(f"{label}.requires_node must be boolean")
    modules = value.get("python_modules", [])
    if not isinstance(modules, list):
        errors.append(f"{label}.python_modules must be a string array")
        return
    for index, module in enumerate(modules):
        if not isinstance(module, str) or not PYTHON_MODULE_PATTERN.fullmatch(module):
            errors.append(f"{label}.python_modules[{index}] must be a valid Python module name")


def validate_matrix(document: Any) -> list[str]:
    """Return structural errors for the offline replay matrix."""

    errors: list[str] = []
    if not isinstance(document, dict):
        return ["matrix must be an object"]
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"matrix.schema_version must be {SCHEMA_VERSION}")
    runs = document.get("runs")
    if not isinstance(runs, list) or not runs:
        errors.append("matrix.runs must be a non-empty array")
        return errors

    run_ids: set[str] = set()
    for index, entry in enumerate(runs):
        label = f"runs[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        run_id = entry.get("run_id")
        if (
            not isinstance(run_id, str)
            or not run_id
            or PurePosixPath(run_id).name != run_id
            or PureWindowsPath(run_id).name != run_id
            or PureWindowsPath(run_id).drive
        ):
            errors.append(f"{label}.run_id must be a simple directory name")
        elif run_id in run_ids:
            errors.append(f"duplicate run_id: {run_id}")
        else:
            run_ids.add(run_id)

        _validate_runtime(entry.get("runtime"), f"{label}.runtime", errors)

        targets = entry.get("negative_targets")
        if not isinstance(targets, list) or not targets:
            errors.append(f"{label}.negative_targets must be a non-empty array")
            continue
        target_paths: set[str] = set()
        for target_index, target in enumerate(targets):
            target_label = f"{label}.negative_targets[{target_index}]"
            if not isinstance(target, dict):
                errors.append(f"{target_label} must be an object")
                continue
            path = target.get("path")
            _relative_path(path, f"{target_label}.path", errors)
            if isinstance(path, str):
                if path in target_paths:
                    errors.append(f"duplicate negative target path: {path}")
                target_paths.add(path)
            _string_list(target.get("expected_cases"), f"{target_label}.expected_cases", errors)
    return errors


def load_matrix(path: Path) -> dict[str, Any]:
    document = _load_json(path)
    errors = validate_matrix(document)
    if errors:
        raise ValueError("invalid regression matrix:\n- " + "\n- ".join(errors))
    return document


def discover_runs(runs_root: Path, run_ids: Iterable[str] | None = None) -> list[Path]:
    """Resolve selected published Run directories in caller-specified order."""

    root = runs_root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"benchmark runs root does not exist: {root}")
    available = {
        path.name: path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }
    selected = list(run_ids) if run_ids is not None else sorted(available)
    if len(selected) != len(set(selected)):
        raise ValueError("run selection contains duplicate ids")
    missing = [run_id for run_id in selected if run_id not in available]
    if missing:
        raise ValueError("unknown benchmark run(s): " + ", ".join(missing))
    return [available[run_id] for run_id in selected]


def _minimal_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.upper() in SAFE_HOST_ENV_KEYS:
            environment[key] = value
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def _runtime_variables(
    python_executable: str | None = None,
    node_executable: str | None = None,
) -> dict[str, str]:
    return {
        "PYTHON": python_executable or sys.executable,
        "NODE": node_executable or shutil.which("node") or "node",
    }


def _node_version(node_executable: str | None = None) -> str | None:
    node = node_executable or shutil.which("node")
    if not node:
        return None
    try:
        completed = subprocess.run(
            [node, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            shell=False,
            check=False,
        env=_minimal_environment(),
    )
    except (OSError, subprocess.SubprocessError):
        return None
    version = completed.stdout.strip()
    return version if completed.returncode == 0 and version else None


def _executable_available(value: str) -> bool:
    return bool(shutil.which(value) or Path(value).is_file())


def _runtime_preflight(
    runtime: Any,
    variables: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    requirements = runtime if isinstance(runtime, dict) else {}
    missing: list[str] = []
    if requirements.get("requires_node") is True and not _executable_available(variables["NODE"]):
        missing.append("node")

    modules = requirements.get("python_modules", [])
    if modules:
        if not _executable_available(variables["PYTHON"]):
            missing.append("python")
        else:
            probe = (
                "import importlib.util, sys; "
                "missing = [name for name in sys.argv[1:] "
                "if importlib.util.find_spec(name) is None]; "
                "print('\\n'.join(missing)); "
                "raise SystemExit(1 if missing else 0)"
            )
            try:
                completed = subprocess.run(
                    [variables["PYTHON"], "-c", probe, *modules],
                    env=_minimal_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    shell=False,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                missing.append("python-modules")
            else:
                if completed.returncode != 0:
                    found = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                    missing.extend(found or ["python-modules"])

    return {
        "passed": not missing,
        "missing": sorted(set(missing)),
    }


def _run_helper(script: Path, arguments: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [sys.executable, str(script), *arguments],
            cwd=str(cwd),
            env=_minimal_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "timed_out": True, "error": "timeout"}
    except FileNotFoundError:
        return {"exit_code": None, "timed_out": False, "error": "command-not-found"}
    except OSError:
        return {"exit_code": None, "timed_out": False, "error": "execution-error"}
    return {
        "exit_code": completed.returncode,
        "timed_out": False,
        "error": None,
    }


def _has_required_files(run_root: Path) -> list[str]:
    return [relative for relative in REQUIRED_RUN_FILES if not (run_root / relative).exists()]


def _copy_run(run_root: Path, destination: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}

    shutil.copytree(run_root, destination, ignore=ignore)


def _summary(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {"total": 0, "passed": 0, "failed": 0, "required_failed": []}
    value = document.get("summary")
    return dict(value) if isinstance(value, dict) else {"total": 0, "passed": 0, "failed": 0, "required_failed": []}


def _read_result(path: Path) -> dict[str, Any]:
    document = _load_json(path)
    if not isinstance(document, dict):
        raise ValueError(f"result must be an object: {path.name}")
    return document


def _execution_summary(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": execution.get("exit_code"),
        "timed_out": execution.get("timed_out", False),
        "error": execution.get("error"),
    }


def _helper_script(run_root: Path, name: str) -> Path:
    path = run_root / "migration-skill" / "scripts" / name
    if not path.is_file():
        raise ValueError(f"frozen helper is missing: {name}")
    return path


def _invoke(
    run_root: Path,
    script_name: str,
    arguments: list[str],
    output_path: Path,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    execution = _run_helper(_helper_script(run_root, script_name), arguments, run_root, timeout_seconds)
    if not output_path.exists():
        return execution, None
    try:
        return execution, _read_result(output_path)
    except ValueError:
        return execution, None


def _result_passed(document: dict[str, Any] | None) -> bool:
    return bool(document and document.get("passed") is True)


def _negative_result_passed(document: dict[str, Any] | None, expected_cases: list[str]) -> bool:
    if not document or document.get("negative_control_scoped") is not True:
        return False
    summary = document.get("summary")
    if not isinstance(summary, dict) or summary.get("targeted_control_passed") is not True:
        return False
    detected = summary.get("detected_mismatch_cases")
    return isinstance(detected, list) and set(expected_cases).issubset(set(detected))


def _replay_run(
    run_root: Path,
    matrix_entry: dict[str, Any],
    timeout_seconds: float,
    variables: dict[str, str],
) -> dict[str, Any]:
    report = _load_json(run_root / "report.json")
    environment = _load_json(run_root / "environment.json")
    missing = _has_required_files(run_root)
    if missing:
        return {
            "run_id": run_root.name,
            "status": "invalid",
            "failure_reasons": ["missing-artifact:" + item for item in missing],
        }
    if not isinstance(report, dict) or report.get("final_status", report.get("verification", {}).get("final_verdict")) != "VERIFIED":
        return {
            "run_id": run_root.name,
            "status": "invalid",
            "failure_reasons": ["published-run-is-not-VERIFIED"],
        }
    if not isinstance(environment, dict):
        return {
            "run_id": run_root.name,
            "status": "invalid",
            "failure_reasons": ["environment-summary-is-not-an-object"],
        }
    if environment.get("network_required") is True or environment.get("credentials_provided") is True:
        return {
            "run_id": run_root.name,
            "benchmark": report.get("benchmark"),
            "status": "blocked",
            "failure_reasons": ["published-run-requires-network-or-credentials"],
        }

    runtime_preflight = _runtime_preflight(matrix_entry.get("runtime"), variables, timeout_seconds)
    if not runtime_preflight["passed"]:
        return {
            "run_id": run_root.name,
            "benchmark": report.get("benchmark"),
            "status": "blocked",
            "failure_reasons": [
                "runtime-requirements-unavailable:" + ",".join(runtime_preflight["missing"])
            ],
            "runtime_preflight": runtime_preflight,
        }

    with tempfile.TemporaryDirectory(prefix="migration-regression-") as temporary:
        replay_root = Path(temporary) / run_root.name
        _copy_run(run_root, replay_root)
        artifact_root = replay_root / ".regression"
        artifact_root.mkdir()
        contract = replay_root / ".migration" / "migration.json"
        corpus = replay_root / ".migration" / "parity-corpus.json"
        manifest = replay_root / ".migration" / "freeze-manifest.json"
        variable_args = ["--var", f"PYTHON={variables['PYTHON']}", "--var", f"NODE={variables['NODE']}"]
        failures: list[str] = []

        validation_exec, validation = _invoke(
            replay_root,
            "validate_contract.py",
            ["--contract", str(contract), "--corpus", str(corpus), "--output", str(artifact_root / "contract-validation.json")],
            artifact_root / "contract-validation.json",
            timeout_seconds,
        )
        if validation_exec.get("exit_code") != 0 or not validation or validation.get("status") != "valid":
            failures.append("contract-validation-failed")

        resume_exec, resume = _invoke(
            replay_root,
            "verify_resume.py",
            [
                "--state", str(replay_root / ".migration" / "state.json"),
                "--target-root", str(replay_root / "generated-target"),
                "--manifest", str(manifest),
                "--workspace-root", str(replay_root),
                "--output", str(artifact_root / "resume-preflight.json"),
            ],
            artifact_root / "resume-preflight.json",
            timeout_seconds,
        )
        if resume_exec.get("exit_code") != 0 or not resume or resume.get("status") != "ready":
            failures.append("resume-preflight-failed")

        source_checks_path = artifact_root / "source-checks.json"
        source_exec, source_checks = _invoke(
            replay_root,
            "run_checks.py",
            [
                "--root", str(replay_root / "source"),
                "--spec", str(contract),
                "--profile", "source",
                "--output", str(source_checks_path),
                *variable_args,
            ],
            source_checks_path,
            timeout_seconds,
        )
        if source_checks is None:
            failures.append("source-checks-missing")

        target_checks_path = artifact_root / "target-checks.json"
        target_exec, target_checks = _invoke(
            replay_root,
            "run_checks.py",
            [
                "--root", str(replay_root / "generated-target"),
                "--spec", str(contract),
                "--profile", "target",
                "--output", str(target_checks_path),
                *variable_args,
            ],
            target_checks_path,
            timeout_seconds,
        )
        if target_exec.get("exit_code") != 0 or target_checks is None or not _summary(target_checks).get("all_required_passed", False):
            failures.append("target-checks-failed")

        source_parity_path = artifact_root / "source-parity.json"
        source_parity_exec, source_parity = _invoke(
            replay_root,
            "run_parity.py",
            [
                "--root", str(replay_root / "source"),
                "--contract", str(contract),
                "--corpus", str(corpus),
                "--profile", "source",
                "--output", str(source_parity_path),
                *variable_args,
            ],
            source_parity_path,
            timeout_seconds,
        )
        if source_parity_exec.get("exit_code") != 0 or source_parity is None or source_parity.get("status") != "passed":
            failures.append("source-parity-failed")

        target_parity_path = artifact_root / "target-parity.json"
        target_parity_exec, target_parity = _invoke(
            replay_root,
            "run_parity.py",
            [
                "--root", str(replay_root / "generated-target"),
                "--contract", str(contract),
                "--corpus", str(corpus),
                "--profile", "target",
                "--output", str(target_parity_path),
                *variable_args,
            ],
            target_parity_path,
            timeout_seconds,
        )
        if target_parity_exec.get("exit_code") != 0 or target_parity is None or target_parity.get("status") != "passed":
            failures.append("target-parity-failed")

        parity_result_path = artifact_root / "parity-result.json"
        compare_exec, parity_result = _invoke(
            replay_root,
            "compare_results.py",
            [
                "--source", str(source_parity_path),
                "--target", str(target_parity_path),
                "--contract", str(contract),
                "--corpus", str(corpus),
                "--manifest", str(manifest),
                "--output", str(parity_result_path),
            ],
            parity_result_path,
            timeout_seconds,
        )
        if compare_exec.get("exit_code") != 0 or not _result_passed(parity_result):
            failures.append("positive-parity-compare-failed")

        migration_result_path = artifact_root / "migration-result.json"
        evaluate_exec, migration_result = _invoke(
            replay_root,
            "evaluate_migration.py",
            [
                "--baseline", str(replay_root / ".migration" / "baseline.json"),
                "--source", str(source_checks_path),
                "--target", str(target_checks_path),
                "--parity", str(parity_result_path),
                "--contract", str(contract),
                "--manifest", str(manifest),
                "--state", str(replay_root / ".migration" / "state.json"),
                "--plan", str(replay_root / ".migration" / "migration-plan.json"),
                "--workspace-root", str(replay_root),
                "--output", str(migration_result_path),
            ],
            migration_result_path,
            timeout_seconds,
        )
        if evaluate_exec.get("exit_code") != 0 or not migration_result or migration_result.get("status") != "VERIFIED":
            failures.append("evaluator-did-not-return-VERIFIED")

        negative_controls: list[dict[str, Any]] = []
        for index, target_spec in enumerate(matrix_entry["negative_targets"]):
            target_path = replay_root / target_spec["path"]
            expected_cases = list(target_spec["expected_cases"])
            negative_parity_path = artifact_root / f"negative-parity-{index}.json"
            negative_compare_path = artifact_root / f"negative-compare-{index}.json"
            negative_parity_exec, negative_parity = _invoke(
                replay_root,
                "run_parity.py",
                [
                    "--root", str(target_path),
                    "--contract", str(contract),
                    "--corpus", str(corpus),
                    "--profile", "target",
                    "--output", str(negative_parity_path),
                    *variable_args,
                ],
                negative_parity_path,
                timeout_seconds,
            )
            negative_arguments = [
                "--source", str(source_parity_path),
                "--target", str(negative_parity_path),
                "--contract", str(contract),
                "--corpus", str(corpus),
                "--manifest", str(manifest),
                "--expect-mismatch",
                "--output", str(negative_compare_path),
            ]
            for case_id in expected_cases:
                negative_arguments.extend(["--expect-case", case_id])
            negative_compare_exec, negative_compare = _invoke(
                replay_root,
                "compare_results.py",
                negative_arguments,
                negative_compare_path,
                timeout_seconds,
            )
            passed = (
                target_path.is_dir()
                and negative_parity is not None
                and negative_compare_exec.get("exit_code") == 0
                and _negative_result_passed(negative_compare, expected_cases)
            )
            if not passed:
                failures.append(f"broken-target-rejection-failed:{target_spec['path']}")
            negative_controls.append(
                {
                    "path": target_spec["path"],
                    "expected_cases": expected_cases,
                    "passed": passed,
                    "executions": {
                        "parity": _execution_summary(negative_parity_exec),
                        "compare": _execution_summary(negative_compare_exec),
                    },
                }
            )

        return {
            "run_id": run_root.name,
            "benchmark": report.get("benchmark"),
            "status": "passed" if not failures else "failed",
            "failure_reasons": failures,
            "source_tree_digest": (migration_result or {}).get("source", {}).get("tree_digest")
            if isinstance(migration_result, dict)
            else None,
            "contract_validation": {
                "passed": validation_exec.get("exit_code") == 0 and isinstance(validation, dict) and validation.get("status") == "valid"
            },
            "executions": {
                "contract_validation": _execution_summary(validation_exec),
                "resume_preflight": _execution_summary(resume_exec),
                "source_checks": _execution_summary(source_exec),
                "target_checks": _execution_summary(target_exec),
                "source_parity": _execution_summary(source_parity_exec),
                "target_parity": _execution_summary(target_parity_exec),
                "parity_compare": _execution_summary(compare_exec),
                "evaluator": _execution_summary(evaluate_exec),
            },
            "resume_preflight": {
                "passed": resume_exec.get("exit_code") == 0 and isinstance(resume, dict) and resume.get("status") == "ready",
                "status": resume.get("status") if isinstance(resume, dict) else None,
            },
            "source_checks": _summary(source_checks),
            "target_checks": _summary(target_checks),
            "source_parity": _summary(source_parity),
            "target_parity": _summary(target_parity),
            "parity_compare": {
                "passed": _result_passed(parity_result),
                "required_failed": _summary(parity_result).get("required_failed", []),
            },
            "evaluator": {
                "passed": isinstance(migration_result, dict) and migration_result.get("status") == "VERIFIED",
                "status": migration_result.get("status") if isinstance(migration_result, dict) else None,
                "parity": (migration_result or {}).get("parity", {}).get("coverage", {})
                if isinstance(migration_result, dict)
                else {},
            },
            "broken_target_rejection": {
                "passed": bool(negative_controls) and all(item["passed"] for item in negative_controls),
                "controls": negative_controls,
            },
            "runtime_preflight": runtime_preflight,
        }


def run_regression(
    repo_root: Path,
    run_ids: Iterable[str] | None = None,
    *,
    matrix_path: Path | None = None,
    timeout_seconds: float = 120,
    python_executable: str | None = None,
    node_executable: str | None = None,
) -> dict[str, Any]:
    """Replay selected published benchmark runs using their frozen helpers."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    repo_root = repo_root.resolve()
    protocol_metadata = load_protocol_metadata(repo_root)
    matrix = load_matrix(matrix_path or repo_root / "benchmarks" / DEFAULT_MATRIX_NAME)
    entries = {entry["run_id"]: entry for entry in matrix["runs"]}
    selected_ids = list(run_ids) if run_ids is not None else list(entries)
    unknown = [run_id for run_id in selected_ids if run_id not in entries]
    if unknown:
        raise ValueError("run ids are not present in the regression matrix: " + ", ".join(unknown))
    run_paths = discover_runs(repo_root / "benchmarks" / "runs", selected_ids)
    variables = _runtime_variables(python_executable, node_executable)
    records = [_replay_run(path, entries[path.name], timeout_seconds, variables) for path in run_paths]
    summary = {
        "total": len(records),
        "passed": sum(1 for record in records if record.get("status") == "passed"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "blocked": sum(1 for record in records if record.get("status") == "blocked"),
        "invalid": sum(1 for record in records if record.get("status") == "invalid"),
    }
    if summary["invalid"]:
        status = "invalid"
    elif summary["blocked"]:
        status = "blocked"
    elif summary["failed"]:
        status = "failed"
    else:
        status = "passed"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "plugin_version": protocol_metadata["plugin_version"],
        "protocol": protocol_metadata["protocol"],
        "status": status,
        "offline_policy": {
            "model_required": False,
            "network_required": False,
            "credentials_allowed": False,
            "network_isolation_guaranteed": False,
        },
        "runtime": {
            "platform": platform.system(),
            "python": platform.python_version(),
            "node": _node_version(variables["NODE"]),
            "python_version": platform.python_version(),
            "node_version": _node_version(variables["NODE"]),
            "runtime_override": {
                "python": bool(python_executable),
                "node": bool(node_executable),
            },
        },
        "summary": summary,
        "runs": records,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay published Migration Skill benchmarks offline")
    parser.add_argument("--root", required=True, help="repository root")
    parser.add_argument("--matrix", help="regression-matrix.json")
    parser.add_argument("--run-id", action="append", help="select one run; repeatable")
    parser.add_argument("--output", required=True, help="regression-report.json")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--python-executable", help="Python runtime for benchmark commands")
    parser.add_argument("--node-executable", help="Node.js runtime for benchmark commands")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_regression(
        Path(args.root),
        args.run_id,
        matrix_path=Path(args.matrix) if args.matrix else None,
        timeout_seconds=args.timeout_seconds,
        python_executable=args.python_executable,
        node_executable=args.node_executable,
    )
    _write_json(Path(args.output), report)
    if report["status"] == "passed":
        return 0
    if report["status"] == "invalid":
        return 2
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
