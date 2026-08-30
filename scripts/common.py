"""Shared standard-library helpers for Migration Skill scripts.

The public scripts deliberately keep their command line interfaces small.  This
module contains the boring, deterministic pieces that must behave the same in
every phase: JSON I/O, safe path handling, tree hashing, command execution and
result summaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INVALID = 2

TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# These directories are generated or dependency-heavy and must not influence
# the source evidence digest.  The inventory script uses the same policy.
IGNORED_TREE_DIRS = frozenset(
    {
        ".git",
        ".migration",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "target",
        "coverage",
        ".next",
        ".turbo",
    }
)

VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(ValueError):
    """Raised when a deterministic helper receives invalid configuration."""


class FrozenStateError(ConfigError):
    """Raised when evidence no longer matches the freeze manifest."""


def load_json(path: str | os.PathLike[str]) -> Any:
    """Load UTF-8 JSON and raise a useful configuration error on failure."""

    file_path = Path(path)
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取 JSON: {file_path}: {exc}") from exc


def write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Write pretty, stable JSON using a same-directory temporary file."""

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    payload += "\n"
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
        temporary_path.replace(file_path)
    except OSError as exc:
        raise ConfigError(f"无法写入 JSON: {file_path}: {exc}") from exc
    finally:
        if "temporary_path" in locals() and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def canonical_path(path: str | os.PathLike[str]) -> Path:
    """Resolve a path without requiring it to exist."""

    return Path(path).expanduser().resolve(strict=False)


def is_within(path: Path, root: Path) -> bool:
    """Return whether *path* is root itself or below *root*."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_cwd(root: Path, raw_cwd: Any) -> Path:
    """Resolve a check cwd and reject paths outside the execution root."""

    if raw_cwd is None:
        candidate = root
    elif not isinstance(raw_cwd, str) or not raw_cwd:
        raise ConfigError("check.cwd 必须是非空字符串")
    else:
        candidate = canonical_path(Path(raw_cwd) if os.path.isabs(raw_cwd) else root / raw_cwd)
    if not candidate.exists() or not candidate.is_dir():
        raise ConfigError(f"check.cwd 不存在或不是目录: {candidate}")
    if not is_within(candidate, root):
        raise ConfigError(f"check.cwd 必须位于执行 root 内: {candidate}")
    return candidate


def validate_argv(argv: Any, field_name: str = "argv") -> list[str]:
    """Validate the explicit argv form used by all command runners."""

    if not isinstance(argv, list) or not argv:
        raise ConfigError(f"{field_name} 必须是非空字符串数组；不支持 shell 字符串")
    if any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        raise ConfigError(f"{field_name} 中每一项都必须是非空字符串且不能含 NUL")
    return list(argv)


def expand_vars(value: str, variables: Mapping[str, str]) -> str:
    """Expand only explicitly supplied ``${NAME}`` variables.

    Not consulting the ambient environment here makes command specifications
    reproducible and avoids silently injecting credentials into argv.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ConfigError(f"未提供命令变量: {name}")
        return str(variables[name])

    return VAR_PATTERN.sub(replace, value)


def expand_argv(argv: Sequence[str], variables: Mapping[str, str]) -> list[str]:
    return [expand_vars(item, variables) for item in argv]


def cap_text(value: str | bytes | None, limit: int) -> tuple[str, bool]:
    """Decode and cap command output without failing on invalid UTF-8."""

    if value is None:
        text = ""
    elif isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def normalize_text(value: Any) -> str:
    """Normalize only line endings and trailing whitespace per the v1 policy."""

    if not isinstance(value, str):
        raise ConfigError("text-normalized 比较要求字符串")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in value.split("\n"))


def normalize_json_value(value: Any) -> Any:
    """Convert JSON-like values into a stable semantic representation."""

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"json-semantic 值不是有效 JSON: {exc}") from exc
    return value


def compare_values(source: Any, target: Any, mode: str) -> bool:
    """Compare two observed values using an explicit contract comparator."""

    if mode == "exact" or mode == "snapshot":
        return source == target
    if mode in {"text", "text-normalized"}:
        return normalize_text(source) == normalize_text(target)
    if mode == "json-semantic":
        return normalize_json_value(source) == normalize_json_value(target)
    if mode == "exit-code":
        return source == target
    raise ConfigError(f"不支持的比较模式: {mode}")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    file_path = Path(path)
    try:
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ConfigError(f"无法计算文件摘要: {file_path}: {exc}") from exc
    return "sha256:" + digest.hexdigest()


