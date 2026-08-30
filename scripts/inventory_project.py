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
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data[:8192]:
        return ""
    return data[:READ_LIMIT].decode("utf-8", errors="replace")


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


def _candidate_commands(manifests: list[dict[str, str]], root: Path, files: list[tuple[Path, str]]) -> tuple[list[list[str]], list[list[str]]]:
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
    if "pyproject.toml" in names or "requirements.txt" in names or any(path.endswith(".py") for path in names):
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


def inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    collected = list(iter_source_files(root))
    extension_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    language_extensions: defaultdict[str, set[str]] = defaultdict(set)
    manifests: list[dict[str, str]] = []
    tests: list[str] = []
    ci_files: list[str] = []
    entrypoints: set[str] = set()
    source_texts: list[tuple[str, str]] = []
    public_signal_paths: defaultdict[str, list[str]] = defaultdict(list)

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
        if (
            "test" in lower_relative
            or "spec" in lower_relative
            or name.lower() in {"tox.ini", "pytest.ini", "jest.config.js", "vitest.config.ts"}
        ):
            tests.append(relative)
        if (
            lower_relative.startswith(".github/workflows/")
            or lower_relative in {".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "jenkinsfile"}
        ):
            ci_files.append(relative)
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
        text = _read_text(path)
        if text and language:
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
            if re.search(r"(?i)(openapi|swagger|graphql|\.proto$|jsonschema|schema)", relative + "\n" + text[:2000]):
                public_signal_paths["schema"].append(relative)

    names = {relative: path for path, relative in collected}
    for manifest_path in ("package.json",):
        if manifest_path in names:
            package = _package_data(names[manifest_path])
            for key in ("main", "module", "browser"):
                value = package.get(key)
                if isinstance(value, str):
                    entrypoints.add(value)
            bins = package.get("bin")
            if isinstance(bins, str):
                entrypoints.add(bins)
            elif isinstance(bins, dict):
                entrypoints.update(value for value in bins.values() if isinstance(value, str))
    for relative, text in source_texts:
        if relative.endswith("pyproject.toml"):
            for match in re.finditer(r"(?m)^\s*([A-Za-z0-9_.-]+)\s*=\s*['\"]([^'\"]+)['\"]", text):
                if "script" in relative.lower() and match.group(2).endswith(".py"):
                    entrypoints.add(match.group(2))

    frameworks: dict[str, dict[str, Any]] = {}
    all_text = "\n".join(text.lower() for _, text in source_texts)
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
        if not evidence:
            continue
        actual_kind = "library" if kind == "library" else "command" if kind == "command" else "http"
        public_surfaces.append(
            {
                "kind": actual_kind,
                "confidence": "medium" if kind != "schema" else "low",
                "evidence": evidence,
                "signals": len(evidence),
            }
        )

    build_commands, test_commands = _candidate_commands(manifests, root, collected)
    return {
        "schema_version": 1,
        "root": str(root),
        "read_only": True,
        "files": {
            "total": len(collected),
            "by_extension": dict(sorted(extension_counts.items())),
        },
        "languages": [
            {
                "name": language,
                "file_count": language_counts[language],
                "extensions": sorted(language_extensions[language]),
            }
            for language in sorted(language_counts)
        ],
        "manifests": sorted(manifests, key=lambda item: item["path"]),
        "entrypoints": _path_strings(list(entrypoints)),
        "tests": _path_strings(tests),
        "ci": _path_strings(ci_files),
        "frameworks": {key: frameworks[key] for key in sorted(frameworks)},
        "possible_public_surfaces": public_surfaces,
        "build_commands": build_commands,
        "test_commands": test_commands,
        "risk_indicators": {key: risks[key] for key in sorted(risks)},
        "notes": [
            "Inventory is evidence collection only; it does not execute project code or access the network.",
            "Framework, entrypoint and public-surface findings are candidates that require Agent confirmation.",
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

