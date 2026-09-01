"""Behavior tests for the v1.2 milestone and resume protocol."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "skills" / "migration-skill" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from advance_milestone import advance  # noqa: E402
from common import tree_digest, write_json  # noqa: E402
from evaluate_milestone import evaluate_milestone  # noqa: E402
from evaluate_migration import evaluate  # noqa: E402
from validate_plan import validate_plan  # noqa: E402
from verify_resume import verify_resume  # noqa: E402


class MigrationV12ProtocolTest(unittest.TestCase):
    def _contract(self):
        return {
            "schema_version": 2,
            "source": {
                "root": "source",
                "revision": "AUTO",
                "language": "Python",
                "framework": "CLI",
                "entrypoints": ["cli.py"],
            },
            "target": {
                "root": "target",
                "language": "Node.js",
                "framework": "CLI",
                "entrypoints": ["cli.js"],
            },
            "public_surfaces": [
                {
                    "id": "main-cli",
                    "kind": "command",
                    "required": True,
                    "source_adapter": {"kind": "harness", "argv": [sys.executable, "adapter.py"]},
                    "target_adapter": {"kind": "harness", "argv": [sys.executable, "adapter.py"]},
                    "compare": {"whole": {"mode": "json-semantic"}},
                    "evidence": ["cli.py"],
                    "confidence": "high",
                    "operations": [{"id": "invoke", "required": True, "evidence": ["cli.py"]}],
                }
            ],
            "completion_gates": {"required_check_kinds": ["test", "parity"]},
            "checks": {
                "source": [{"id": "source-tests", "kind": "test", "argv": [sys.executable, "-c", "pass"]}],
                "target": [{"id": "target-tests", "kind": "test", "argv": [sys.executable, "-c", "pass"]}],
            },
            "parity_corpus": "parity-corpus.json",
        }

    def _corpus(self):
        return {
            "schema_version": 2,
            "cases": [
                {"id": "normal", "surface_id": "main-cli", "operation_id": "invoke", "input": {"name": "Ada"}, "required": True},
                {"id": "error", "surface_id": "main-cli", "operation_id": "invoke", "input": {"name": ""}, "required": True},
                {"id": "boundary", "surface_id": "main-cli", "operation_id": "invoke", "input": {"name": "\u00e9"}, "required": True},
            ],
        }

    def _plan(self):
        return {
            "schema_version": 1,
            "milestones": [
                {"id": "M1", "name": "normal", "depends_on": [], "required_cases": ["normal"], "required_checks": ["target-tests"]},
                {"id": "M2", "name": "error", "depends_on": ["M1"], "required_cases": ["error"], "required_checks": ["target-tests"]},
                {"id": "M3", "name": "boundary", "depends_on": ["M2"], "required_cases": ["boundary"], "required_checks": ["target-tests"]},
            ],
        }

    def _freeze(self):
        return {
            "intact": True,
            "manifest": {
                "source": {"revision": "source-revision", "tree_digest": "source-tree"},
                "judge_validation": {"valid": True},
            },
        }

    def _baseline(self):
        return {
            "status": "captured_clean",
            "revision": "source-revision",
            "tree_digest": "source-tree",
            "checks": [{"id": "source-tests", "kind": "test", "status": "passed"}],
            "inherited_failures": [],
        }

    def _source_checks(self):
        return {"checks": [{"id": "source-tests", "kind": "test", "status": "passed"}]}

    def _target_checks(self):
        return {"checks": [{"id": "target-tests", "kind": "test", "status": "passed"}]}

    def _parity(self, passed_ids):
        cases = []
        for case_id in ("normal", "error", "boundary"):
            cases.append(
                {
                    "id": case_id,
                    "surface_id": "main-cli",
                    "operation_id": "invoke",
                    "required": True,
                    "passed": case_id in passed_ids,
                }
            )
        return {"status": "passed" if len(passed_ids) == 3 else "failed", "source_valid": True, "cases": cases}

    def _state(self):
        return {
            "schema_version": 2,
            "source_revision": "source-revision",
            "current_milestone": "M1",
            "completed_milestones": [],
            "protected_cases": [],
            "protected_checks": [],
            "last_accepted_checkpoint": None,
            "required_gaps": [],
        }

    def test_plan_rejects_missing_dependency_and_duplicate_case(self):
        plan = self._plan()
        self.assertEqual(validate_plan(plan, self._contract(), self._corpus()), [])
        broken = json.loads(json.dumps(plan))
        broken["milestones"][1]["depends_on"] = ["UNKNOWN"]
        broken["milestones"][0]["required_cases"].append("normal")
        errors = validate_plan(broken, self._contract(), self._corpus())
        self.assertTrue(any("依赖" in error for error in errors))
        self.assertTrue(any("重复" in error for error in errors))

    def test_milestone_gate_ignores_future_cases_but_protects_prior_proof(self):
        result = evaluate_milestone(
            self._baseline(),
            self._source_checks(),
            self._target_checks(),
            self._parity({"normal"}),
            self._contract(),
            self._corpus(),
            self._plan(),
            self._state(),
            self._freeze(),
            "M1",
        )
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["proof_set"]["cases"], ["normal"])
        self.assertEqual(result["status"], "eligible")

        state = self._state()
        state["completed_milestones"] = ["M1"]
        state["protected_cases"] = ["normal"]
        state["protected_checks"] = ["target-tests"]
        result = evaluate_milestone(
            self._baseline(),
            self._source_checks(),
            self._target_checks(),
            self._parity({"normal", "error"}),
            self._contract(),
            self._corpus(),
            self._plan(),
            state,
            self._freeze(),
            "M2",
        )
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["proof_set"]["cases"], ["error", "normal"])

        regression = evaluate_milestone(
            self._baseline(),
            self._source_checks(),
            self._target_checks(),
            self._parity({"error"}),
            self._contract(),
            self._corpus(),
            self._plan(),
            state,
            self._freeze(),
            "M2",
        )
        self.assertFalse(regression["eligible"])
        self.assertIn("protected_cases", regression["gate_failures"])

    def test_advance_uses_proof_set_monotonicity_and_keeps_rejected_state_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            (target / "cli.js").write_text("ok\n", encoding="utf-8")
            state_path = root / "state.json"
            result_path = root / "milestone-result.json"
            state = self._state()
            write_json(state_path, state)
            result = {
                "schema_version": 1,
                "artifact_type": "milestone-result-v1",
                "milestone_id": "M1",
                "eligible": True,
                "ratchet_eligible": True,
                "migration_score": 0.5,
                "proof_set": {"cases": ["normal"], "checks": ["target-tests"]},
                "target": {"revision": None, "tree_digest": tree_digest(target)},
                "required_conditions": {"all": True},
            }
            write_json(result_path, result)
            accepted = advance(state_path, result_path, "M1", target)
            self.assertEqual(accepted["status"], "accepted")
            accepted_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(accepted_state["protected_cases"], ["normal"])
            self.assertEqual(accepted_state["protected_checks"], ["target-tests"])

            before = state_path.read_text(encoding="utf-8")
            result["eligible"] = False
            result["ratchet_eligible"] = False
            write_json(result_path, result)
            rejected = advance(state_path, result_path, "M2", target)
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(before, state_path.read_text(encoding="utf-8"))

    def test_resume_is_a_pre_edit_gate_and_detects_external_target_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            (target / "cli.js").write_text("ok\n", encoding="utf-8")
            state = self._state()
            state["last_accepted_checkpoint"] = {
                "milestone_id": "M1",
                "target_revision": None,
                "target_tree_digest": tree_digest(target),
            }
            state_path = root / "state.json"
            manifest_path = root / "freeze-manifest.json"
            write_json(state_path, state)
            write_json(manifest_path, {"schema_version": 3})
            # The verifier is exercised through the CLI/module seam; the test
            # uses the dependency injection hook to keep this test offline.
            result = verify_resume(
                state_path,
                target,
                manifest_path,
                root / "resume.json",
                freeze_checker=lambda _: self._freeze(),
            )
            self.assertTrue(result["valid"], result)
            self.assertEqual(result["status"], "ready")
            (target / "cli.js").write_text("changed\n", encoding="utf-8")
            result = verify_resume(
                state_path,
                target,
                manifest_path,
                root / "resume-invalid.json",
                freeze_checker=lambda _: self._freeze(),
            )
            self.assertFalse(result["valid"])
            self.assertEqual(result["status"], "invalidated")

    def test_final_gate_requires_all_milestones_after_each_milestone_gate(self):
        target = {"root": "target", "checks": [{"id": "target-tests", "kind": "test", "status": "passed"}]}
        report = evaluate(
            self._baseline(),
            self._source_checks(),
            target,
            self._parity({"normal", "error", "boundary"}),
            self._contract(),
            self._corpus(),
            self._state(),
            self._freeze(),
            self._plan(),
        )
        self.assertEqual(report["status"], "PARTIALLY_VERIFIED")
        self.assertFalse(report["required_conditions"]["all_milestones_completed"])

        state = self._state()
        state["completed_milestones"] = ["M1", "M2", "M3"]
        state["protected_cases"] = ["normal", "error", "boundary"]
        state["protected_checks"] = ["target-tests"]
        report = evaluate(
            self._baseline(),
            self._source_checks(),
            target,
            self._parity({"normal", "error", "boundary"}),
            self._contract(),
            self._corpus(),
            state,
            self._freeze(),
            self._plan(),
        )
        self.assertEqual(report["status"], "VERIFIED")

    def test_three_milestone_ratchet_accepts_incremental_proof_and_finalizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            (target / "target.js").write_text("target\n", encoding="utf-8")
            state_path = root / "state.json"
            state = self._state()
            write_json(state_path, state)
            write_json(root / "migration-plan.json", self._plan())

            for milestone_id, passed_ids in (("M1", {"normal"}), ("M2", {"normal", "error"}), ("M3", {"normal", "error", "boundary"})):
                target_document = {"root": str(target), **self._target_checks()}
                result = evaluate_milestone(
                    self._baseline(),
                    self._source_checks(),
                    target_document,
                    self._parity(passed_ids),
                    self._contract(),
                    self._corpus(),
                    self._plan(),
                    state,
                    self._freeze(),
                    milestone_id,
                )
                self.assertTrue(result["eligible"], result)
                result_path = root / f"{milestone_id}-result.json"
                write_json(result_path, result)
                report = advance(
                    state_path,
                    result_path,
                    milestone_id,
                    target,
                    plan_path=root / "migration-plan.json",
                )
                self.assertEqual(report["status"], "accepted")
                state = json.loads(state_path.read_text(encoding="utf-8"))

                if milestone_id == "M1":
                    self.assertEqual(state["protected_cases"], ["normal"])
                elif milestone_id == "M2":
                    self.assertEqual(state["protected_cases"], ["error", "normal"])
                else:
                    self.assertEqual(state["protected_cases"], ["boundary", "error", "normal"])

            final = evaluate(
                self._baseline(),
                self._source_checks(),
                {"root": str(target), **self._target_checks()},
                self._parity({"normal", "error", "boundary"}),
                self._contract(),
                self._corpus(),
                state,
                self._freeze(),
                self._plan(),
            )
            self.assertEqual(final["status"], "VERIFIED")

    def test_milestone_regression_is_rejected_without_state_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            (target / "target.js").write_text("target\n", encoding="utf-8")
            state_path = root / "state.json"
            state = self._state()
            state["completed_milestones"] = ["M1"]
            state["protected_cases"] = ["normal"]
            state["protected_checks"] = ["target-tests"]
            write_json(state_path, state)
            result = evaluate_milestone(
                self._baseline(),
                self._source_checks(),
                {"root": str(target), **self._target_checks()},
                self._parity({"error"}),
                self._contract(),
                self._corpus(),
                self._plan(),
                state,
                self._freeze(),
                "M2",
            )
            self.assertFalse(result["eligible"])
            result_path = root / "M2-regression.json"
            write_json(result_path, result)
            before = state_path.read_text(encoding="utf-8")
            report = advance(state_path, result_path, "M2", target, plan_path=root / "migration-plan.json")
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(before, state_path.read_text(encoding="utf-8"))

    def test_v3_freeze_manifest_survives_workspace_relocation(self):
        from test_migration_scripts import MigrationScriptsTest

        fixture = MigrationScriptsTest()._prepare_frozen_fixture()
        try:
            relocated = fixture["base"].parent / ("relocated-workspace-" + fixture["base"].name)
            shutil.copytree(fixture["base"], relocated)
            manifest = json.loads((relocated / "freeze-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 3)
            self.assertEqual(manifest["path_mode"], "relative")
            self.assertTrue(all(not Path(item["path"]).is_absolute() for item in manifest["files"].values()))
            from common import verify_freeze

            verified = verify_freeze(relocated / "freeze-manifest.json")
            self.assertTrue(verified["intact"])
        finally:
            if 'relocated' in locals():
                shutil.rmtree(relocated, ignore_errors=True)
            fixture["temporary"].cleanup()


if __name__ == "__main__":
    unittest.main()