def iter_source_files(root: Path) -> Iterable[tuple[Path, str]]:
    """Yield regular files and relative POSIX paths under a source root."""

    root = canonical_path(root)
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory in directories:
            candidate = current_path / directory
            if directory in IGNORED_TREE_DIRS or candidate.is_symlink():
                continue
            kept_directories.append(directory)
        directories[:] = sorted(kept_directories)
        for filename in sorted(filenames):
            candidate = current_path / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            yield candidate, relative


def tree_digest(root: Path) -> str:
    """Hash path names and file bytes while ignoring generated directories."""

    digest = hashlib.sha256()
    for file_path, relative in iter_source_files(root):
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            raise ConfigError(f"无法读取 source 文件: {file_path}: {exc}") from exc
        encoded_name = relative.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def git_revision(root: Path) -> str | None:
    """Return HEAD for a Git root, or None for a non-Git source tree."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(canonical_path(root)), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    revision = completed.stdout.strip()
    return revision or None


def _safe_env() -> dict[str, str]:
    """Return the execution environment without ever serializing it."""

    return {str(key): str(value) for key, value in os.environ.items()}


def redact_text(value: str) -> str:
    """Redact common credential-shaped output without logging environment data.

    This is intentionally conservative: the helper never prints the ambient
    environment, and only masks obvious bearer/basic authorization tokens in
    captured output.  Real isolation still belongs to an external sandbox.
    """

    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(basic\s+)[A-Za-z0-9+/=]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    return value


def run_check(
    root: Path,
    check: Mapping[str, Any],
    variables: Mapping[str, str] | None = None,
    output_limit: int = 20000,
) -> dict[str, Any]:
    """Run one explicit argv check with shell disabled."""

    variables = variables or {}
    check_id = check.get("id")
    if not isinstance(check_id, str) or not check_id:
        raise ConfigError("check.id 必须是非空字符串")
    argv = expand_argv(validate_argv(check.get("argv"), f"check[{check_id}].argv"), variables)
    cwd = resolve_cwd(root, check.get("cwd"))
    required = check.get("required", True)
    if not isinstance(required, bool):
        raise ConfigError(f"check[{check_id}].required 必须是布尔值")
    expected_exit_code = check.get("expected_exit_code", 0)
    if not isinstance(expected_exit_code, int) or isinstance(expected_exit_code, bool):
        raise ConfigError(f"check[{check_id}].expected_exit_code 必须是整数")
    timeout_seconds = check.get("timeout_seconds", 60)
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
        raise ConfigError(f"check[{check_id}].timeout_seconds 必须是正数")
    if timeout_seconds <= 0:
        raise ConfigError(f"check[{check_id}].timeout_seconds 必须是正数")
    env_spec = check.get("env", {})
    if env_spec is None:
        env_spec = {}
    if not isinstance(env_spec, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in env_spec.items()
    ):
        raise ConfigError(f"check[{check_id}].env 必须是字符串到字符串的对象")
    environment = _safe_env()
    for key, value in env_spec.items():
        environment[key] = expand_vars(value, variables)

    started = time.perf_counter()
    status = "failed"
    exit_code: int | None = None
    timed_out = False
    stdout_value = ""
    stderr_value = ""
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=environment,
            stdin=subprocess.DEVNULL,
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
        status = "passed" if exit_code == expected_exit_code else "failed"
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        status = "timeout"
        stdout_value = exc.stdout or ""
        stderr_value = exc.stderr or ""
    except OSError as exc:
        status = "failed"
        stderr_value = str(exc)
    duration = time.perf_counter() - started
    stdout_value, stdout_truncated = cap_text(stdout_value, output_limit)
    stderr_value, stderr_truncated = cap_text(stderr_value, output_limit)
    return {
        "id": check_id,
        "kind": check.get("kind", "check"),
        "required": required,
        "argv": [redact_text(item) for item in argv],
        "cwd": str(cwd),
        "expected_exit_code": expected_exit_code,
        "exit_code": exit_code,
        "status": status,
        "timeout": timed_out,
        "stdout": redact_text(stdout_value),
        "stderr": redact_text(stderr_value),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "duration_seconds": round(duration, 6),
    }


def summarize_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for result in results if result.get("status") == "passed")
    failed = sum(1 for result in results if result.get("status") == "failed")
    timed_out = sum(1 for result in results if result.get("status") == "timeout")
    required = [result for result in results if result.get("required", True)]
    required_failed = [
        str(result.get("id"))
        for result in required
        if result.get("status") != "passed"
    ]
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "timed_out": timed_out,
        "required_failed": required_failed,
        "all_required_passed": not required_failed,
    }


def checks_from_spec(spec: Any, profile: str) -> list[dict[str, Any]]:
    """Read checks from either a full migration contract or a check list."""

    if isinstance(spec, list):
        raw_checks = spec
    elif isinstance(spec, dict):
        raw_checks = spec.get("checks", [])
        if isinstance(raw_checks, dict):
            raw_checks = raw_checks.get(profile, [])
        elif raw_checks is None:
            raw_checks = []
    else:
        raise ConfigError("check spec 必须是数组或包含 checks 的对象")
    if not isinstance(raw_checks, list):
        raise ConfigError(f"checks.{profile} 必须是数组")
    selected: list[dict[str, Any]] = []
    for check in raw_checks:
        if not isinstance(check, dict):
            raise ConfigError("每个 check 必须是对象")
        check_profile = check.get("profile")
        if check_profile is not None and check_profile != profile:
            continue
        selected.append(dict(check))
    return selected


def result_items(document: Any, preferred_key: str = "results") -> list[dict[str, Any]]:
    """Extract result/case records from common helper output shapes."""

    if isinstance(document, list):
        raw = document
    elif isinstance(document, dict):
        raw = document.get(preferred_key)
        if raw is None:
            raw = document.get("cases")
        if raw is None:
            raw = document.get("results")
        if raw is None:
            raw = document.get("checks")
    else:
        raw = None
    if not isinstance(raw, list):
        raise ConfigError("结果 JSON 必须包含 results、cases 或 checks 数组")
    if any(not isinstance(item, dict) for item in raw):
        raise ConfigError("结果数组中的每一项都必须是对象")
    return [dict(item) for item in raw]


def result_map(document: Any, preferred_key: str = "results") -> dict[str, dict[str, Any]]:
    items = result_items(document, preferred_key)
    mapping: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ConfigError("结果项必须包含非空 id")
        if item_id in mapping:
            raise ConfigError(f"结果包含重复 id: {item_id}")
        mapping[item_id] = item
    return mapping


def verify_freeze(manifest_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Verify every source and evidence digest in a freeze manifest."""

    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise FrozenStateError("freeze manifest schema_version 不受支持")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise FrozenStateError("freeze manifest 缺少 source")
    root_value = source.get("root")
    if not isinstance(root_value, str) or not root_value:
        raise FrozenStateError("freeze manifest.source.root 无效")
    root = canonical_path(root_value)
    if not root.exists() or not root.is_dir():
        raise FrozenStateError(f"冻结的 source root 不存在: {root}")
    expected_revision = source.get("revision")
    current_revision = git_revision(root)
    if expected_revision != current_revision:
        raise FrozenStateError(
            f"Source revision 已变化: expected={expected_revision!r}, current={current_revision!r}"
        )
    expected_tree_digest = source.get("tree_digest")
    current_tree_digest = tree_digest(root)
    if expected_tree_digest != current_tree_digest:
        raise FrozenStateError(
            f"Source tree digest 已变化: expected={expected_tree_digest!r}, current={current_tree_digest!r}"
        )

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise FrozenStateError("freeze manifest 缺少 files")
    verified_files: list[str] = []
    for label, entry in files.items():
        if not isinstance(entry, dict):
            raise FrozenStateError(f"冻结文件条目无效: {label}")
        file_value = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(file_value, str) or not isinstance(expected_hash, str):
            raise FrozenStateError(f"冻结文件条目缺少 path/sha256: {label}")
        file_path = canonical_path(file_value)
        if not file_path.exists() or not file_path.is_file():
            raise FrozenStateError(f"冻结文件不存在: {file_path}")
        actual_hash = sha256_file(file_path)
        if actual_hash != expected_hash:
            raise FrozenStateError(
                f"冻结文件已变化: {label}: expected={expected_hash}, current={actual_hash}"
            )
        verified_files.append(label)
    return {
        "intact": True,
        "manifest": manifest,
        "source_root": str(root),
        "revision": current_revision,
        "tree_digest": current_tree_digest,
        "verified_files": verified_files,
    }


def json_value_at(value: Any, path: Sequence[str]) -> tuple[bool, Any]:
    """Get a mapping field while preserving the distinction from JSON null."""

    current = value
    for component in path:
        if not isinstance(current, dict) or component not in current:
            return False, None
        current = current[component]
    return True, current


def now_environment_summary() -> dict[str, str]:
    """Return non-secret execution metadata suitable for result files."""

    return {
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }
