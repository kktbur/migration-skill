"""Contract-level tests for the public Flask-to-FastAPI benchmark fixture."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "flask-to-fastapi"


def load_json(name: str):
    return json.loads((CASE / name).read_text(encoding="utf-8"))


class FlaskBenchmarkSpecTests(unittest.TestCase):
    def test_contract_declares_five_http_operations_with_evidence(self):
        contract = load_json("migration.json")
        self.assertEqual(contract["source"]["framework"], "Flask")
        self.assertEqual(contract["target"]["framework"], "FastAPI")
        surface = contract["public_surfaces"][0]
        operations = surface["operations"]
        self.assertEqual(
            {item["id"] for item in operations},
            {
                "GET-/health",
                "GET-/users/:id",
                "POST-/users",
                "DELETE-/users/:id",
                "GET-/search",
            },
        )
        self.assertTrue(all(item.get("evidence") for item in operations))

    def test_corpus_has_independent_cases_for_every_operation(self):
        contract = load_json("migration.json")
        corpus = load_json("parity-corpus.json")
        surface = contract["public_surfaces"][0]
        operation_ids = {item["id"] for item in surface["operations"]}
        cases = corpus["cases"]
        self.assertGreaterEqual(len(cases), 15)
        self.assertLessEqual(len(cases), 25)
        self.assertEqual(len({item["id"] for item in cases}), len(cases))
        self.assertTrue(all(item["required"] for item in cases))
        self.assertEqual({item["operation_id"] for item in cases}, operation_ids)

    def test_plan_is_three_bounded_milestones(self):
        plan = load_json("migration-plan.json")
        milestones = plan["milestones"]
        self.assertEqual([item["id"] for item in milestones], ["M1", "M2", "M3"])
        self.assertEqual(milestones[0]["depends_on"], [])
        self.assertEqual(milestones[1]["depends_on"], ["M1"])
        self.assertEqual(milestones[2]["depends_on"], ["M2"])
        self.assertTrue(all(item["required_cases"] for item in milestones))
        self.assertTrue(all(item["required_checks"] for item in milestones))

    def test_case_is_blind_and_has_no_prebuilt_target(self):
        readme = (CASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("no FastAPI Target", readme)
        self.assertFalse((CASE / "generated-target").exists())


if __name__ == "__main__":
    unittest.main()
