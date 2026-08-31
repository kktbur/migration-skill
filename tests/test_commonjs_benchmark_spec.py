"""Contract-level tests for the blind CommonJS-to-ESM benchmark fixture."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "commonjs-to-esm"


def load_json(name: str):
    return json.loads((CASE / name).read_text(encoding="utf-8"))


class CommonJSBenchmarkSpecTests(unittest.TestCase):
    def test_contract_declares_runtime_boundary_and_operation_evidence(self):
        contract = load_json("migration.json")
        self.assertEqual(contract["source"]["framework"], "CommonJS")
        self.assertEqual(contract["target"]["framework"], "ESM")
        surface = contract["public_surfaces"][0]
        self.assertEqual(
            {item["id"] for item in surface["operations"]},
            {"default-export", "named-export", "error-semantics"},
        )
        self.assertTrue(all(item.get("evidence") for item in surface["operations"]))

    def test_corpus_covers_every_operation_with_boundary_cases(self):
        contract = load_json("migration.json")
        corpus = load_json("parity-corpus.json")
        operations = {item["id"] for item in contract["public_surfaces"][0]["operations"]}
        cases = corpus["cases"]
        self.assertGreaterEqual(len(cases), 6)
        self.assertEqual(len({item["id"] for item in cases}), len(cases))
        self.assertTrue(all(item.get("required") is True for item in cases))
        self.assertEqual({item["operation_id"] for item in cases}, operations)
        self.assertTrue(any(item["input"].get("args") == ["张三"] for item in cases))

    def test_plan_has_three_bounded_milestones_with_rollback_and_verification(self):
        contract = load_json("migration.json")
        plan = load_json("migration-plan.json")
        milestones = plan["milestones"]
        self.assertEqual([item["id"] for item in milestones], ["M1", "M2", "M3"])
        self.assertEqual(milestones[0]["depends_on"], [])
        self.assertEqual(milestones[1]["depends_on"], ["M1"])
        self.assertEqual(milestones[2]["depends_on"], ["M2"])
        for milestone in milestones:
            for field in ("scope", "files", "expected_behavior", "acceptance", "verification_command", "rollback_boundary"):
                self.assertTrue(milestone.get(field), field)
        self.assertEqual(
            {check["id"] for check in contract["checks"]["target"]},
            {"target-m1-tests", "target-m2-tests", "target-m3-tests"},
        )

    def test_mutation_plan_targets_required_cases(self):
        contract = load_json("migration.json")
        corpus = load_json("parity-corpus.json")
        operations = {item["id"] for item in contract["public_surfaces"][0]["operations"]}
        cases = {item["id"]: item for item in corpus["cases"]}
        controls = load_json("mutation-plan.json")["negative_controls"]
        self.assertGreaterEqual(len(controls), 3)
        for control in controls:
            self.assertTrue(control["expected_case"] in cases)
            self.assertTrue(control["expected_operation"] in operations)
            self.assertTrue(control["result"])

    def test_case_is_blind_and_has_no_prebuilt_target(self):
        readme = (CASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("no ESM Target", readme)
        self.assertFalse((CASE / "generated-target").exists())


if __name__ == "__main__":
    unittest.main()
