"""Offline helpers for repeatable Plugin lifecycle model tests.

The real Codex host owns installation caches and session discovery.  These
helpers deliberately model only the filesystem boundary in a temporary
directory so unit tests can prove that Plugin lifecycle actions do not mutate
user migration evidence.  They never install into the user's Codex home.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT
BENCHMARK_ROOT = REPO_ROOT / "benchmarks" / "runs" / "20260831-python-cli-to-node-cli-001"
MARKETPLACE_TEMPLATE = Path(__file__).resolve().parent / "marketplace" / ".agents" / "plugins" / "marketplace.json"


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def copy_plugin_package(source: Path, destination: Path) -> Path:
    """Copy only the root Plugin package, not benchmarks or test fixtures."""

    source = source.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    for relative in (Path(".codex-plugin"), Path("skills")):
        source_path = source / relative
        if not source_path.is_dir():
            raise ValueError(f"Plugin package is incomplete: {source_path}")
        shutil.copytree(
            source_path,
            destination / relative,
            ignore=_copy_ignore,
        )
    return destination


def stage_local_marketplace(workspace: Path, plugin_source: Path = PLUGIN_ROOT) -> dict[str, Path]:
    """Create an isolated local marketplace containing the current Plugin."""

    workspace = workspace.resolve()
    marketplace_root = workspace / "marketplace"
    marketplace_root.mkdir(parents=True, exist_ok=False)
    plugin_root = copy_plugin_package(plugin_source, marketplace_root / "plugins" / "migration-skill")
    marketplace_file = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    marketplace_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MARKETPLACE_TEMPLATE, marketplace_file)
    return {
        "marketplace_root": marketplace_root,
        "marketplace_file": marketplace_file,
        "plugin_root": plugin_root,
    }


def model_install_plugin(
    staged_plugin: Path,
    install_root: Path,
    version: str = "0.2.0",
) -> Path:
    """Model a versioned Plugin cache entry without touching Codex config."""

    destination = install_root / "migration-skill" / version
    return copy_plugin_package(staged_plugin, destination)


def model_install_historical_verifier(
    benchmark_root: Path,
    install_root: Path,
    version: str = "0.2.0",
) -> Path:
    """Represent the verifier shipped with the published benchmark snapshot."""

    source = benchmark_root / "migration-skill" / "scripts"
    destination = install_root / "migration-skill" / version / "skills" / "migration-skill" / "scripts"
    if not source.is_dir():
        raise ValueError(f"benchmark verifier snapshot is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=_copy_ignore)
    return destination


def copy_benchmark_run(destination: Path) -> Path:
    """Copy a published run into a temporary workspace for lifecycle tests."""

    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"benchmark destination already exists: {destination}")
    shutil.copytree(BENCHMARK_ROOT, destination, ignore=_copy_ignore)
    return destination


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_snapshot(root: Path) -> dict[str, str]:
    """Return a content snapshot suitable for proving lifecycle isolation."""

    root = root.resolve()
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result[path.relative_to(root).as_posix()] = digest.hexdigest()
    return result


def user_migration_snapshot(run_root: Path) -> dict[str, dict[str, str]]:
    return {
        name: file_snapshot(run_root / name)
        for name in ("source", "generated-target", ".migration")
    }


def installed_verifier_root(install_root: Path, version: str) -> Path:
    return install_root / "migration-skill" / version / "skills" / "migration-skill" / "scripts"
