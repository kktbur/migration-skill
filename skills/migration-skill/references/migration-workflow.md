# Migration workflow

This reference describes the operational sequence behind `SKILL.md`. It is independent of a particular source or target language.

## Phase 0: scope and workspace

Record the source root, target root, source and target stacks, entrypoints, requested behavior invariants, and allowed side effects. Prefer a sibling target directory or Git worktree. If the source is a Git repository, record its current revision before running checks.

Do not modify the original source. If source tests create tracked files, use a disposable execution copy and retain the original revision as the evidence anchor.

## Phase 1: inventory and readiness

Run:

```text
python scripts/inventory_project.py --root SOURCE --output .migration/inventory.json
```

Inventory is read-only: it does not import the project, install dependencies, or access the network. It reports manifests, languages, entrypoints, tests, CI, documentation, OpenAPI/GraphQL/protobuf/schema evidence, candidate operations, public-surface signals, dependencies, and risks.

Inspect the strongest evidence in this order:

1. Existing public-surface, integration, E2E, and CI tests.
2. HTTP routes, CLI parsers, exported APIs, file interfaces, and schemas.
3. OpenAPI, GraphQL, protobuf, package entrypoints, and documented examples.
4. Agent inference, which must be marked low confidence.

Assess public-surface coverage, test reliability, external dependencies, databases, queues, WebSockets, OAuth, filesystem and process access, native dependencies, and network requirements. Use `HIGH` only when the source can be run and observed reliably. Use `MEDIUM` when a Judge can be built after additional harness work. Use `LOW` and `PLAN_ONLY` when observable behavior or safe execution cannot be established.

## Phase 2: Contract and Corpus

Create `.migration/migration.json` with schema version 2. Enumerate atomic operations below each public surface and attach path/type evidence to every required operation. Create `.migration/parity-corpus.json` with concrete inputs, one `operation_id` per case, and required/optional classification. After the Judge is frozen, create `.migration/migration-plan.json` with bounded milestones; a plan milestone is allowed to cover only a subset of the final Corpus.

Validate before execution:

```text
python scripts/validate_contract.py \
  --contract .migration/migration.json \
  --corpus .migration/parity-corpus.json
```

The Contract states invariants; the Corpus does not contain expected outputs or comparator rules.

## Phase 3: Source baseline and Judge

Capture the Source baseline before accepting migration edits:

```text
python scripts/capture_baseline.py \
  --root SOURCE \
  --spec .migration/migration.json \
  --output .migration/baseline.json \
  --profile source
```

Existing failing checks are recorded as inherited failures. Capture still succeeds by default; use `--strict` only when a caller explicitly wants a nonzero result for inherited failures. A timeout, command-not-found, execution error, or source change during capture is not an inherited failure and blocks reliable evidence.

Run the same Corpus against Source:

```text
python scripts/run_parity.py --root SOURCE --contract .migration/migration.json \
  --corpus .migration/parity-corpus.json --profile source \
  --output .migration/results/source-parity.json
```

The positive Judge can compare Source against itself, or compare it with a separately portable expected artifact. Then create a mutation plan whose entries identify the required case each deliberate mutation must break. Before Freeze, use the explicit bootstrap mode to compare the mutated result:

```text
python scripts/compare_results.py --source source-parity.json --target mutated-parity.json \
  --contract .migration/migration.json --corpus .migration/parity-corpus.json \
  --output negative-control.json --expect-mismatch --expect-case health \
  --pre-freeze
```

After Freeze, every normal parity comparison must provide `--manifest`; the pre-freeze flag is deliberately explicit and its result cannot be used as a final migration result without rerunning the comparison against the frozen bundle.

Validate the controls:

```text
python scripts/validate_judge.py --positive positive.json \
  --mutation-plan mutation-plan.json --root SOURCE \
  --output .migration/judge-validation.json
```

If the positive run does not pass or a targeted mutation is not detected, stop with `PLAN_ONLY` and record `JUDGE_INVALID`.

## Phase 4: Freeze evidence

Freeze the source revision/tree digest and the complete verifier bundle:

