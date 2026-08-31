"""Shared standard-library helpers for Migration Skill scripts.

The public scripts deliberately keep their command line interfaces small. This
module contains the deterministic pieces that must behave the same in every
phase: JSON I/O, safe path handling, source hashing, command execution,
comparison normalization, and result summaries.
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

TOOL_VERSION = "0.3.0"
FREEZE_SCHEMA_VERSION = 3
SUPPORTED_FREEZE_SCHEMA_VERSIONS = {1, 2, FREEZE_SCHEMA_VERSION}
SCHEMA_VERSION = FREEZE_SCHEMA_VERSION

# Generic non-Git inventory/digest traversal skips generated and dependency
# directories. A Git-aware traversal below prefers tracked plus non-ignored
# working-tree files, so a tracked directory named ``target`` is not silently
# discarded.
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

ALWAYS_IGNORED_TREE_DIRS = frozenset({".git", ".migration"})
SECRET_FILE_NAMES = frozenset(
    {
        "credentials",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "secret",
        "secret.json",
        "secret.yaml",
        "secret.yml",
        "secrets.yaml",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
    }
)
SECRET_FILE_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".jks", ".p8", ".der"})
SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
    }
)
SECRET_ENV_PATTERN = re.compile(
    r"(?i)(^|_)(api[_-]?key|access[_-]?key|token|secret|password|passwd|credential|private[_-]?key|auth)(_|$)"
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
    temporary_path: Path | None = None
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
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def canonical_path(path: str | os.PathLike[str]) -> Path:
    """Resolve a path without requiring it to exist."""

    return Path(path).expanduser().resolve(strict=False)


def relative_posix_path(path: Path, root: Path) -> str:
    """Return a portable POSIX path and reject paths outside *root*."""

    path = canonical_path(path)
    root = canonical_path(root)
    if not is_within(path, root):
        raise ConfigError(f"路径必须位于 workspace root 内: {path}")
    relative = path.relative_to(root).as_posix()
    return relative or "."


def relative_reference_path(path: Path, base: Path) -> str:
    """Return a portable relative reference, allowing ``..`` segments."""

    import posixpath

    relative = os.path.relpath(str(canonical_path(path)), str(canonical_path(base)))
    return posixpath.normpath(relative).replace("\\", "/") or "."


def manifest_workspace_root(
    manifest_path: str | os.PathLike[str],
    manifest: Mapping[str, Any],
    workspace_root: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Resolve the portable workspace base for a v3 manifest.

    A v3 manifest stores ``workspace_root`` relative to the directory that
    contains the manifest.  Supplying an explicit workspace root is useful
    when replaying an artifact after moving the whole workspace.
    """

    schema_version = manifest.get("schema_version") if isinstance(manifest, Mapping) else None
    if schema_version != FREEZE_SCHEMA_VERSION:
        return None
    if workspace_root is not None:
        return canonical_path(workspace_root)
    raw_root = manifest.get("workspace_root", ".")
    if not isinstance(raw_root, str) or not raw_root or os.path.isabs(raw_root):
        raise FrozenStateError("freeze manifest.workspace_root 必须是相对路径")
    manifest_parent = canonical_path(manifest_path).parent
    resolved = canonical_path(manifest_parent / raw_root)
    if not resolved.exists() or not resolved.is_dir():
        raise FrozenStateError(f"portable workspace root 不存在: {resolved}")
    return resolved


