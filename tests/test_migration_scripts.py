"""Stdlib-only tests for the deterministic Migration Skill helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from advance_milestone import advance  # noqa: E402
from capture_baseline import capture  # noqa: E402
from common import (  # noqa: E402
    FrozenStateError,
    _safe_env,
    compare_values,
    run_check,
    tree_digest,
    validate_variable_name,
    verify_freeze,
    write_json,
)
from compare_results import compare  # noqa: E402
from evaluate_migration import _new_source_regressions, evaluate  # noqa: E402
from freeze_contract import freeze  # noqa: E402
from inventory_project import inventory  # noqa: E402
from run_checks import run_checks  # noqa: E402
from run_parity import run_parity  # noqa: E402
from validate_contract import validate_documents  # noqa: E402
from validate_judge import validate_artifact, validate_judge  # noqa: E402


class MigrationScriptsTest(unittest.TestCase):
    def _v2_contract(self, source_checks=None, target_checks=None):
        return {
            "schema_version": 2,
            "source": {
                "root": ".",
                "revision": "AUTO",
                "language": "Python",
                "framework": "CLI",
                "entrypoints": ["cli.py"],
            },
            "target": {
                "root": "../target",
                "language": "Node.js",
                "framework": "CLI",
                "entrypoints": ["cli.js"],
            },
            "environment": {"set": {"NODE_ENV": "test"}},
            "public_surfaces": [
                {
                    "id": "main-cli",
                    "kind": "command",
                    "required": True,
                    "source_adapter": {
                        "kind": "harness",
                        "argv": [sys.executable, "adapter.py"],
                    },
                    "target_adapter": {
                        "kind": "harness",
                        "argv": [sys.executable, "adapter.py"],
                    },
                    "compare": {"whole": {"mode": "json-semantic"}},
                    "evidence": ["cli.py", "adapter.py", "test_cli.py"],
                    "confidence": "high",
                    "operations": [
                        {"id": "hello", "required": True, "evidence": ["cli.py", "test_cli.py"]},
                        {"id": "boundary-empty", "required": True, "evidence": ["cli.py"]},
                        {"id": "error", "required": True, "evidence": ["cli.py", "test_cli.py"]},
                    ],
                }
            ],
            "completion_gates": {"required_check_kinds": ["test"]},
            "checks": {
                "source": source_checks or [],
                "target": target_checks or [],
            },
            "parity_corpus": "parity-corpus.json",
        }

    def _v2_corpus(self):
        return {
            "schema_version": 2,
            "cases": [
                {
                    "id": "hello",
                    "surface_id": "main-cli",
                    "operation_id": "hello",
                    "input": {"argv": ["--name", "Ada"]},
                    "required": True,
                },
                {
                    "id": "boundary-empty",
                    "surface_id": "main-cli",
                    "operation_id": "boundary-empty",
                    "input": {"argv": ["--name", ""]},
                    "required": True,
                },
                {
                    "id": "error",
                    "surface_id": "main-cli",
                    "operation_id": "error",
                    "input": {"argv": ["--unknown"]},
                    "required": True,
                },
            ],
        }

    def _checks(self):
        source = [
            {"id": "source-test", "kind": "test", "argv": [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_cli.py"]}
        ]
        target = [dict(source[0], id="target-test")]
        return source, target

    def _write_cli_fixture(self, base: Path):
        source = base / "source"
        target = base / "target"
        source.mkdir()
        target.mkdir()
        source_cli = (
            "import json, sys\n"
            "args = sys.argv[1:]\n"
            "if len(args) == 2 and args[0] == '--name':\n"
            "    if not args[1]:\n"
            "        print(json.dumps({'error': 'name required'}, sort_keys=True))\n"
            "        raise SystemExit(2)\n"
            "    print(json.dumps({'greeting': 'hello ' + args[1]}, sort_keys=True))\n"
            "    raise SystemExit(0)\n"
            "print(json.dumps({'error': 'invalid arguments'}, sort_keys=True))\n"
            "raise SystemExit(2)\n"
        )
        target_cli = (
            "import json, sys\n"
            "args = sys.argv[1:]\n"
            "if len(args) == 2 and args[0] == '--name':\n"
            "    if not args[1]:\n"
            "        print(json.dumps({'error': 'name required'}, sort_keys=True))\n"
            "        raise SystemExit(2)\n"
            "    print(json.dumps({'greeting': 'hello ' + args[1]}, sort_keys=True))\n"
            "    raise SystemExit(0)\n"
            "print(json.dumps({'error': 'invalid arguments'}, sort_keys=True))\n"
            "raise SystemExit(2)\n"
        )
        adapter = (
            "import json, subprocess, sys\n"
            "request = json.load(sys.stdin)\n"
            "argv = request['input']['argv']\n"
            "completed = subprocess.run([sys.executable, 'cli.py', *argv], capture_output=True, text=True, check=False)\n"
            "try:\n"
            "    output = json.loads(completed.stdout)\n"
            "except json.JSONDecodeError:\n"
            "    output = completed.stdout\n"
            "print(json.dumps({'status': 'passed', 'observed': {'exit_code': completed.returncode, 'stdout': output}}, sort_keys=True))\n"
        )
        test_code = (
            "import json, subprocess, sys, unittest\n"
            "class TestCli(unittest.TestCase):\n"
            "    def test_hello(self):\n"
            "        result = subprocess.run([sys.executable, 'cli.py', '--name', 'Ada'], capture_output=True, text=True, check=False)\n"
            "        self.assertEqual(result.returncode, 0)\n"
            "        self.assertEqual(json.loads(result.stdout), {'greeting': 'hello Ada'})\n"
            "if __name__ == '__main__': unittest.main()\n"
        )
        (source / "cli.py").write_text(source_cli, encoding="utf-8")
        (target / "cli.py").write_text(target_cli, encoding="utf-8")
        for root in (source, target):
            (root / "adapter.py").write_text(adapter, encoding="utf-8")
            (root / "test_cli.py").write_text(test_code, encoding="utf-8")
        source_checks, target_checks = self._checks()
        contract = self._v2_contract(source_checks, target_checks)
        corpus = self._v2_corpus()
        spec_dir = base / "spec"
        spec_dir.mkdir()
        contract_path = spec_dir / "migration.json"
        corpus_path = spec_dir / "parity-corpus.json"
        write_json(contract_path, contract)
        write_json(corpus_path, corpus)
        return source, target, contract, corpus, contract_path, corpus_path

    def _prepare_frozen_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        source, target, contract, corpus, contract_path, corpus_path = self._write_cli_fixture(base)
        positive_path = base / "positive.json"
        negative_path = base / "negative.json"
        source_parity = run_parity(source, contract, corpus, "source")
        positive = compare(source_parity, source_parity, contract, corpus)
        write_json(positive_path, positive)
        original_target = (target / "cli.py").read_text(encoding="utf-8")
        (target / "cli.py").write_text(original_target.replace("'hello ' + args[1]", "'goodbye ' + args[1]"), encoding="utf-8")
        negative_parity = run_parity(target, contract, corpus, "target")
        negative = compare(
            source_parity,
            negative_parity,
            contract,
            corpus,
            expect_mismatch=True,
            expected_cases={"hello"},
        )
        write_json(negative_path, negative)
        (target / "cli.py").write_text(original_target, encoding="utf-8")
        plan_path = base / "mutation-plan.json"
        write_json(
            plan_path,
            {
                "schema_version": 1,
                "negative_controls": [
                    {
                        "mutation_id": "change-greeting",
                        "expected_case": "hello",
                        "expected_operation": "hello",
                        "result": "negative.json",
                    }
                ],
            },
        )
        judge_path = base / "judge-validation.json"
        judge = validate_judge(positive_path, plan_path, judge_path, source_root=source)
        self.assertTrue(judge["valid"], judge)
        manifest_path = base / "freeze-manifest.json"
        verifier_root = base / "verifier"
        shutil.copytree(SCRIPT_ROOT, verifier_root)
        manifest = freeze(
            source,
            contract_path,
            corpus_path,
            verifier_root / "evaluate_migration.py",
            manifest_path,
            judge_path,
            verifier_root,
        )
        baseline = capture(source, contract, "source")
        source_checks = run_checks(source, contract, "source", {}, 20000)
        target_checks = run_checks(target, contract, "target", {}, 20000)
        target_parity = run_parity(target, contract, corpus, "target")
        parity = compare(source_parity, target_parity, contract, corpus)
        state = {
            "source_revision": manifest["source"]["revision"],
            "current_milestone": "M001",
            "completed_milestones": [],
            "last_accepted_checkpoint": None,
            "required_gaps": [],
        }
        freeze_result = {"intact": True, "manifest": manifest}
        return {
            "temporary": temporary,
            "base": base,
            "source": source,
            "target": target,
            "contract": contract,
            "corpus": corpus,
            "contract_path": contract_path,
            "corpus_path": corpus_path,
            "baseline": baseline,
            "manifest": manifest,
            "manifest_path": manifest_path,
            "judge_path": judge_path,
            "source_checks": source_checks,
            "target_checks": target_checks,
            "parity": parity,
            "state": state,
            "freeze": freeze_result,
        }

    def test_environment_is_minimal_and_explicit_nonsecret_values_work(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-leak", "NODE_ENV": "parent"}, clear=False):
            environment = _safe_env()
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("GITHUB_TOKEN", environment)
            self.assertIn("PATH", {key.upper() for key in environment})
            self.assertEqual(_safe_env({"inherit": ["NODE_ENV"]})["NODE_ENV"], "parent")
            self.assertEqual(_safe_env({"set": {"NODE_ENV": "test"}})["NODE_ENV"], "test")
            with self.assertRaises(ValueError):
                _safe_env({"inherit": ["AWS_SECRET_ACCESS_KEY"]})
            with self.assertRaises(ValueError):
                validate_variable_name("OPENAI_API_KEY", "--var")

            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = run_check(
                    root,
                    {
                        "id": "env",
                        "argv": [sys.executable, "-c", "import os; print(os.environ.get('OPENAI_API_KEY', 'missing'))"],
                    },
                )
                self.assertEqual(result["status"], "passed")
                self.assertEqual(result["stdout"].strip(), "missing")

    def test_tree_digest_ignores_secret_files_and_streams_generic_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=secret-one\n", encoding="utf-8")
            (root / "credentials.json").write_text('{"token":"secret-one"}\n', encoding="utf-8")
            (root / "cert.pem").write_text("secret-one\n", encoding="utf-8")
            before = tree_digest(root)
            (root / ".env").write_text("OPENAI_API_KEY=secret-two\n", encoding="utf-8")
            (root / "credentials.json").write_text('{"token":"secret-two"}\n', encoding="utf-8")
            (root / "cert.pem").write_text("secret-two\n", encoding="utf-8")
            self.assertEqual(before, tree_digest(root))

    def test_inventory_detects_docs_schema_pyproject_and_operations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text("from flask import Flask\n@app.get('/health')\ndef health(): pass\n", encoding="utf-8")
            (root / "README.md").write_text("GET /health\n", encoding="utf-8")
            (root / "openapi.yaml").write_text("paths:\n  /health:\n    get:\n      responses: {}\n", encoding="utf-8")
            (root / "schema.graphql").write_text("type Query { health: Boolean }\n", encoding="utf-8")
            (root / "service.proto").write_text("service API { rpc Health (Request) returns (Response); }\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project.scripts]\nhello = 'pkg.cli:main'\n", encoding="utf-8")
            report = inventory(root)
            self.assertIn("README.md", report["documentation"])
            self.assertIn("openapi.yaml", report["schemas"])
            self.assertIn("pkg.cli", report["entrypoints"])
            operation_ids = {item["id"] for item in report["candidate_operations"]}
            self.assertIn("GET-/health", operation_ids)
            self.assertIn("PATH-/health", operation_ids)
            self.assertTrue(any(item["id"] == "script:hello" for item in report["candidate_operations"]))

    def test_contract_validation_v2_operations_environment_and_invalid_inputs(self):
        source, target, contract, corpus, _, _ = self._write_cli_fixture(Path(tempfile.mkdtemp()))
        try:
            self.assertEqual(validate_documents(contract, corpus), [])
            duplicate = json.loads(json.dumps(contract))
            duplicate["public_surfaces"][0]["operations"].append(
                json.loads(json.dumps(duplicate["public_surfaces"][0]["operations"][0]))
            )
            self.assertTrue(any("重复" in error for error in validate_documents(duplicate, corpus)))
            missing_operation_case = json.loads(json.dumps(corpus))
            missing_operation_case["cases"] = missing_operation_case["cases"][:1]
            self.assertTrue(any("required operation" in error for error in validate_documents(contract, missing_operation_case)))
            invalid_compare = json.loads(json.dumps(contract))
            invalid_compare["public_surfaces"][0]["compare"] = {"mode": "json-semantic"}
            self.assertTrue(validate_documents(invalid_compare, corpus))
            invalid_env = json.loads(json.dumps(contract))
            invalid_env["environment"] = {"inherit": ["OPENAI_API_KEY"]}
            self.assertTrue(any("Secret" in error for error in validate_documents(invalid_env, corpus)))
            invalid_argv = json.loads(json.dumps(contract))
            invalid_argv["public_surfaces"][0]["source_adapter"]["argv"] = "python adapter.py"
            self.assertTrue(any("argv" in error for error in validate_documents(invalid_argv, corpus)))
        finally:
            shutil.rmtree(source.parent, ignore_errors=True)

    def test_run_checks_success_failure_timeout_and_output_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = {
                "checks": [
                    {"id": "pass", "kind": "test", "argv": [sys.executable, "-c", "print('ok')"]},
                    {"id": "failure", "kind": "test", "required": False, "argv": [sys.executable, "-c", "raise SystemExit(3)"]},
                    {"id": "large", "kind": "static", "argv": [sys.executable, "-c", "print('x' * 100)" ]},
                ]
            }
            report = run_checks(root, spec, "source", {}, 10)
            statuses = {item["id"]: item for item in report["results"]}
            self.assertEqual(statuses["pass"]["status"], "passed")
            self.assertEqual(statuses["failure"]["status"], "failed")
            self.assertTrue(statuses["large"]["stdout_truncated"])
            self.assertTrue(report["summary"]["all_required_passed"])
            timeout = run_check(
                root,
                {"id": "timeout", "argv": [sys.executable, "-c", "import time; time.sleep(0.4)"], "timeout_seconds": 0.05},
            )
            self.assertEqual(timeout["status"], "timeout")
            baseline = capture(
                root,
                {"checks": [{"id": "timeout", "kind": "test", "argv": [sys.executable, "-c", "import time; time.sleep(0.4)"], "timeout_seconds": 0.05}]},
                "source",
            )
            self.assertEqual(baseline["status"], "capture_failed")

    def test_comparators_apply_normalization_and_preserve_json_types(self):
        self.assertTrue(compare_values("a\r\nb  \r\n", "a\nb\n", "exact", ["crlf-to-lf", "trim-trailing-whitespace"]))
        self.assertTrue(compare_values("a\r\nb  \r\n", "a\nb\n", "text-normalized"))
        self.assertTrue(compare_values('{"b": 2, "a": 1}', {"a": 1, "b": 2}, "json-semantic"))
        self.assertFalse(compare_values({"a": 1}, {"a": "1"}, "json-semantic"))
        self.assertFalse(compare_values({"a": None}, {}, "json-semantic"))

    def test_parity_runner_and_targeted_negative_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, target, contract, corpus, _, _ = self._write_cli_fixture(base)
            source_result = run_parity(source, contract, corpus, "source")
            target_result = run_parity(target, contract, corpus, "target")
            self.assertEqual(source_result["status"], "passed")
            self.assertEqual(target_result["status"], "passed")
            self.assertEqual(source_result["summary"]["passed"], 3)
            original = (target / "cli.py").read_text(encoding="utf-8")
            (target / "cli.py").write_text(original.replace("'hello ' + args[1]", "'goodbye ' + args[1]"), encoding="utf-8")
            broken = run_parity(target, contract, corpus, "target")
            negative = compare(source_result, broken, contract, corpus, expect_mismatch=True, expected_cases={"hello"})
            self.assertEqual(negative["status"], "negative_control_passed")
            self.assertEqual(negative["summary"]["detected_mismatch_cases"], ["hello"])

    def test_validate_judge_rejects_fake_or_unscoped_negative_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            positive = base / "positive.json"
            negative = base / "negative.json"
            plan = base / "plan.json"
            output = base / "judge.json"
            write_json(positive, {"status": "passed", "passed": True, "summary": {"required_failed": []}, "cases": []})
            write_json(
                negative,
                {
                    "status": "negative_control_passed",
                    "passed": True,
                    "negative_control": True,
                    "negative_control_scoped": False,
                    "cases": [{"id": "health", "required": True, "passed": False}],
                },
            )
            write_json(
                plan,
                {
                    "schema_version": 1,
                    "negative_controls": [{"mutation_id": "bad", "expected_case": "health", "result": "negative.json"}],
                },
            )
            artifact = validate_judge(positive, plan, output)
            self.assertFalse(artifact["valid"])
            self.assertTrue(any(item["reason"] == "negative-control-is-not-scoped" for item in artifact["negative_controls"]))
            self.assertTrue(validate_artifact(artifact))

    def test_freeze_validates_judge_and_entire_verifier_bundle(self):
        fixture = self._prepare_frozen_fixture()
        try:
            self.assertTrue(verify_freeze(fixture["manifest_path"])["intact"])
            with self.assertRaises(FrozenStateError):
                tampered = json.loads(fixture["contract_path"].read_text(encoding="utf-8"))
                tampered["target"]["framework"] = "tampered"
                write_json(fixture["contract_path"], tampered)
                verify_freeze(fixture["manifest_path"])
            original_contract = json.loads(fixture["contract_path"].read_text(encoding="utf-8"))
            original_contract["target"]["framework"] = "CLI"
            write_json(fixture["contract_path"], original_contract)
            (fixture["base"] / "verifier" / "common.py").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(FrozenStateError):
                verify_freeze(fixture["manifest_path"])
        finally:
            fixture["temporary"].cleanup()

    def test_baseline_inherited_failure_is_capture_success_and_strict_is_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = {"checks": [{"id": "inherited", "kind": "test", "argv": [sys.executable, "-c", "raise SystemExit(3)"]}]}
            report = capture(root, spec, "source")
            self.assertEqual(report["status"], "captured_with_inherited_failures")
            self.assertEqual(report["inherited_failures"], ["inherited"])

    def test_inherited_failure_is_not_new_regression_but_new_failure_is(self):
        baseline = {
            "checks": [{"id": "inherited", "status": "failed"}, {"id": "stable", "status": "passed"}],
            "inherited_failures": ["inherited"],
        }
        current = {"checks": [{"id": "inherited", "status": "failed"}, {"id": "stable", "status": "passed"}]}
        self.assertEqual(_new_source_regressions(baseline, current), [])
        current["checks"][1]["status"] = "failed"
        self.assertEqual(_new_source_regressions(baseline, current), ["stable"])

    def test_evaluator_adaptive_gates_operation_coverage_and_resume(self):
        fixture = self._prepare_frozen_fixture()
        try:
            report = evaluate(
                fixture["baseline"],
                fixture["source_checks"],
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                fixture["state"],
                fixture["freeze"],
            )
            self.assertEqual(report["status"], "VERIFIED")
            self.assertTrue(report["parity"]["coverage"]["all_required_operations_covered"])
            self.assertFalse(report["target"]["quality_gates"]["static"]["required"])
            self.assertTrue(report["ratchet_eligible"])
            rejected_contract = json.loads(json.dumps(fixture["contract"]))
            rejected_contract["public_surfaces"][0]["operations"] = rejected_contract["public_surfaces"][0]["operations"][:1]
            rejected_corpus = json.loads(json.dumps(fixture["corpus"]))
            self.assertTrue(validate_documents(rejected_contract, rejected_corpus))
        finally:
            fixture["temporary"].cleanup()

    def test_advance_milestone_is_atomic_and_resume_detects_target_change(self):
        fixture = self._prepare_frozen_fixture()
        try:
            result = evaluate(
                fixture["baseline"],
                fixture["source_checks"],
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                fixture["state"],
                fixture["freeze"],
            )
            result_path = fixture["base"] / "migration-result.json"
            state_path = fixture["base"] / "state.json"
            write_json(result_path, result)
            write_json(state_path, fixture["state"])
            checkpoint = advance(state_path, result_path, "M001", fixture["target"])
            self.assertEqual(checkpoint["status"], "accepted")
            accepted_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(accepted_state["completed_milestones"], ["M001"])
            resumed_report = evaluate(
                fixture["baseline"],
                fixture["source_checks"],
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                accepted_state,
                fixture["freeze"],
            )
            self.assertEqual(resumed_report["resume"]["checkpoint_validation"]["status"], "verified")
            before = state_path.read_text(encoding="utf-8")
            rejected_result = dict(result, ratchet_eligible=False)
            write_json(result_path, rejected_result)
            rejected = advance(state_path, result_path, "M002", fixture["target"])
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(before, state_path.read_text(encoding="utf-8"))
            (fixture["target"] / "cli.py").write_text("changed\n", encoding="utf-8")
            invalidated = evaluate(
                fixture["baseline"],
                fixture["source_checks"],
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                accepted_state,
                fixture["freeze"],
            )
            self.assertEqual(invalidated["status"], "INVALIDATED")
        finally:
            fixture["temporary"].cleanup()


if __name__ == "__main__":
    unittest.main()
