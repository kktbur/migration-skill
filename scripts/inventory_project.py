"""Perform a read-only, deterministic inventory of a source repository."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from common import ConfigError, EXIT_INVALID, EXIT_OK, iter_source_files, write_json
except ImportError:  # pragma: no cover
    from .common import ConfigError, EXIT_INVALID, EXIT_OK, iter_source_files, write_json


EXTENSIONS = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".sql": "SQL",
    ".swift": "Swift",
}

TEXT_SUFFIXES = frozenset(
    {
        *EXTENSIONS,
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".md",
        ".rst",
        ".txt",
        ".graphql",
        ".gql",
        ".proto",
        ".lock",
    }
)

MANIFEST_NAMES = {
    "package.json": "npm",
    "package-lock.json": "npm-lock",
    "pnpm-lock.yaml": "pnpm-lock",
    "yarn.lock": "yarn-lock",
    "pyproject.toml": "Python project",
    "requirements.txt": "Python requirements",
    "Pipfile": "Pipenv",
    "poetry.lock": "Poetry lock",
    "go.mod": "Go module",
    "go.sum": "Go checksum",
    "Cargo.toml": "Cargo",
    "Cargo.lock": "Cargo lock",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle Kotlin",
    "Gemfile": "Bundler",
    "composer.json": "Composer",
    "mix.exs": "Elixir Mix",
    "pubspec.yaml": "Dart pub",
}

FRAMEWORK_PATTERNS = {
    "Flask": ("flask",),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Express": ("express",),
    "Fastify": ("fastify",),
    "Next.js": ("next",),
    "React": ("react",),
    "Vue": ("vue",),
    "Angular": ("@angular",),
    "Gin": ("gin-gonic/gin",),
    "Echo": ("labstack/echo",),
    "Spring": ("spring-boot", "org.springframework"),
    "Rails": ("rails",),
    "Axum": ("axum",),
    "Actix": ("actix-web",),
    "Koa": ("koa",),
    "NestJS": ("@nestjs",),
}

RISK_PATTERNS = {
    "database": ("sqlalchemy", "django.db", "prisma", "sequelize", "typeorm", "postgres", "mysql", "sqlite", "mongodb"),
    "background-jobs": ("celery", "rq", "bull", "sidekiq", "job_queue", "background task"),
    "message-queue": ("kafka", "rabbitmq", "amqp", "nats", "sqs"),
    "websocket": ("websocket", "socket.io", "socketio"),
    "authentication-or-oauth": ("oauth", "openid", "jwt", "passport", "authlib"),
    "network-or-external-api": ("requests", "httpx", "axios", "fetch(", "boto3", "google.cloud", "urllib"),
    "file-io": ("open(", "readfile", "writefile", "pathlib", "os.rename", "fs."),
    "system-command": ("subprocess", "os.system", "child_process", "exec(", "spawn("),
    "native-or-hardware": ("ctypes", "cffi", "pybind", "cuda", "torch", "tensorflow", "native"),
}

READ_LIMIT = 512 * 1024


def _read_text(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(READ_LIMIT)
    except OSError:
        return ""
    if b"\x00" in data[:8192]:
        return ""
    return data.decode("utf-8", errors="replace")


def _path_strings(paths: list[str]) -> list[str]:
    return sorted(set(paths), key=lambda value: (value.lower(), value))


def _manifest_record(relative: str, kind: str) -> dict[str, str]:
    return {"path": relative, "kind": kind}


def _package_data(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _toml_data(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        return {}
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _pyproject_scripts(path: Path) -> dict[str, str]:
    data = _toml_data(path)
    scripts: dict[str, str] = {}
    for section in (
        data.get("project", {}).get("scripts", {}),
        data.get("project", {}).get("gui-scripts", {}),
        data.get("tool", {}).get("poetry", {}).get("scripts", {}),
    ):
        if isinstance(section, dict):
            scripts.update(
                {str(name): str(value) for name, value in section.items() if isinstance(name, str) and isinstance(value, str)}
            )
    return scripts


def _candidate_commands(files: list[tuple[Path, str]]) -> tuple[list[list[str]], list[list[str]]]:
    build_commands: list[list[str]] = []
    test_commands: list[list[str]] = []
    names = {relative: path for path, relative in files}
    if "package.json" in names:
        package = _package_data(names["package.json"])
        scripts = package.get("scripts", {})
        if isinstance(scripts, dict):
            if "build" in scripts:
                build_commands.append(["npm", "run", "build"])
            if "test" in scripts:
                test_commands.append(["npm", "test"])
    if "pyproject.toml" in names or "requirements.txt" in names or any(path.suffix.lower() == ".py" for path, _ in files):
        test_commands.append(["python", "-m", "pytest"])
    if "go.mod" in names:
        build_commands.append(["go", "build", "./..."])
        test_commands.append(["go", "test", "./..."])
    if "Cargo.toml" in names:
        build_commands.append(["cargo", "build"])
        test_commands.append(["cargo", "test"])
    if "pom.xml" in names:
        build_commands.append(["mvn", "test"])
        test_commands.append(["mvn", "test"])
    if "Makefile" in names:
        build_commands.append(["make", "build"])
        test_commands.append(["make", "test"])
    return build_commands, test_commands


def _add_operation(
    operations: dict[tuple[str, str], dict[str, Any]],
    kind: str,
    operation_id: str,
    relative: str,
    evidence_type: str,
    line_number: int | None,
    **extra: Any,
) -> None:
    key = (kind, operation_id)
    evidence: dict[str, Any] = {"path": relative, "type": evidence_type}
    if line_number is not None:
        evidence["line"] = line_number
    item = operations.setdefault(
        key,
        {
            "id": operation_id,
            "kind": kind,
            "confidence": "medium",
            "evidence": [],
        },
    )
    if evidence not in item["evidence"]:
        item["evidence"].append(evidence)
    item.update(extra)


def _discover_operations(relative: str, text: str, operations: dict[tuple[str, str], dict[str, Any]]) -> None:
    lower_relative = relative.lower()
    route_patterns = (
        re.compile(r"(?i)@[^\n]*(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]"),
        re.compile(r"(?i)\b(?:app|router|api|server)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]"),
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern in route_patterns:
            match = pattern.search(line)
            if match:
                method, path = match.group(1).upper(), match.group(2)
                _add_operation(
                    operations,
                    "http",
                    f"{method}-{path}",
                    relative,
                    "route-definition",
                    line_number,
                    method=method,
                    path=path,
                )
        route_match = re.search(r"(?i)@[^\n]*route\s*\(\s*['\"]([^'\"]+)['\"]", line)
        if route_match:
            path = route_match.group(1)
            methods = re.findall(r"(?i)['\"](get|post|put|patch|delete)['\"]", line)
            for method in methods or ["ANY"]:
                method = method.upper()
                _add_operation(
                    operations,
                    "http",
                    f"{method}-{path}",
                    relative,
                    "route-definition",
                    line_number,
                    method=method,
                    path=path,
                )
        for match in re.finditer(r"(?i)(?:add_parser|subparsers?\.add_parser|command)\s*\(\s*['\"]([^'\"]+)['\"]", line):
            _add_operation(operations, "command", f"command:{match.group(1)}", relative, "cli-definition", line_number)
        for match in re.finditer(r"(?i)\brpc\s+(\w+)\s*\(", line):
            _add_operation(operations, "library", f"rpc:{match.group(1)}", relative, "protobuf-definition", line_number)
        for match in re.finditer(r"(?i)^\s*(\w+)\s*\([^)]*\)", line):
            if "graphql" in lower_relative or "type query" in text[: max(0, text.find(line))].lower():
                _add_operation(operations, "library", f"graphql:{match.group(1)}", relative, "graphql-definition", line_number)

    for line_number, line in enumerate(text.splitlines(), start=1):
        schema_path = any(token in lower_relative for token in ("openapi", "swagger", "schema", "graphql", ".proto"))
        path_match = re.match(r"^\s{0,8}(/[^:#\s]*):\s*$", line)
        if schema_path and path_match:
            path = path_match.group(1)
            _add_operation(operations, "http", f"PATH-{path}", relative, "schema-path", line_number, path=path, confidence="low")
        rpc_match = re.search(r"(?i)\brpc\s+(\w+)\s*\(", line)
        if rpc_match:
            _add_operation(operations, "library", f"rpc:{rpc_match.group(1)}", relative, "protobuf-definition", line_number)


def _documentation_and_schema(relative: str) -> tuple[str | None, str | None]:
    lower = relative.lower()
    if Path(relative).name.lower() in {"readme", "readme.md", "readme.rst", "contributing.md", "architecture.md"} or lower.endswith((".md", ".rst")):
        return "documentation", None
    if lower.endswith((".graphql", ".gql", ".proto")) or any(token in Path(relative).name.lower() for token in ("openapi", "swagger", "schema")):
        return None, "schema"
    return None, None


def inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    collected = list(iter_source_files(root))
    extension_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    language_extensions: defaultdict[str, set[str]] = defaultdict(set)
    manifests: list[dict[str, str]] = []
    tests: list[str] = []
    ci_files: list[str] = []
    documentation: list[str] = []
    schemas: list[str] = []
    entrypoints: set[str] = set()
    source_texts: list[tuple[str, str]] = []
    public_signal_paths: defaultdict[str, list[str]] = defaultdict(list)
    operations: dict[tuple[str, str], dict[str, Any]] = {}

    for path, relative in collected:
        suffix = path.suffix.lower()
        extension_counts[suffix or "[no extension]"] += 1
        language = EXTENSIONS.get(suffix)
        if language:
            language_counts[language] += 1
            language_extensions[language].add(suffix)
        name = path.name
        lower_relative = relative.lower()
        if name in MANIFEST_NAMES:
            manifests.append(_manifest_record(relative, MANIFEST_NAMES[name]))
        if "test" in lower_relative or "spec" in lower_relative or name.lower() in {
            "tox.ini",
            "pytest.ini",
            "jest.config.js",
            "vitest.config.ts",
        }:
            tests.append(relative)
        if lower_relative.startswith(".github/workflows/") or lower_relative in {
            ".gitlab-ci.yml",
            ".travis.yml",
            "azure-pipelines.yml",
            "jenkinsfile",
        }:
            ci_files.append(relative)
        doc_kind, schema_kind = _documentation_and_schema(relative)
        if doc_kind:
            documentation.append(relative)
        if schema_kind:
            schemas.append(relative)
        if name in {"Dockerfile", "Makefile", "manage.py"} or name.lower() in {
            "app.py",
            "main.py",
            "server.py",
            "index.js",
            "index.ts",
            "main.go",
            "main.rs",
        }:
            entrypoints.add(relative)
        if "/cmd/" in f"/{lower_relative}" and name == "main.go":
            entrypoints.add(relative)
        text = _read_text(path) if suffix in TEXT_SUFFIXES or name.lower() in {"dockerfile", "makefile", "jenkinsfile"} else ""
        if not text:
            continue
        source_texts.append((relative, text))
        route_signal = re.search(
            r"(?i)(\.route\s*\(|\.(get|post|put|patch|delete)\s*\(|HandleFunc\s*\(|router\.(GET|POST|PUT|PATCH|DELETE)\s*\()",
            text,
        )
        if route_signal:
            public_signal_paths["http"].append(relative)
        cli_signal = re.search(
            r"(?i)(ArgumentParser|argparse|commander|yargs|cobra\.Command|flag\.NewFlagSet|urfave/cli|\.cli\.command)",
            text,
        )
        if cli_signal:
            public_signal_paths["command"].append(relative)
        export_signal = re.search(r"(?m)^\s*(export\s+|module\.exports|__all__\s*=|public\s+(class|interface|fun))", text)
        if export_signal:
            public_signal_paths["library"].append(relative)
        if schema_kind or re.search(r"(?i)(openapi|swagger|graphql|jsonschema|schema)", relative + "\n" + text[:2000]):
            public_signal_paths["schema"].append(relative)
        _discover_operations(relative, text, operations)

    names = {relative: path for path, relative in collected}
    if "package.json" in names:
        package = _package_data(names["package.json"])
        for key in ("main", "module", "browser"):
            value = package.get(key)
            if isinstance(value, str):
                entrypoints.add(value)
        bins = package.get("bin")
        if isinstance(bins, str):
            entrypoints.add(bins)
        elif isinstance(bins, dict):
            entrypoints.update(value for value in bins.values() if isinstance(value, str))
        scripts = package.get("scripts", {})
        if isinstance(scripts, dict):
            for script_name in scripts:
                if isinstance(script_name, str):
                    _add_operation(operations, "command", f"script:{script_name}", "package.json", "manifest-script", None)
    if "pyproject.toml" in names:
        for script_name, target in _pyproject_scripts(names["pyproject.toml"]).items():
            entrypoint = target.split(":", 1)[0]
            entrypoints.add(entrypoint)
            _add_operation(operations, "command", f"script:{script_name}", "pyproject.toml", "manifest-script", None, target=target)

    frameworks: dict[str, dict[str, Any]] = {}
    for framework, needles in FRAMEWORK_PATTERNS.items():
        evidence = [relative for relative, text in source_texts if any(needle.lower() in text.lower() for needle in needles)]
        if evidence:
            frameworks[framework] = {"evidence": _path_strings(evidence), "confidence": "medium"}

    risks: dict[str, list[str]] = {}
    for risk, needles in RISK_PATTERNS.items():
        evidence = [relative for relative, text in source_texts if any(needle.lower() in text.lower() for needle in needles)]
        if evidence:
            risks[risk] = _path_strings(evidence)

    public_surfaces: list[dict[str, Any]] = []
    for kind in ("http", "command", "library", "schema"):
        evidence = _path_strings(public_signal_paths[kind])
        kind_operations = [
            operation for (operation_kind, _), operation in operations.items()
            if operation_kind == ("http" if kind == "schema" else kind)
        ]
        if not evidence and not kind_operations:
            continue
        actual_kind = "library" if kind == "library" else "command" if kind == "command" else "http"
        public_surfaces.append(
            {
                "id": f"{kind}-candidates",
                "kind": actual_kind,
                "confidence": "medium" if kind != "schema" else "low",
                "evidence": evidence,
                "operations": sorted(kind_operations, key=lambda item: item["id"]),
                "signals": len(evidence),
            }
        )

    build_commands, test_commands = _candidate_commands(collected)
    return {
        "schema_version": 2,
        "root": str(root),
        "read_only": True,
        "files": {"total": len(collected), "by_extension": dict(sorted(extension_counts.items()))},
        "languages": [
            {"name": language, "file_count": language_counts[language], "extensions": sorted(language_extensions[language])}
            for language in sorted(language_counts)
        ],
        "manifests": sorted(manifests, key=lambda item: item["path"]),
        "entrypoints": _path_strings(list(entrypoints)),
        "tests": _path_strings(tests),
        "ci": _path_strings(ci_files),
        "documentation": _path_strings(documentation),
        "schemas": _path_strings(schemas),
        "candidate_operations": sorted(operations.values(), key=lambda item: (item["kind"], item["id"])),
        "frameworks": {key: frameworks[key] for key in sorted(frameworks)},
        "possible_public_surfaces": public_surfaces,
        "build_commands": build_commands,
        "test_commands": test_commands,
        "risk_indicators": {key: risks[key] for key in sorted(risks)},
        "notes": [
            "Inventory is evidence collection only; it does not execute project code or access the network.",
            "Framework, entrypoint, operation and public-surface findings are candidates that require Contract confirmation.",
            "Secret-like files are excluded by the common secret ignore policy and are never emitted as evidence content.",
            "Agent inference is lower confidence than route, test, manifest or schema evidence.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Migration Skill project inventory")
    parser.add_argument("--root", required=True, help="source repository root")
    parser.add_argument("--output", required=True, help="inventory JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inventory(Path(args.root))
    write_json(args.output, report)
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