def resolve_manifest_path(
    manifest_path: str | os.PathLike[str],
    manifest: Mapping[str, Any],
    value: str,
    workspace_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve a manifest file path for both v2 absolute and v3 relative data."""

    if not isinstance(value, str) or not value:
        raise FrozenStateError("freeze manifest path 无效")
    base = manifest_workspace_root(manifest_path, manifest, workspace_root)
    if base is not None:
        if os.path.isabs(value):
            raise FrozenStateError(f"v3 freeze manifest 不允许绝对路径: {value}")
        resolved = canonical_path(base / value)
        if not is_within(resolved, base):
            raise FrozenStateError(f"freeze manifest path 越过 workspace root: {value}")
        return resolved
    return canonical_path(value)


def is_within(path: Path, root: Path) -> bool:
    """Return whether *path* is root itself or below *root*."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_cwd(root: Path, raw_cwd: Any) -> Path:
    """Resolve a check cwd and reject paths outside the execution root."""

    root = canonical_path(root)
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
    """Expand only explicitly supplied ``${NAME}`` variables."""

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


def normalize_text(value: Any, normalization: Any = None) -> str:
    """Apply only explicitly allowed text normalizations.

    ``text-normalized`` uses both rules by default. Other modes apply only the
    rules explicitly supplied by their comparator configuration.
    """

    if not isinstance(value, str):
        raise ConfigError("文本比较要求字符串")
    rules: list[str]
    if normalization is None:
        rules = []
    elif isinstance(normalization, str):
        rules = [normalization]
    elif isinstance(normalization, list) and all(isinstance(item, str) for item in normalization):
        rules = list(normalization)
    else:
        raise ConfigError("normalization 必须是字符串或字符串数组")
    unknown = set(rules) - {"crlf-to-lf", "trim-trailing-whitespace"}
    if unknown:
        raise ConfigError(f"不支持的 normalization: {sorted(unknown)}")
    if "crlf-to-lf" in rules:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if "trim-trailing-whitespace" in rules:
        value = "\n".join(line.rstrip() for line in value.split("\n"))
    return value


def normalize_json_value(value: Any, normalization: Any = None) -> Any:
    """Convert JSON-like values into a stable semantic representation."""

    if isinstance(value, str):
        if normalization is not None:
            value = normalize_text(value, normalization)
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"json-semantic 值不是有效 JSON: {exc}") from exc
    return value


def compare_values(source: Any, target: Any, mode: str, normalization: Any = None) -> bool:
    """Compare two observed values using an explicit contract comparator."""

    if mode in {"exact", "snapshot", "exit-code"}:
        if normalization is None:
            return source == target
        if isinstance(source, str) and isinstance(target, str):
            return normalize_text(source, normalization) == normalize_text(target, normalization)
        return source == target
    if mode == "text":
        if normalization is None:
            return source == target
        return normalize_text(source, normalization) == normalize_text(target, normalization)
    if mode == "text-normalized":
        rules = normalization if normalization is not None else ["crlf-to-lf", "trim-trailing-whitespace"]
        return normalize_text(source, rules) == normalize_text(target, rules)
    if mode == "json-semantic":
        return normalize_json_value(source, normalization) == normalize_json_value(target, normalization)
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


def is_secret_path(relative: str | os.PathLike[str]) -> bool:
    """Return whether a relative source path is treated as secret material."""

    path = Path(relative)
    name = path.name.lower()
    if name in SECRET_FILE_NAMES or path.suffix.lower() in SECRET_FILE_SUFFIXES:
        return True
    if any(token in name for token in ("secret", "credential")):
        return True
    if name.startswith(".env") and name not in {".env.example", ".env.sample", ".env.template"}:
        return True
    return any(part.lower() in {"secrets", "credentials"} for part in path.parts)


