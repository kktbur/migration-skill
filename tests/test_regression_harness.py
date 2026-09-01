"""Tests for the offline published-benchmark regression harness."""

from __future__ import annotations

import os
import shutil
import json
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.run_regression import (
    discover_runs,
    load_matrix,
    load_protocol_metadata,
    run_regression,
    validate_matrix,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "benchmarks" / "regression-matrix.json"
RUNS_ROOT = REPO_ROOT / "benchmarks" / "runs"


class RegressionHarnessTest(unittest.TestCase):
    def test_public_matrix_is_valid_and_covers_three_benchmarks(self):
        matrix = load_matrix(MATRIX_PATH)

        self.assertEqual(validate_matrix(matrix), [])
        self.assertEqual(
            [item["run_id"] for item in matrix["runs"]],
            [
                "20260831-python-cli-to-node-cli-001",
                "20260831-flask-to-fastapi-001",
                "20260831-commonjs-to-esm-001",
            ],
        )

    def test_flask_benchmark_dependencies_are_exactly_pinned(self):
        requirements_path = (
            REPO_ROOT
            / "benchmarks"
            / "cases"
            / "flask-to-fastapi"
            / "requirements.txt"
        )
        requirements = [
            line.strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertEqual(
            requirements,
            [
                "Flask==3.1.3",
                "fastapi==0.141.1",
                "httpx==0.28.1",
            ],
        )
        self.assertTrue(all("==" in requirement for requirement in requirements))

    def test_matrix_rejects_duplicate_runs_and_absolute_negative_paths(self):
        matrix = {
            "schema_version": 1,
            "runs": [
                {
                    "run_id": "same",
                    "negative_targets": [{"path": "broken", "expected_cases": ["case"]}],
                },
                {
                    "run_id": "same",
                    "negative_targets": [{"path": "C:/outside", "expected_cases": ["case"]}],
                },
            ],
        }

        errors = validate_matrix(matrix)

        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("relative" in error for error in errors))

    def test_matrix_rejects_invalid_runtime_requirement(self):
        matrix = {
            "schema_version": 1,
            "runs": [
                {
                    "run_id": "same",
                    "runtime": {"requires_node": "yes", "python_modules": ["not-valid!"]},
                    "negative_targets": [{"path": "broken", "expected_cases": ["case"]}],
                }
            ],
        }

        errors = validate_matrix(matrix)

        self.assertTrue(any("requires_node" in error for error in errors))
        self.assertTrue(any("python_modules" in error for error in errors))

    def test_discover_runs_rejects_unknown_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            runs_root = Path(temporary)
            (runs_root / "known").mkdir()

            with self.assertRaises(ValueError):
                discover_runs(runs_root, ["unknown"])

    def test_published_runs_have_the_replay_artifact_chain(self):
        matrix = load_matrix(MATRIX_PATH)
        run_paths = discover_runs(RUNS_ROOT, [item["run_id"] for item in matrix["runs"]])

        for run_path in run_paths:
            for relative in (
                "report.json",
                ".migration/baseline.json",
                ".migration/freeze-manifest.json",
                ".migration/migration.json",
                ".migration/migration-plan.json",
                ".migration/mutation-plan.json",
                ".migration/parity-corpus.json",
                ".migration/state.json",
                "source",
                "generated-target",
                "migration-skill/scripts",
            ):
                self.assertTrue((run_path / relative).exists(), f"missing {run_path.name}/{relative}")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the local replay smoke test")
    @unittest.skipIf(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        "published fixture Source test requires a UTF-8 Windows locale; CI uses the host code page",
    )
    def test_dependency_free_python_cli_run_replays_without_network(self):
        report = run_regression(
            REPO_ROOT,
            run_ids=["20260831-python-cli-to-node-cli-001"],
        )

        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(
            report["summary"],
            {"total": 1, "passed": 1, "failed": 0, "blocked": 0, "invalid": 0},
        )
        self.assertEqual(report["runs"][0]["status"], "passed")
        self.assertEqual(report["runs"][0]["evaluator"]["status"], "VERIFIED")
        self.assertTrue(report["runs"][0]["broken_target_rejection"]["passed"])
        plugin = json.loads(
            (REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["plugin_version"], plugin["version"])
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(
            report["protocol"],
            {"contract_schema": 2, "freeze_schema": 3},
        )
        self.assertEqual(report["runtime"]["python"], report["runtime"]["python_version"])
        self.assertEqual(report["runtime"]["node"], report["runtime"]["node_version"])

    def test_protocol_metadata_rejects_manifest_policy_version_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".codex-plugin").mkdir()
            (root / "docs").mkdir()
            (root / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"version": "0.2.0-rc.1"}),
                encoding="utf-8",
            )
            (root / "docs" / "plugin-compatibility.json").write_text(
                json.dumps(
                    {
                        "plugin": {"version": "0.2.0"},
                        "protocol": {"contract_schema": 2, "freeze_schema": 3},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_protocol_metadata(root)

    def test_missing_runtime_dependency_is_blocked_not_reported_as_regression(self):
        matrix = {
            "schema_version": 1,
            "runs": [
                {
                    "run_id": "20260831-python-cli-to-node-cli-001",
                    "runtime": {"python_modules": ["migration_harness_module_that_does_not_exist"]},
                    "negative_targets": [
                        {"path": "broken-target", "expected_cases": ["normal-json"]}
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            matrix_path = Path(temporary) / "matrix.json"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

            report = run_regression(
                REPO_ROOT,
                run_ids=["20260831-python-cli-to-node-cli-001"],
                matrix_path=matrix_path,
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["summary"]["blocked"], 1)
        self.assertIn(
            "runtime-requirements-unavailable:migration_harness_module_that_does_not_exist",
            report["runs"][0]["failure_reasons"],
        )


if __name__ == "__main__":
    unittest.main()
