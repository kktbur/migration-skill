"""Offline and host-probe tests for the Migration Skill Plugin lifecycle."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TEST_ROOT.parent
SCRIPT_ROOT = REPO_ROOT / "skills" / "migration-skill" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from common import FrozenStateError, sha256_file, verify_freeze, verify_verifier_bundle  # noqa: E402
from verify_resume import verify_resume  # noqa: E402
from plugin_lifecycle.lifecycle_support import (  # noqa: E402
    BENCHMARK_ROOT,
    PLUGIN_ROOT,
    copy_benchmark_run,
    file_snapshot,
    installed_verifier_root,
    model_install_historical_verifier,
    model_install_plugin,
    stage_local_marketplace,
    user_migration_snapshot,
)
from plugin_lifecycle.run_host_lifecycle import (  # noqa: E402
    classify_host_error,
    run_host_lifecycle,
)


class PluginLifecycleTest(unittest.TestCase):
    def test_local_marketplace_stages_a_discoverable_skills_only_plugin(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = stage_local_marketplace(Path(temporary))
            marketplace = json.loads(staged["marketplace_file"].read_text(encoding="utf-8"))
            entry = marketplace["plugins"][0]
            self.assertEqual(entry["name"], "migration-skill")
            self.assertEqual(entry["source"]["source"], "local")
            self.assertEqual(entry["source"]["path"], "./plugins/migration-skill")
            manifest = json.loads((staged["plugin_root"] / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "migration-skill")
            self.assertEqual(manifest["version"], "0.2.0")
            self.assertEqual(manifest["skills"], "./skills/")
            self.assertTrue((staged["plugin_root"] / "skills" / "migration-skill" / "SKILL.md").is_file())
            self.assertFalse((staged["plugin_root"] / ".migration").exists())

    def test_model_fresh_install_does_not_create_user_migration_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = stage_local_marketplace(Path(temporary) / "stage")
            installed = model_install_plugin(staged["plugin_root"], Path(temporary) / "installed")
            self.assertTrue((installed / ".codex-plugin" / "plugin.json").is_file())
            self.assertTrue((installed / "skills" / "migration-skill" / "SKILL.md").is_file())
            self.assertFalse((installed / ".migration").exists())

    def test_published_raw_benchmark_is_verified_and_rejects_broken_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = copy_benchmark_run(Path(temporary) / "run")
            report = json.loads((run / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["verification"]["final_verdict"], "VERIFIED")
            self.assertEqual(report["negative_evidence"]["status"], "failed")
            self.assertTrue(verify_freeze(run / ".migration" / "freeze-manifest.json")["intact"])

    def _benchmark_resume_fixture(self, temporary: str) -> tuple[Path, Path, Path, Path, Path, Path]:
        root = Path(temporary)
        run = copy_benchmark_run(root / "run")
        install_root = root / "installed"
        compatible_bundle = model_install_historical_verifier(run, install_root, "0.2.0")
        state = run / ".migration" / "state.json"
        target = run / "generated-target"
        manifest = run / ".migration" / "freeze-manifest.json"
        return run, install_root, compatible_bundle, state, target, manifest

    def test_upgrade_verifier_mismatch_invalidates_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, install_root, compatible, state, target, manifest = self._benchmark_resume_fixture(temporary)
            ready = verify_resume(
                state,
                target,
                manifest,
                Path(temporary) / "resume-compatible.json",
                verifier_root=compatible,
            )
            self.assertTrue(ready["valid"], ready)

            incompatible = installed_verifier_root(install_root, "0.2.1-test")
            incompatible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(compatible, incompatible)
            common_path = incompatible / "common.py"
            common_path.write_text(common_path.read_text(encoding="utf-8") + "\n# incompatible test upgrade\n", encoding="utf-8")
            invalidated = verify_resume(
                state,
                target,
                manifest,
                Path(temporary) / "resume-upgrade-invalid.json",
                verifier_root=incompatible,
            )
            self.assertFalse(invalidated["valid"])
            self.assertEqual(invalidated["reason"], "verifier-bundle-mismatch")
            self.assertTrue(invalidated["freeze_intact"])

    def test_rollback_restores_compatible_bundle_without_mutating_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, install_root, compatible, state, target, manifest = self._benchmark_resume_fixture(temporary)
            before = user_migration_snapshot(run)
            incompatible = installed_verifier_root(install_root, "0.2.1-test")
            incompatible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(compatible, incompatible)
            (incompatible / "compare_results.py").write_text(
                (incompatible / "compare_results.py").read_text(encoding="utf-8") + "\n# rollback test\n",
                encoding="utf-8",
            )
            shutil.rmtree(incompatible.parent.parent)
            restored = verify_resume(
                state,
                target,
                manifest,
                Path(temporary) / "resume-rollback.json",
                verifier_root=compatible,
            )
            self.assertTrue(restored["valid"], restored)
            self.assertEqual(before, user_migration_snapshot(run))

    def test_uninstall_and_reinstall_preserve_user_evidence_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, install_root, compatible, state, target, manifest = self._benchmark_resume_fixture(temporary)
            before = user_migration_snapshot(run)
            compatible_backup = Path(temporary) / "compatible-verifier-backup"
            shutil.copytree(compatible, compatible_backup)
            installed_plugin = install_root / "migration-skill"
            shutil.rmtree(installed_plugin)
            self.assertEqual(before, user_migration_snapshot(run))
            restored = installed_verifier_root(install_root, "0.2.0")
            restored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(compatible_backup, restored)
            self.assertTrue(verify_resume(
                state,
                target,
                manifest,
                Path(temporary) / "resume-reinstall.json",
                verifier_root=restored,
            )["valid"])
            self.assertEqual(before, user_migration_snapshot(run))

    def test_active_verifier_bundle_comparison_is_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = copy_benchmark_run(Path(temporary) / "run")
            manifest = json.loads((run / ".migration" / "freeze-manifest.json").read_text(encoding="utf-8"))
            active = Path(temporary) / "active"
            shutil.copytree(run / "migration-skill" / "scripts", active)
            self.assertTrue(verify_verifier_bundle(manifest, active)["intact"])
            (active / "evaluate_migration.py").write_text(
                (active / "evaluate_migration.py").read_text(encoding="utf-8") + "\n# mismatch\n",
                encoding="utf-8",
            )
            with self.assertRaises(FrozenStateError):
                verify_verifier_bundle(manifest, active)

    def test_host_probe_default_is_manual_only_and_does_not_execute_codex(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_host_lifecycle(
                PLUGIN_ROOT,
                root / "marketplace",
                root / "host-probe.json",
                codex_command="definitely-not-run",
            )
            self.assertEqual(report["status"], "not_requested")
            self.assertEqual(report["checks"]["fresh_install"]["status"], "manual_required")
            self.assertTrue((root / "marketplace" / ".agents" / "plugins" / "marketplace.json").is_file())

    def test_host_probe_classifies_missing_home_without_exposing_values(self):
        self.assertEqual(classify_host_error("Error: failed to resolve CODEX_HOME / Could not find home directory"), "codex-home-unresolved")


if __name__ == "__main__":
    unittest.main()