def _git_file_paths(root: Path) -> list[str] | None:
    """Return tracked and non-ignored paths for a Git root, if available."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(canonical_path(root)), "ls-files", "-co", "--exclude-standard", "-z"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        raw_paths = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    except AttributeError:
        return None
    paths = []
    for raw in raw_paths:
        if not raw:
            continue
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            continue
        if any(part.lower() in ALWAYS_IGNORED_TREE_DIRS for part in path.parts):
            continue
        if is_secret_path(path):
            continue
        paths.append(path.as_posix())
    return sorted(set(paths))


def iter_source_files(root: Path) -> Iterable[tuple[Path, str]]:
    """Yield regular non-secret files and relative POSIX paths.

    Git repositories use tracked plus non-ignored working-tree files. Generic
    trees use the conservative generated-directory policy. Secret-like files
    are excluded from both modes before their contents are opened.
    """

    root = canonical_path(root)
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"root 不存在或不是目录: {root}")

    git_paths = _git_file_paths(root)
    if git_paths is not None:
        for relative in git_paths:
            candidate = root / relative
            if candidate.is_symlink() or not candidate.is_file():
                continue
            yield candidate, relative
        return

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
            if is_secret_path(relative):
                continue
            yield candidate, relative


def tree_digest(root: Path) -> str:
    """Hash path names and file bytes with a streaming, secret-aware policy."""

    digest = hashlib.sha256()
    for file_path, relative in iter_source_files(root):
        encoded_name = relative.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        try:
            file_size = file_path.stat().st_size
            digest.update(file_size.to_bytes(8, "big"))
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ConfigError(f"无法读取 source 文件: {file_path}: {exc}") from exc
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


def is_secret_env_name(name: str) -> bool:
    return bool(SECRET_ENV_PATTERN.search(name))


def validate_variable_name(name: str, label: str = "variable") -> str:
    """Validate an explicit command variable without permitting secret-shaped names."""

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ConfigError(f"{label} 名称无效: {name!r}")
    if is_secret_env_name(name):
        raise ConfigError(f"{label} 不允许疑似 Secret 环境变量: {name}")
    return name


def _ambient_value(name: str) -> tuple[str, str] | None:
    for actual, value in os.environ.items():
        if actual.lower() == name.lower():
            return actual, str(value)
    return None


def _validate_environment_spec(spec: Any, label: str = "environment") -> tuple[list[str], dict[str, str]]:
    if spec is None:
        return [], {}
    if not isinstance(spec, dict):
        raise ConfigError(f"{label} 必须是对象")
    unknown = set(spec) - {"inherit", "set"}
    if unknown:
        raise ConfigError(f"{label} 包含未知字段: {sorted(unknown)}")
    inherit = spec.get("inherit", [])
    if not isinstance(inherit, list) or any(not isinstance(item, str) or not item for item in inherit):
        raise ConfigError(f"{label}.inherit 必须是字符串数组")
    values = spec.get("set", {})
    if not isinstance(values, dict) or any(
        not isinstance(key, str) or not key or not isinstance(value, str) for key, value in values.items()
    ):
        raise ConfigError(f"{label}.set 必须是字符串到字符串的对象")
    for key in [*inherit, *values]:
        if "\x00" in key or is_secret_env_name(key):
            raise ConfigError(f"{label} 不允许继承或设置疑似 Secret 环境变量: {key}")
    return list(dict.fromkeys(inherit)), dict(values)


def _safe_env(
    environment_spec: Mapping[str, Any] | None = None,
    variables: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a minimum environment without implicit credential inheritance.

    Only the platform-safe allowlist is copied by default. Additional names
    and values must be explicitly declared by a Contract and secret-shaped
    names are rejected even when explicitly requested.
    """

    inherit, set_values = _validate_environment_spec(environment_spec or {})
    variables = variables or {}
    environment: dict[str, str] = {}
    for key in SAFE_ENV_KEYS:
        found = _ambient_value(key)
        if found is not None:
            actual, value = found
            environment[actual] = value
    for key in inherit:
        found = _ambient_value(key)
        if found is not None:
            actual, value = found
            environment[actual] = value
    for key, value in set_values.items():
        environment[key] = expand_vars(value, variables)
    return environment


