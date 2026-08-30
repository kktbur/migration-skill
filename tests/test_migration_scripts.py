"""Stdlib-only tests for the deterministic Migration Skill helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from capture_baseline import capture  # noqa: E402
from common import (  # noqa: E402
    FrozenStateError,
    compare_values,
    run_check,
    tree_digest,
    verify_freeze,
    write_json,
)
from compare_results import compare  # noqa: E402
from evaluate_migration import _new_source_regressions, evaluate  # noqa: E402
from freeze_contract import freeze  # noqa: E402
from inventory_project import inventory  # noqa: E402
from run_checks import run_checks  # noqa: E402
from validate_contract import validate_documents  # noqa: E402


class MigrationScriptsTest(unittest.TestCase):
    def _contract(self, source_checks=None, target_checks=None):
        return {
            "schema_version": 1,
            "source": {
                "root": ".",
                "revision": "AUTO",
                "language": "Python",
                "framework": "Flask",
                "entrypoints": ["app.py"],
            },
            "target": {
                "root": "../target",
                "language": "Python",
                "framework": "Flask-compatible fixture",
            },
            "public_surfaces": [
                {
                    "id": "main-http",
                    "kind": "http",
                    "required": True,
                    "source_adapter": {
                        "kind": "harness",
                        "argv": [sys.executable, "-c", "pass"],
                    },
                    "target_adapter": {
                        "kind": "harness",
                        "argv": [sys.executable, "-c", "pass"],
                    },
                    "compare": {"status": True, "body": "json-semantic"},
                    "evidence": ["app.py"],
                    "confidence": "high",
                }
            ],
            "checks": {
                "source": source_checks or [],
                "target": target_checks or [],
            },
            "parity_corpus": "parity-corpus.json",
        }

    def _corpus(self, cases=None):
        if cases is None:
            cases = [{
            "id": "health",
            "surface_id": "main-http",
            "input": {"method": "GET", "path": "/health"},
            "required": True,
            }]
        return {"schema_version": 1, "cases": cases}

    def _quality_checks(self):
        command = [sys.executable, "-c", "pass"]
        return [
            {"id": "source-static", "kind": "static", "argv": command},
            {"id": "source-build", "kind": "build", "argv": command},
            {"id": "source-test", "kind": "test", "argv": command},
        ]

    def _command_contract(self, source_checks, target_checks):
        return {
            "schema_version": 1,
            "source": {"root": ".", "revision": "AUTO", "language": "Python", "entrypoints": ["cli.py"]},
            "target": {"root": "../target", "language": "Python", "entrypoints": ["cli.py"]},
            "public_surfaces": [{
                "id": "main-cli",
                "kind": "command",
                "required": True,
                "source_adapter": {"kind": "harness", "argv": [sys.executable, "cli.py"]},
                "target_adapter": {"kind": "harness", "argv": [sys.executable, "cli.py"]},
                "compare": {"mode": "json-semantic"},
                "evidence": ["cli.py", "test_cli.py"],
                "confidence": "high",
            }],
            "checks": {"source": source_checks, "target": target_checks},
            "parity_corpus": "parity-corpus.json",
        }

    def _fixture(self, empty_corpus=False):
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        source = base / "source"
        target = base / "target"
        source.mkdir()
        target.mkdir()
        (source / "app.py").write_text("def health(): return {'ok': True}\n", encoding="utf-8")
        (target / "app.py").write_text("def health(): return {'ok': True}\n", encoding="utf-8")
        migration_dir = source / ".migration"
        migration_dir.mkdir()
        source_checks = self._quality_checks()
        target_checks = [dict(item, id=item["id"].replace("source", "target")) for item in source_checks]
        contract = self._contract(source_checks, target_checks)
        corpus = self._corpus([] if empty_corpus else None)
        contract_path = migration_dir / "migration.json"
        corpus_path = migration_dir / "parity-corpus.json"
        baseline_path = migration_dir / "baseline.json"
        freeze_path = migration_dir / "freeze-manifest.json"
        write_json(contract_path, contract)
        write_json(corpus_path, corpus)
        baseline = capture(source, contract, "source")
        write_json(baseline_path, baseline)
        evaluator_path = SCRIPT_ROOT / "evaluate_migration.py"
        manifest = freeze(source, contract_path, corpus_path, evaluator_path, freeze_path)
        source_checks_result = run_checks(source, contract, "source", {}, 20000)
        target_checks_result = run_checks(target, contract, "target", {}, 20000)
        source_parity = {
            "cases": [{
                "id": "health",
                "surface_id": "main-http",
                "status": "passed",
                "observed": {"status": 200, "body": {"ok": True}},
            }]
            if not empty_corpus else []
        }
        target_parity = json.loads(json.dumps(source_parity))
        parity = compare(source_parity, target_parity, contract, corpus)
        state = {
            "source_revision": manifest["source"]["revision"],
            "current_milestone": "M002",
            "completed_milestones": ["M001"],
            "last_accepted_checkpoint": "checkpoint-M001",
            "judge": {"positive_control": True, "negative_control": True},
            "required_gaps": [],
        }
        return {
            "temporary": temporary,
            "source": source,
            "target": target,
            "contract": contract,
            "corpus": corpus,
            "contract_path": contract_path,
            "corpus_path": corpus_path,
            "baseline": baseline,
            "manifest": manifest,
            "freeze_path": freeze_path,
            "freeze": {"intact": True, "manifest": manifest},
            "source_checks": source_checks_result,
            "target_checks": target_checks_result,
            "parity": parity,
            "state": state,
        }

    def test_inventory_is_read_only_and_ignores_generated_dirs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            (root / "node_modules").mkdir()
            (root / "dist").mkdir()
            (root / ".migration").mkdir()
            (root / ".git" / "ignored.py").write_text("x", encoding="utf-8")
            (root / "node_modules" / "ignored.js").write_text("x", encoding="utf-8")
            (root / "dist" / "ignored.js").write_text("x", encoding="utf-8")
            (root / ".migration" / "ignored.json").write_text("{}", encoding="utf-8")
            (root / "package.json").write_text(
                '{"dependencies":{"express":"1"},"scripts":{"build":"x","test":"x"}}',
                encoding="utf-8",
            )
            (root / "app.py").write_text("from flask import Flask\n@app.get('/health')\ndef health(): pass\n", encoding="utf-8")
            (root / "test_app.py").write_text("def test_health(): pass\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
            before = tree_digest(root)
            report = inventory(root)
            after = tree_digest(root)
            self.assertEqual(before, after)
            self.assertEqual(report["files"]["total"], 4)
            self.assertIn("Python", {item["name"] for item in report["languages"]})
            self.assertEqual(report["manifests"][0]["path"], "package.json")
            self.assertIn("app.py", report["entrypoints"])
            self.assertIn(".github/workflows/ci.yml", report["ci"])
            self.assertTrue(report["possible_public_surfaces"])

    def test_contract_validation_valid_and_invalid_inputs(self):
        contract = self._contract()
        corpus = self._corpus()
        self.assertEqual(validate_documents(contract, corpus), [])

        duplicate = json.loads(json.dumps(contract))
        duplicate["public_surfaces"].append(json.loads(json.dumps(duplicate["public_surfaces"][0])))
        self.assertTrue(any("重复 id" in error for error in validate_documents(duplicate, corpus)))

        invalid_surface = json.loads(json.dumps(contract))
        invalid_surface["public_surfaces"][0]["kind"] = "unknown"
        self.assertTrue(validate_documents(invalid_surface, corpus))

        invalid_argv = json.loads(json.dumps(contract))
        invalid_argv["public_surfaces"][0]["source_adapter"]["argv"] = "python -c pass"
        self.assertTrue(any("argv" in error for error in validate_documents(invalid_argv, corpus)))

        invalid_case = self._corpus([{"id": "missing-input", "surface_id": "main-http"}])
        self.assertTrue(any("缺少 input" in error for error in validate_documents(contract, invalid_case)))

    def test_run_checks_success_failure_timeout_and_output_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = {
                "checks": [
                    {"id": "pass", "kind": "test", "argv": [sys.executable, "-c", "print('ok')"]},
                    {"id": "failure", "kind": "test", "required": False, "argv": [sys.executable, "-c", "raise SystemExit(3)"]},
                    {"id": "large", "kind": "static", "argv": [sys.executable, "-c", "print('x' * 100)"]},
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

    def test_comparators_normalize_text_and_json_semantics(self):
        self.assertTrue(compare_values("a\r\nb  \r\n", "a\nb\n", "text-normalized"))
        self.assertTrue(compare_values('{"b": 2, "a": 1}', {"a": 1, "b": 2}, "json-semantic"))
        self.assertFalse(compare_values({"a": 1}, {"a": "1"}, "json-semantic"))

    def test_parity_missing_required_case_and_negative_control(self):
        contract = self._contract()
        corpus = self._corpus()
        source = {"cases": [{"id": "health", "status": "passed", "observed": {"status": 200, "body": {"ok": True}}}]}
        missing_target = {"cases": []}
        result = compare(source, missing_target, contract, corpus)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["summary"]["required_failed"], ["health"])
        broken_target = {"cases": [{"id": "health", "status": "passed", "observed": {"status": 500, "body": {"ok": False}}}]}
        negative = compare(source, broken_target, contract, corpus, expect_mismatch=True)
        self.assertEqual(negative["status"], "negative_control_passed")

    def test_freeze_detects_contract_and_evaluator_tampering(self):
        fixture = self._fixture()
        try:
            self.assertTrue(verify_freeze(fixture["freeze_path"])["intact"])
            tampered = dict(fixture["contract"])
            tampered["target"] = dict(tampered["target"], framework="tampered")
            write_json(fixture["contract_path"], tampered)
            with self.assertRaises(FrozenStateError):
                verify_freeze(fixture["freeze_path"])
        finally:
            fixture["temporary"].cleanup()

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            contract_path = base / "migration.json"
            corpus_path = base / "parity-corpus.json"
            evaluator_path = base / "evaluate.py"
            manifest_path = base / "freeze.json"
            write_json(contract_path, self._contract())
            write_json(corpus_path, self._corpus())
            evaluator_path.write_text("print('original')\n", encoding="utf-8")
            freeze(source, contract_path, corpus_path, evaluator_path, manifest_path)
            evaluator_path.write_text("print('mutated')\n", encoding="utf-8")
            with self.assertRaises(FrozenStateError):
                verify_freeze(manifest_path)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            (source / "app.py").write_text("original\n", encoding="utf-8")
            try:
                subprocess.run(["git", "init", "-q"], cwd=str(source), check=True)
                subprocess.run(["git", "add", "app.py"], cwd=str(source), check=True)
                subprocess.run(
                    ["git", "-c", "user.name=Migration Test", "-c", "user.email=migration@example.invalid", "commit", "-qm", "initial"],
                    cwd=str(source),
                    check=True,
                )
            except (OSError, subprocess.CalledProcessError):
                self.skipTest("git is unavailable for revision freeze test")
            contract_path = base / "migration.json"
            corpus_path = base / "parity-corpus.json"
            evaluator_path = base / "evaluate.py"
            manifest_path = base / "freeze.json"
            write_json(contract_path, self._contract())
            write_json(corpus_path, self._corpus())
            evaluator_path.write_text("print('original')\n", encoding="utf-8")
            freeze(source, contract_path, corpus_path, evaluator_path, manifest_path)
            (source / "app.py").write_text("changed\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=str(source), check=True)
            subprocess.run(
                ["git", "-c", "user.name=Migration Test", "-c", "user.email=migration@example.invalid", "commit", "-qm", "changed"],
                cwd=str(source),
                check=True,
            )
            (source / "app.py").write_text("original\n", encoding="utf-8")
            with self.assertRaises(FrozenStateError):
                verify_freeze(manifest_path)

    def test_inherited_failure_is_not_new_regression_but_new_failure_is(self):
        baseline = {"checks": [
            {"id": "inherited", "status": "failed"},
            {"id": "stable", "status": "passed"},
        ], "inherited_failures": ["inherited"]}
        current = {"checks": [
            {"id": "inherited", "status": "failed"},
            {"id": "stable", "status": "passed"},
        ]}
        self.assertEqual(_new_source_regressions(baseline, current), [])
        current["checks"][1]["status"] = "failed"
        self.assertEqual(_new_source_regressions(baseline, current), ["stable"])

    def test_evaluator_verified_and_resume_state(self):
        fixture = self._fixture()
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
            self.assertEqual(report["resume"]["current_milestone"], "M002")
            self.assertEqual(report["inherited_failures"], [])
            self.assertTrue(report["score_is_informational_only"])
            invalid_judge_state = json.loads(json.dumps(fixture["state"]))
            invalid_judge_state["judge"]["negative_control"] = False
            invalid_judge_report = evaluate(
                fixture["baseline"],
                fixture["source_checks"],
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                invalid_judge_state,
                fixture["freeze"],
            )
            self.assertEqual(invalid_judge_report["status"], "PLAN_ONLY")
        finally:
            fixture["temporary"].cleanup()

    def test_evaluator_rejects_new_regression_and_unknown_required_surface(self):
        fixture = self._fixture()
        try:
            source_checks = json.loads(json.dumps(fixture["source_checks"]))
            source_checks["results"][1]["status"] = "failed"
            report = evaluate(
                fixture["baseline"],
                source_checks,
                fixture["target_checks"],
                fixture["parity"],
                fixture["contract"],
                fixture["corpus"],
                fixture["state"],
                fixture["freeze"],
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(report["source_baseline_regressed"])
        finally:
            fixture["temporary"].cleanup()

        empty_fixture = self._fixture(empty_corpus=True)
        try:
            report = evaluate(
                empty_fixture["baseline"],
                empty_fixture["source_checks"],
                empty_fixture["target_checks"],
                empty_fixture["parity"],
                empty_fixture["contract"],
                empty_fixture["corpus"],
                empty_fixture["state"],
                empty_fixture["freeze"],
            )
            self.assertNotEqual(report["status"], "VERIFIED")
            self.assertFalse(report["parity"]["coverage"]["all_required_surfaces_covered"])
        finally:
            empty_fixture["temporary"].cleanup()

    def test_cli_forward_run_completes_and_negative_control_fails(self):
        """Exercise the public CLIs in the same order a Codex task would use."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            source.mkdir()
            target.mkdir()
            cli_code = (
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
            test_code = (
                "import json, subprocess, sys, unittest\n"
                "class TestCli(unittest.TestCase):\n"
                "    def test_hello(self):\n"
                "        result = subprocess.run([sys.executable, 'cli.py', '--name', 'Ada'], capture_output=True, text=True, check=False)\n"
                "        self.assertEqual(result.returncode, 0)\n"
                "        self.assertEqual(json.loads(result.stdout), {'greeting': 'hello Ada'})\n"
                "if __name__ == '__main__': unittest.main()\n"
            )
            (source / "cli.py").write_text(cli_code, encoding="utf-8")
            (target / "cli.py").write_text(cli_code, encoding="utf-8")
            (source / "test_cli.py").write_text(test_code, encoding="utf-8")
            (target / "test_cli.py").write_text(test_code, encoding="utf-8")
            migration = source / ".migration"
            migration.mkdir()
            contract_path = migration / "migration.json"
            corpus_path = migration / "parity-corpus.json"
            inventory_path = migration / "inventory.json"
            baseline_path = migration / "baseline.json"
            manifest_path = migration / "freeze-manifest.json"
            source_checks_path = migration / "source-checks.json"
            target_checks_path = migration / "target-checks.json"
            source_parity_path = migration / "source-parity.json"
            target_parity_path = migration / "target-parity.json"
            parity_path = migration / "parity-result.json"
            state_path = migration / "state.json"
            result_path = migration / "migration-result.json"
            judge_path = migration / "judge-validation.json"
            checks = [
                {"id": "source-static", "kind": "static", "argv": [sys.executable, "-m", "py_compile", "cli.py"]},
                {"id": "source-build", "kind": "build", "argv": [sys.executable, "-m", "py_compile", "cli.py"]},
                {"id": "source-test", "kind": "test", "argv": [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_cli.py"]},
            ]
            target_checks = [dict(item, id=item["id"].replace("source", "target")) for item in checks]
            contract = self._command_contract(checks, target_checks)
            corpus = {
                "schema_version": 1,
                "cases": [
                    {"id": "hello", "surface_id": "main-cli", "input": {"argv": ["--name", "Ada"]}, "required": True},
                    {"id": "boundary-empty", "surface_id": "main-cli", "input": {"argv": ["--name", ""]}, "required": True},
                    {"id": "error", "surface_id": "main-cli", "input": {"argv": ["--unknown"]}, "required": True},
                ],
            }
            write_json(contract_path, contract)
            write_json(corpus_path, corpus)
            write_json(judge_path, {"positive_control": True, "negative_control": True})

            def cli(script_name, *arguments):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT_ROOT / script_name), *map(str, arguments)],
                    cwd=str(SCRIPT_ROOT.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{script_name} failed\nstdout={completed.stdout}\nstderr={completed.stderr}",
                )
                return completed

            cli("inventory_project.py", "--root", source, "--output", inventory_path)
            cli("validate_contract.py", "--contract", contract_path, "--corpus", corpus_path)
            cli("capture_baseline.py", "--root", source, "--spec", contract_path, "--output", baseline_path)
            cli(
                "freeze_contract.py",
                "--root",
                source,
                "--contract",
                contract_path,
                "--corpus",
                corpus_path,
                "--evaluator",
                SCRIPT_ROOT / "evaluate_migration.py",
                "--judge-validation",
                judge_path,
                "--output",
                manifest_path,
            )
            cli("run_checks.py", "--root", source, "--spec", contract_path, "--profile", "source", "--output", source_checks_path)
            cli("run_checks.py", "--root", target, "--spec", contract_path, "--profile", "target", "--output", target_checks_path)

            def run_adapter(root):
                results = []
                for case in corpus["cases"]:
                    completed = subprocess.run(
                        [sys.executable, "cli.py", *case["input"]["argv"]],
                        cwd=str(root),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                    results.append({
                        "id": case["id"],
                        "surface_id": case["surface_id"],
                        "status": "passed",
                        "observed": {
                            "exit_code": completed.returncode,
                            "stdout": json.loads(completed.stdout),
                        },
                    })
                return {"cases": results}

            parity_cases = run_adapter(source)["cases"]
            write_json(source_parity_path, {"cases": parity_cases})
            write_json(target_parity_path, run_adapter(target))
            cli(
                "compare_results.py",
                "--source",
                source_parity_path,
                "--target",
                target_parity_path,
                "--contract",
                contract_path,
                "--corpus",
                corpus_path,
                "--manifest",
                manifest_path,
                "--output",
                parity_path,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            write_json(
                state_path,
                {
                    "source_revision": manifest["source"]["revision"],
                    "current_milestone": "M001",
                    "completed_milestones": [],
                    "last_accepted_checkpoint": None,
                    "judge": {"positive_control": True, "negative_control": True},
                    "required_gaps": [],
                },
            )
            cli(
                "evaluate_migration.py",
                "--baseline",
                baseline_path,
                "--source",
                source_checks_path,
                "--target",
                target_checks_path,
                "--parity",
                parity_path,
                "--contract",
                contract_path,
                "--manifest",
                manifest_path,
                "--state",
                state_path,
                "--output",
                result_path,
            )
            self.assertEqual(json.loads(result_path.read_text(encoding="utf-8"))["status"], "VERIFIED")

            (target / "cli.py").write_text(cli_code.replace("'hello ' + args[1]", "'goodbye ' + args[1]"), encoding="utf-8")
            write_json(target_parity_path, run_adapter(target))
            negative = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_ROOT / "compare_results.py"),
                    "--source",
                    str(source_parity_path),
                    "--target",
                    str(target_parity_path),
                    "--contract",
                    str(contract_path),
                    "--corpus",
                    str(corpus_path),
                    "--manifest",
                    str(manifest_path),
                    "--output",
                    str(migration / "negative-control.json"),
                    "--expect-mismatch",
                ],
                cwd=str(SCRIPT_ROOT.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(negative.returncode, 0, negative.stderr)
            negative_report = json.loads((migration / "negative-control.json").read_text(encoding="utf-8"))
            self.assertEqual(negative_report["status"], "negative_control_passed")


if __name__ == "__main__":
    unittest.main()