```text
python scripts/freeze_contract.py --root SOURCE \
  --contract .migration/migration.json \
  --corpus .migration/parity-corpus.json \
  --evaluator scripts/evaluate_migration.py \
  --judge-validation .migration/judge-validation.json \
  --verifier-root scripts \
  --workspace-root WORKSPACE \
  --output .migration/freeze-manifest.json
```

The frozen bundle includes `common.py`, `validate_contract.py`, `run_parity.py`, `compare_results.py`, `validate_judge.py`, `evaluate_migration.py`, and any other Python verifier helper under the chosen root. With `--workspace-root`, v1.2 records relative paths in a relocatable v3 manifest. If the Source revision, tree digest, Contract, Corpus, Judge artifact, or verifier file set/hash changes, rerun Inventory, Baseline, Judge, and Freeze.

## Phase 5: bounded migration

Build a dependency-aware milestone list. Each milestone records an ID, scope, files or module boundary, prerequisites, expected behavior, checks, and rollback boundary. Choose a unit that can be verified in isolation; do not impose a universal layer order on every repository.

Use Codex for semantic work: finding cross-file dependencies, mapping equivalent APIs, translating configuration, repairing compiler/test failures, and updating call sites. Keep deterministic tools for inventory, command execution, output comparison, freeze integrity, and verdicts.

The default write boundary is:

```text
Source: read-only
Target: sibling directory, worktree, or dedicated migration branch
.migration/: evidence and state
```

## Phase 6: plan, milestone verification, and resume

Validate the plan before starting edits:

```text
python scripts/validate_plan.py \
  --plan .migration/migration-plan.json \
  --contract .migration/migration.json \
  --corpus .migration/parity-corpus.json
```

At the start of every milestone, run the pre-edit gate. It checks the last accepted Target checkpoint before any new edits are made:

```text
python scripts/verify_resume.py \
  --state .migration/state.json \
  --target-root TARGET \
  --manifest .migration/freeze-manifest.json \
  --output .migration/results/resume-preflight.json \
  --workspace-root WORKSPACE
```

Then run checks/parity for the current milestone and evaluate only that milestone:

```text
python scripts/evaluate_milestone.py \
  --baseline .migration/baseline.json \
  --source .migration/results/source-checks.json \
  --target .migration/results/target-checks.json \
  --parity .migration/results/parity-result.json \
  --contract .migration/migration.json \
  --plan .migration/migration-plan.json \
  --state .migration/state.json \
  --manifest .migration/freeze-manifest.json \
  --milestone-id M001 \
  --output .migration/results/milestone-M001.json
```

After each bounded milestone:

```text
edit target
→ configured static checks
→ build when configured
→ tests
→ milestone required parity
→ evaluate_milestone.py
→ advance_milestone.py --plan migration-plan.json
```

`evaluate_milestone.py` is the Milestone Gate. It allows future cases to remain missing, but requires the current milestone and all previously protected proof cases/checks to pass. `advance_milestone.py` is the state mutation boundary: it atomically writes `state.json` only when the result is eligible and its proof set is a superset of the previous accepted proof set. Scores are informational and cannot override required gates.

Persist accepted milestones and target tree digests in `.migration/state.json`. A resumed session must run `verify_resume.py` before editing. If the target changed outside the checkpoint, mark the preflight `invalidated` instead of guessing which edits survived. After the next milestone changes the Target digest, do not compare it to the older checkpoint in the final evaluator.

## Phase 7: final completion

Only after every milestone has been accepted, run the final gate:

```text
python scripts/evaluate_migration.py \
  --baseline .migration/baseline.json \
  --source .migration/results/source-checks.json \
  --target .migration/results/target-checks.json \
  --parity .migration/results/parity-result.json \
  --contract .migration/migration.json \
  --plan .migration/migration-plan.json \
  --manifest .migration/freeze-manifest.json \
  --state .migration/state.json \
  --output .migration/results/migration-result.json
```

The final gate requires all planned milestones, all final required cases and operations, all configured final checks, an intact Freeze, a valid Judge, and no new Source regression.

## Phase 8: handoff

Write `.migration/migration-report.md` with the Source revision, target path, accepted milestones, inherited failures, new regressions, required/optional parity counts, operation coverage, sandbox requirements, known gaps, and the deterministic final state. Do not describe a partially verified result as complete.
