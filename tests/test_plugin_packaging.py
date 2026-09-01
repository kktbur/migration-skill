"""Tests for the skills-only Plugin distribution boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL = ROOT / "skills" / "migration-skill"
MANIFEST_PATH = ROOT / ".codex-plugin" / "plugin.json"
COMPATIBILITY_PATH = ROOT / "docs" / "plugin-compatibility.json"
ADR_PATH = ROOT / "docs" / "adr" / "0001-plugin-distribution.md"


class PluginPackagingTest(unittest.TestCase):
    def test_manifest_is_skills_only_and_points_at_canonical_skill(self):
        self.assertTrue(MANIFEST_PATH.is_file())
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "migration-skill")
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)

        interface = manifest["interface"]
        for field in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "capabilities",
            "defaultPrompt",
        ):
            self.assertIn(field, interface)
        self.assertIsInstance(interface["defaultPrompt"], list)
        self.assertTrue(interface["defaultPrompt"])

    def test_raw_skill_is_self_contained_under_canonical_path(self):
        self.assertTrue((CANONICAL_SKILL / "SKILL.md").is_file())
        self.assertTrue((CANONICAL_SKILL / "agents" / "openai.yaml").is_file())
        for name in (
            "behavior-contract.md",
            "migration-workflow.md",
            "post-v1-roadmap.md",
            "safety.md",
            "upstream-lineage.md",
            "verification.md",
        ):
            self.assertTrue((CANONICAL_SKILL / "references" / name).is_file(), name)
        for name in (
            "advance_milestone.py",
            "capture_baseline.py",
            "common.py",
            "compare_results.py",
            "evaluate_migration.py",
            "evaluate_milestone.py",
            "freeze_contract.py",
            "inventory_project.py",
            "run_checks.py",
            "run_parity.py",
            "validate_contract.py",
            "validate_judge.py",
            "validate_plan.py",
            "validate_skill.py",
            "verify_resume.py",
        ):
            self.assertTrue((CANONICAL_SKILL / "scripts" / name).is_file(), name)

        self.assertFalse((ROOT / "SKILL.md").exists())
        self.assertFalse((ROOT / "scripts").exists())

    def test_plugin_compatibility_policy_is_machine_readable(self):
        self.assertTrue(COMPATIBILITY_PATH.is_file())
        policy = json.loads(COMPATIBILITY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(policy["plugin"]["name"], "migration-skill")
        self.assertEqual(policy["plugin"]["version"], "0.2.0")
        self.assertEqual(policy["protocol"]["contract_schema"], 2)
        self.assertEqual(policy["protocol"]["freeze_schema"], 3)
        self.assertTrue(policy["in_progress_migration"]["verify_frozen_bundle_before_use"])
        self.assertTrue(policy["in_progress_migration"]["plugin_update_cannot_replace_bundle"])
        self.assertEqual(policy["lifecycle_validation"]["host_session_checks"], "manual-required")
        self.assertEqual(policy["lifecycle_validation"]["host_execution_default"], "disabled")

    def test_adr_covers_lifecycle_and_frozen_verifier_boundary(self):
        self.assertTrue(ADR_PATH.is_file())
        text = ADR_PATH.read_text(encoding="utf-8").lower()
        for phrase in (
            "fresh install",
            "upgrade",
            "rollback",
            "uninstall",
            "contract schema",
            "freeze schema",
            "frozen verifier",
            "mcp",
            "raw skill",
        ):
            self.assertIn(phrase, text)

    def test_lifecycle_validation_assets_are_published_without_host_side_effects(self):
        lifecycle_root = ROOT / "tests" / "plugin_lifecycle"
        for name in (
            "fresh-install.md",
            "upgrade.md",
            "rollback.md",
            "uninstall-reinstall.md",
            "lifecycle_support.py",
            "run_host_lifecycle.py",
            "test_lifecycle.py",
        ):
            self.assertTrue((lifecycle_root / name).is_file(), name)
        self.assertTrue((ROOT / "docs" / "plugin-lifecycle-test-report.md").is_file())
        self.assertTrue((lifecycle_root / "marketplace" / ".agents" / "plugins" / "marketplace.json").is_file())


if __name__ == "__main__":
    unittest.main()
