# Migration workflow

This reference describes the operational sequence behind `SKILL.md`. It is intentionally independent of a particular source or target language.

## Phase 0: scope and workspace

Record the source root, target root, source and target stacks, entrypoints, requested behavior invariants, and allowed side effects. Prefer a sibling target directory or Git worktree. If the source is a Git repository, record its current revision before running checks.

Do not modify the original source. If source tests create tracked files, use a disposable execution copy and retain the original revision as the evidence anchor.

## Phase 1: inventory and readiness

Run `inventory_project.py`. Then inspect the strongest evidence in this order:

1. Existing public-surface, integration, E2E, and CI tests.
2. HTTP routes, CLI parsers, exported APIs, file interfaces, and schemas.
3. OpenAPI, GraphQL, protobuf, package entrypoints, and documented examples.
4. Agent inference, which must be marked low confidence.

Assess public-surface coverage, test reliability, external dependencies, databases, queues, WebSockets, OAuth, filesystem and process access, native dependencies, and network requirements. Use `HIGH` only when the source can be run and observed reliably. Use `MEDIUM` when a Judge can be built after additional harness work. Use `LOW` and `PLAN_ONLY` when observable behavior or safe execution cannot be established.

## Phase 2: contract and corpus

`migration.json` states which externally observable behaviors are required. `parity-corpus.json` supplies concrete inputs for those behaviors. A contract can have many cases, and a case belongs to one declared surface.

The candidate contract is generated from evidence, then reviewed by the user or Codex. Once the source Judge passes and its negative control fails as expected, freeze the assets. After freeze, only adding a new source-passing case is allowed; additions require a new freeze.

## Phase 3: Judge validation

Prefer a portable adapter over language-specific private-function tests. A good adapter produces stable exit codes, text, JSON, files, or snapshots and can run against both implementations.

Run at least:

- a happy-path case;
- an error-path case;
- a boundary case when one exists;
- a deliberate mutation that changes status, output, exit code, or error behavior.

The positive source run must pass. The negative control must fail. If the comparator passes both, stop with `PLAN_ONLY` and record `JUDGE_INVALID`.

## Phase 4: bounded migration

Build a dependency-aware milestone list. Each milestone records an ID, scope, files or module boundary, prerequisites, expected behavior, checks, and rollback boundary. Choose a unit that can be verified in isolation; do not impose a universal layer order on every repository.

Use Codex for semantic work: finding cross-file dependencies, mapping equivalent APIs, translating configuration, repairing compiler/test failures, and updating call sites. Keep deterministic tools for inventory, command execution, output comparison, and freeze integrity.

## Phase 5: ratchet and resume

After each milestone:

```text
edit target
→ static checks
→ build
→ tests
→ required parity
→ evaluate
→ accept checkpoint or repair/reject
```

Write the accepted milestone and result paths to `state.json`. A resumed session must verify the freeze manifest before continuing.

## Phase 6: handoff

Write `migration-report.md` with the source revision, target path, accepted milestones, inherited failures, new regressions, required/optional parity counts, uncovered surfaces, sandbox requirements, known gaps, and the deterministic final state. Do not describe a partially verified result as complete.
