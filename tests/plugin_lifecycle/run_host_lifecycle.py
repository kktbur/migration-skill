"""Opt-in Codex host lifecycle probe.

The default mode stages a local marketplace and records the manual host steps
without changing Codex configuration.  ``--execute-host`` is intentionally
required for commands that add/remove a marketplace or install/uninstall a
Plugin.  The probe cannot automate a new Codex session or prove natural
language Skill triggering; those checks remain explicit manual steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

try:
    from .lifecycle_support import stage_local_marketplace
except ImportError:  # pragma: no cover - direct script execution
    from lifecycle_support import stage_local_marketplace


OUTPUT_LIMIT = 4000
SECRET_NAME = re.compile(
    r"(?i)(api[_-]?key|access[_-]?key|token|secret|password|passwd|credential|private[_-]?key)"
)
SECRET_VALUE = re.compile(r"(?i)(bearer\s+|basic\s+|api[_ -]?key\s*[:=]\s*|token\s*[:=]\s*)[^\s,;]+")


def _redact(value: str) -> str:
    lines = []
    for line in value.splitlines():
        if SECRET_NAME.search(line):
            lines.append("[REDACTED HOST OUTPUT LINE]")
        else:
            lines.append(SECRET_VALUE.sub(r"\1[REDACTED]", line))
    text = "\n".join(lines)
    return text[:OUTPUT_LIMIT] + ("\n[TRUNCATED]" if len(text) > OUTPUT_LIMIT else "")


def _presence(name: str) -> bool:
    return any(key.lower() == name.lower() for key in os.environ)


def host_environment_presence() -> dict[str, bool]:
    """Expose only whether host path variables exist, never their values."""

    return {
        "HOME": _presence("HOME"),
        "CODEX_HOME": _presence("CODEX_HOME"),
        "USERPROFILE": _presence("USERPROFILE"),
    }


def classify_host_error(output: str) -> str | None:
    """Classify a known host prerequisite failure without exposing output."""

    lowered = output.lower()
    if "could not find home directory" in lowered or "failed to resolve codex_home" in lowered:
        return "codex-home-unresolved"
    return None


def _command_argv(command: str, arguments: Sequence[str]) -> list[str]:
    """Resolve a PowerShell Codex shim without enabling a general shell."""

    resolved = shutil.which(command) or command
    if Path(resolved).suffix.lower() == ".ps1":
        pwsh = shutil.which("pwsh") or "pwsh"
        return [pwsh, "-NoProfile", "-File", resolved, *arguments]
    return [resolved, *arguments]


def _run_host_command(command: str, arguments: Sequence[str], cwd: Path) -> dict[str, Any]:
    argv = _command_argv(command, arguments)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            shell=False,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        classification = classify_host_error(stdout + "\n" + stderr)
        return {
            "argv": [str(item) for item in argv],
            "exit_code": completed.returncode,
            "status": "passed" if completed.returncode == 0 else "failed",
            "stdout": _redact(stdout),
            "stderr": _redact(stderr),
            "classification": classification,
            "duration_seconds": round(time.perf_counter() - started, 6),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": [str(item) for item in argv],
            "exit_code": None,
            "status": "timeout",
            "stdout": _redact(str(exc.stdout or "")),
            "stderr": _redact(str(exc.stderr or "")),
            "classification": "timeout",
            "duration_seconds": round(time.perf_counter() - started, 6),
        }
    except OSError as exc:
        return {
            "argv": [str(item) for item in argv],
            "exit_code": None,
            "status": "failed",
            "stdout": "",
            "stderr": _redact(str(exc)),
            "classification": "command-not-found" if isinstance(exc, FileNotFoundError) else "execution-error",
            "duration_seconds": round(time.perf_counter() - started, 6),
        }


def run_host_lifecycle(
    plugin_root: Path,
    marketplace_root: Path,
    output_path: Path,
    *,
    codex_command: str = "codex",
    execute_host: bool = False,
) -> dict[str, Any]:
    """Stage a marketplace and optionally execute the host lifecycle probe."""

    plugin_root = plugin_root.resolve()
    marketplace_root = marketplace_root.resolve()
    output_path = output_path.resolve()
    staged = stage_local_marketplace(output_path.parent / "staged", plugin_root)
    # Keep the caller-visible path stable for manual host steps.  The staging
    # helper creates its own directory; move only within the caller's temp
    # probe workspace and refuse to overwrite existing data.
    if marketplace_root.exists():
        if any(marketplace_root.iterdir()):
            raise ValueError(f"marketplace root must be empty or absent: {marketplace_root}")
        marketplace_root.rmdir()
    marketplace_root.parent.mkdir(parents=True, exist_ok=True)
    staged["marketplace_root"].replace(marketplace_root)
    staged = {
        **staged,
        "marketplace_root": marketplace_root,
        "marketplace_file": marketplace_root / ".agents" / "plugins" / "marketplace.json",
        "plugin_root": marketplace_root / "plugins" / "migration-skill",
    }

    report: dict[str, Any] = {
        "schema_version": 1,
        "mode": "host-execute" if execute_host else "manual-only",
        "status": "not_requested" if not execute_host else "pending",
        "codex_command": codex_command,
        "host_environment_presence": host_environment_presence(),
        "marketplace_root": str(marketplace_root),
        "staged_plugin_root": str(staged["plugin_root"]),
        "checks": {
            "fresh_install": {"status": "manual_required"},
            "plugin_discovery": {"status": "manual_required"},
            "explicit_skill_invocation": {"status": "manual_required"},
            "natural_language_invocation": {"status": "manual_required"},
        },
        "cleanup": {"status": "not_run"},
        "manual_steps": [
            "restart Codex or open a new session after installation",
            "confirm Migration Skill appears in the Plugins directory",
            "invoke $migration-skill in a new session",
            "invoke with natural language: migrate a Python CLI to Node CLI while preserving behavior",
        ],
    }
    if not execute_host:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    commands = [
        (
            "marketplace_add",
            ["plugin", "marketplace", "add", str(marketplace_root), "--json"],
        ),
        (
            "marketplace_discovery",
            ["plugin", "list", "--available", "--marketplace", "migration-skill-dev", "--json"],
        ),
        (
            "plugin_install",
            ["plugin", "add", "migration-skill", "--marketplace", "migration-skill-dev", "--json"],
        ),
        ("plugin_list", ["plugin", "list", "--json"]),
    ]
    try:
        for name, arguments in commands:
            result = _run_host_command(codex_command, arguments, marketplace_root)
            report["checks"][name] = result
            if result["status"] != "passed":
                report["status"] = "blocked" if result.get("classification") == "codex-home-unresolved" else "failed"
                break
        else:
            report["checks"]["fresh_install"] = {
                "status": "passed",
                "commands": ["marketplace_add", "plugin_install"],
            }
            report["checks"]["plugin_discovery"] = {
                "status": "passed",
                "commands": ["marketplace_discovery", "plugin_list"],
            }
            report["status"] = "manual_required"
            report["checks"]["explicit_skill_invocation"] = {
                "status": "manual_required",
                "reason": "new-session invocation cannot be automated by this probe",
            }
            report["checks"]["natural_language_invocation"] = {
                "status": "manual_required",
                "reason": "new-session invocation cannot be automated by this probe",
            }
    finally:
        cleanup_results = []
        for name, arguments in (
            ("plugin_remove", ["plugin", "remove", "migration-skill", "--marketplace", "migration-skill-dev", "--json"]),
            ("marketplace_remove", ["plugin", "marketplace", "remove", "migration-skill-dev", "--json"]),
        ):
            cleanup_results.append({name: _run_host_command(codex_command, arguments, marketplace_root)})
        cleanup_failed = any(
            next(iter(item.values())).get("status") != "passed"
            for item in cleanup_results
            if item
        )
        report["cleanup"] = {
            "status": "failed" if cleanup_failed else "completed",
            "commands": cleanup_results,
        }
        if cleanup_failed and report["status"] not in {"blocked", "failed"}:
            report["status"] = "failed"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Codex Plugin lifecycle without host changes by default")
    parser.add_argument("--plugin-root", required=True, help="repository root containing .codex-plugin and skills/")
    parser.add_argument("--marketplace-root", required=True, help="empty directory to stage local marketplace")
    parser.add_argument("--output", required=True, help="probe report JSON")
    parser.add_argument("--codex-command", default="codex", help="Codex executable or PowerShell shim")
    parser.add_argument(
        "--execute-host",
        action="store_true",
        help="perform host marketplace/install/remove commands; changes Codex host state",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_host_lifecycle(
        Path(args.plugin_root),
        Path(args.marketplace_root),
        Path(args.output),
        codex_command=args.codex_command,
        execute_host=args.execute_host,
    )
    return 0 if report["status"] in {"not_requested", "manual_required"} else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