def _merge_environment_specs(
    base: Mapping[str, Any] | None,
    override: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_inherit, base_set = _validate_environment_spec(base or {}, "environment")
    override_inherit, override_set = _validate_environment_spec(override or {}, "check.environment")
    merged_set = dict(base_set)
    merged_set.update(override_set)
    return {"inherit": list(dict.fromkeys([*base_inherit, *override_inherit])), "set": merged_set}


def redact_text(value: str) -> str:
    """Redact common credential-shaped output without logging environment data."""

    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(basic\s+)[A-Za-z0-9+/=]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(password|secret|credential|private[_ -]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
    return value


def run_check(
    root: Path,
    check: Mapping[str, Any],
    variables: Mapping[str, str] | None = None,
    output_limit: int = 20000,
    environment_spec: Mapping[str, Any] | None = None,
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
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ConfigError(f"check[{check_id}].timeout_seconds 必须是正数")

    check_environment = check.get("environment")
    legacy_env = check.get("env")
    if check_environment is not None and legacy_env is not None:
        raise ConfigError(f"check[{check_id}] 不能同时使用 environment 和旧版 env")
    if check_environment is None and legacy_env is not None:
        if not isinstance(legacy_env, dict):
            raise ConfigError(f"check[{check_id}].env 必须是字符串到字符串的对象")
        check_environment = {"set": legacy_env}
    environment = _safe_env(
        _merge_environment_specs(environment_spec, check_environment),
        variables,
    )

    started = time.perf_counter()
    status = "failed"
    exit_code: int | None = None
    timed_out = False
    stdout_value = ""
    stderr_value = ""
    execution_error: str | None = None
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
        execution_error = "timeout"
    except FileNotFoundError as exc:
        status = "failed"
        stderr_value = str(exc)
        execution_error = "command-not-found"
    except OSError as exc:
        status = "failed"
        stderr_value = str(exc)
        execution_error = "execution-error"
    duration = time.perf_counter() - started
    stdout_value, stdout_truncated = cap_text(stdout_value, output_limit)
    stderr_value, stderr_truncated = cap_text(stderr_value, output_limit)
    result = {
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
    if execution_error:
        result["execution_error"] = execution_error
    return result


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


def _bundle_files(root: Path) -> dict[str, Path]:
    if not root.exists() or not root.is_dir():
        raise FrozenStateError(f"verifier bundle root 不存在: {root}")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        if path.is_symlink() or not path.is_file() or "__pycache__" in path.parts:
            continue
        files[path.relative_to(root).as_posix()] = path
    if not files:
        raise FrozenStateError(f"verifier bundle 没有 Python 文件: {root}")
    return files


def _verify_file_entries(
    entries: Mapping[str, Any],
    label: str,
    *,
    manifest_path: Path | None = None,
    manifest: Mapping[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    if not isinstance(entries, dict) or not entries:
        raise FrozenStateError(f"freeze manifest 缺少 {label}")
    verified: list[str] = []
    resolved: dict[str, str] = {}
    for entry_label, entry in entries.items():
        if not isinstance(entry, dict):
            raise FrozenStateError(f"冻结文件条目无效: {entry_label}")
        file_value = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(file_value, str) or not isinstance(expected_hash, str):
            raise FrozenStateError(f"冻结文件条目缺少 path/sha256: {entry_label}")
        if manifest_path is not None and manifest is not None:
            file_path = resolve_manifest_path(manifest_path, manifest, file_value, workspace_root)
        elif workspace_root is not None and not os.path.isabs(file_value):
            file_path = canonical_path(workspace_root / file_value)
        else:
            file_path = canonical_path(file_value)
        if not file_path.exists() or not file_path.is_file():
            raise FrozenStateError(f"冻结文件不存在: {file_path}")
        actual_hash = sha256_file(file_path)
        if actual_hash != expected_hash:
            raise FrozenStateError(
                f"冻结文件已变化: {entry_label}: expected={expected_hash}, current={actual_hash}"
            )
        verified.append(str(entry_label))
        resolved[str(entry_label)] = str(file_path)
    return verified, resolved


def verify_freeze(
    manifest_path: str | os.PathLike[str],
    workspace_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Verify source evidence, assets, and the complete verifier bundle."""

    manifest_file = canonical_path(manifest_path)
    manifest = load_json(manifest_file)
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in SUPPORTED_FREEZE_SCHEMA_VERSIONS:
        raise FrozenStateError("freeze manifest schema_version 不受支持")
    schema_version = manifest.get("schema_version")
    portable_workspace = manifest_workspace_root(manifest_file, manifest, workspace_root)
    if schema_version == FREEZE_SCHEMA_VERSION:
        if manifest.get("path_mode") != "relative" or manifest.get("portable") is not True:
            raise FrozenStateError("v3 freeze manifest 必须声明 relative/portable")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise FrozenStateError("freeze manifest 缺少 source")
    root_value = source.get("root")
    if not isinstance(root_value, str) or not root_value:
        raise FrozenStateError("freeze manifest.source.root 无效")
    root = (
        resolve_manifest_path(manifest_file, manifest, root_value, portable_workspace)
        if schema_version == FREEZE_SCHEMA_VERSION
        else canonical_path(root_value)
    )
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
    verified_files, resolved_files = _verify_file_entries(
        files,
        "files",
        manifest_path=manifest_file if schema_version == FREEZE_SCHEMA_VERSION else None,
        manifest=manifest if schema_version == FREEZE_SCHEMA_VERSION else None,
        workspace_root=portable_workspace,
    )
    if schema_version in {2, FREEZE_SCHEMA_VERSION}:
        contract_entry = files.get("contract") if isinstance(files, dict) else None
        if not isinstance(contract_entry, dict) or not isinstance(contract_entry.get("path"), str):
            raise FrozenStateError("freeze manifest 缺少冻结 contract")
        contract_path = resolve_manifest_path(
            manifest_file,
            manifest,
            contract_entry["path"],
            portable_workspace,
        ) if schema_version == FREEZE_SCHEMA_VERSION else canonical_path(contract_entry["path"])
        contract = load_json(contract_path)
        if not isinstance(contract, dict):
            raise FrozenStateError("冻结 contract 顶层必须是对象")
        expected_check_specification = {
            "checks": contract.get("checks", []),
            "environment": contract.get("environment", {}),
        }
        if schema_version == FREEZE_SCHEMA_VERSION:
            expected_check_specification["completion_gates"] = contract.get("completion_gates", {})
        recorded_check_specification = manifest.get("check_specification")
        if recorded_check_specification != expected_check_specification:
            raise FrozenStateError("冻结的 check specification 与 Contract 不一致")
        recorded_digest = manifest.get("check_specification_digest")
        actual_digest = sha256_bytes(
            json.dumps(
                recorded_check_specification,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if recorded_digest != actual_digest:
            raise FrozenStateError("check specification digest 无效")
        expected_normalization = {
            "surface_comparators": {
                surface["id"]: surface.get("compare", {})
                for surface in contract.get("public_surfaces", [])
                if isinstance(surface, dict) and isinstance(surface.get("id"), str)
            },
            "contract_normalization": contract.get("normalization_policy", {}),
        }
        if manifest.get("normalization_policy") != expected_normalization:
            raise FrozenStateError("冻结的 normalization policy 与 Contract 不一致")
    bundle_verified: list[str] = []
    bundle = manifest.get("verifier_bundle")
    resolved_bundle_root: Path | None = None
    if schema_version in {2, FREEZE_SCHEMA_VERSION}:
        if not isinstance(bundle, dict):
            raise FrozenStateError("freeze manifest 缺少 verifier_bundle")
        bundle_root_value = bundle.get("root")
        entries = bundle.get("files")
        if not isinstance(bundle_root_value, str):
            raise FrozenStateError("verifier_bundle.root 无效")
        bundle_root = (
            resolve_manifest_path(manifest_file, manifest, bundle_root_value, portable_workspace)
            if schema_version == FREEZE_SCHEMA_VERSION
            else canonical_path(bundle_root_value)
        )
        resolved_bundle_root = bundle_root
        actual_bundle = _bundle_files(bundle_root)
        if not isinstance(entries, dict) or set(entries) != set(actual_bundle):
            raise FrozenStateError("verifier bundle 文件集合已变化")
        for label, path in actual_bundle.items():
            entry = entries.get(label)
            expected_path = (
                relative_posix_path(path, portable_workspace)
                if schema_version == FREEZE_SCHEMA_VERSION and portable_workspace is not None
                else str(path)
            )
            if not isinstance(entry, dict) or entry.get("path") != expected_path:
                raise FrozenStateError(f"verifier bundle 路径已变化: {label}")
            expected_hash = entry.get("sha256")
            if expected_hash != sha256_file(path):
                raise FrozenStateError(f"verifier bundle 文件已变化: {label}")
            bundle_verified.append(label)
    return {
        "intact": True,
        "manifest": manifest,
        "source_root": str(root),
        "revision": current_revision,
        "tree_digest": current_tree_digest,
        "verified_files": verified_files,
        "verified_verifier_files": bundle_verified,
        "resolved_files": resolved_files,
        "workspace_root": str(portable_workspace) if portable_workspace is not None else None,
        "resolved_verifier_root": str(resolved_bundle_root) if resolved_bundle_root is not None else None,
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
