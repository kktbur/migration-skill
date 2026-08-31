# Migration Skill

Migration Skill is a Codex-native, local-first protocol for behavior-preserving codebase migration.

It turns a migration request into an auditable sequence:

```text
Discover → Contract → Judge → Freeze → Plan → Resume Preflight → Rewrite → Verify → Ratchet
```

The project is intentionally not another `gpt-migrate` Agent Runtime. Codex supplies repository reading, cross-file reasoning, editing, command execution, build, test, and debugging. This package supplies the pieces that need to stay deterministic across sessions:

- read-only inventory and migration-readiness evidence;
- a JSON Behavior Contract with atomic public operations;
- a separate parity Corpus of concrete inputs;
- a portable Source/Target adapter protocol;
- targeted Judge mutation validation;
- a frozen verifier bundle and source evidence digest;
- adaptive completion gates and atomic milestone checkpoints.

The current package is a v1.2 protocol implementation. It does not claim that an arbitrary repository can be migrated automatically or that a subprocess wrapper is a network sandbox.

## Requirements

Python 3.11 or newer is required. The deterministic helpers use the standard-library `tomllib` parser introduced in Python 3.11; the offline test path has no third-party Python dependency.

## Quick start

Use the `migration-skill` directory as a repository-scoped Codex Skill. The package does not install itself globally and does not require an LLM SDK, MCP server, Docker orchestrator, or third-party Python package.

1. Run the read-only inventory:

   ```text
   python scripts/inventory_project.py --root SOURCE --output .migration/inventory.json
   ```

2. Have Codex turn the evidence into `.migration/migration.json` schema v2 and `.migration/parity-corpus.json`. Every required operation must have evidence, and every required Corpus case must name its `operation_id`.

3. Validate the Contract and Corpus:

   ```text
   python scripts/validate_contract.py \
     --contract .migration/migration.json \
     --corpus .migration/parity-corpus.json
   ```

4. Capture the Source baseline and execute the Source/Target adapters with `run_parity.py`. If a Contract contains placeholders such as `${PYTHON}`, pass them explicitly with `--var`; validate a positive Source Judge and targeted negative controls with `validate_judge.py`.

5. Freeze the source evidence and complete verifier bundle, then write `.migration/migration-plan.json` and validate it with `validate_plan.py`.

6. Before every new edit, run `verify_resume.py`. After one bounded milestone, run `evaluate_milestone.py` and accept its proof set only through `advance_milestone.py`. Run the final `evaluate_migration.py` only after all milestones are complete.

The full command sequence and recovery rules are in [`references/migration-workflow.md`](references/migration-workflow.md). Contract examples are in [`references/behavior-contract.md`](references/behavior-contract.md).

## Adapter protocol

For each Corpus case, `run_parity.py` starts the selected Surface adapter with `shell=False`, sends one JSON object on stdin, and expects one JSON object on stdout:

```json
{
  "case_id": "health",
  "surface_id": "public-http",
  "operation_id": "GET-/health",
  "input": {"method": "GET", "path": "/health"}
}
```

The adapter returns:

```json
{
  "status": "passed",
  "observed": {"status": 200, "body": {"ok": true}}
}
```

The same Corpus is run against Source and Target. `compare_results.py` applies the frozen `whole` or `fields` comparator, including explicit text normalization and JSON semantic comparison.

## Safety model

Checks and adapters receive a minimum environment by default; host credentials are not implicitly inherited. Explicitly declared environment names that look like keys, tokens, passwords, credentials, or private keys are rejected. Secrets must not be placed in Contract, Corpus, target, logs, or result JSON.

The runners use `shell=False`, but this is not network isolation. Package installation, native code, external services, unknown scripts, and high-risk repositories require a real sandbox/Docker boundary or a deliberate `PLAN_ONLY` result. The source remains read-only and the target is isolated by default.

Read [`references/safety.md`](references/safety.md) before executing a repository with external side effects.

## Completion states

The deterministic evaluator emits exactly one of:

```text
VERIFIED
PARTIALLY_VERIFIED
BLOCKED
PLAN_ONLY
INVALIDATED
```

`VERIFIED` requires an intact freeze, no new Source regression, all configured required Target checks, all required parity cases, complete required operation coverage, a valid Judge, all milestones in the validated plan, and no required gaps. Scores and percentages are informational only. A milestone can be eligible while future cases are missing; that intermediate result is not final `VERIFIED`.

## Repository layout

```text
SKILL.md
agents/openai.yaml
references/
scripts/
tests/
benchmarks/
```

The deterministic helper scripts use Python's standard library only. `scripts/validate_skill.py` validates the package locally; the Skill Creator `quick_validate.py` can also be run against this directory.

## Development and CI

Run the same checks used by CI:

```text
python -m unittest discover -s tests
python -c "from pathlib import Path; import py_compile; [py_compile.compile(str(path), doraise=True) for path in Path('scripts').glob('*.py')]"
python scripts/validate_skill.py --root .
```

GitHub Actions runs these checks on both Ubuntu and Windows. Tests use `unittest` and temporary directories and do not require Docker, network access, or third-party packages.

## Benchmarks and limits

The benchmark plan covers Python CLI → Node CLI, Flask → FastAPI, and CommonJS → ESM. Benchmark cases are blind: they publish Source, Contract, Corpus, plan, and mutation metadata but no pre-made Target. Complete `VERIFIED` runs with broken-Target rejection are published at [`benchmarks/runs/20260831-python-cli-to-node-cli-001/`](benchmarks/runs/20260831-python-cli-to-node-cli-001/), [`benchmarks/runs/20260831-flask-to-fastapi-001/`](benchmarks/runs/20260831-flask-to-fastapi-001/), and [`benchmarks/runs/20260831-commonjs-to-esm-001/`](benchmarks/runs/20260831-commonjs-to-esm-001/). See [`benchmarks/README.md`](benchmarks/README.md).

Out of scope for v1 are production deployment, production database writes, cloud mutation, a GUI, a long-running Agent Runtime, a GitHub PR bot, automatic network isolation, arbitrary monorepo one-click migration, and in-place migration without a branch/worktree boundary.

## Lineage and feedback

The architectural lineage from `gpt-migrate`, Anthropic's Code Migration Kit, GitHub Next Crane, and sandboxed migration examples is documented in [`references/upstream-lineage.md`](references/upstream-lineage.md). No implementation code is copied from those projects.

Please report reproducible defects, unsafe behavior, or adapter compatibility issues through the repository's [GitHub Issues](https://github.com/kktbur/migration-skill/issues). Maintenance should keep the verifier bundle, schema validation, mutation tests, cross-platform CI, and benchmark evidence in sync whenever a protocol rule changes.
