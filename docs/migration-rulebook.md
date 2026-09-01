# Migration Benchmark Rulebook

This rulebook defines the maintenance and acceptance rules for the published
Migration Skill benchmark runs. It is a protocol for replaying evidence; it is
not a second Agent Runtime and it does not make a benchmark claim on behalf of
an unavailable host environment.

## Scope

The rulebook applies to:

- blind benchmark cases under `benchmarks/cases/`;
- dated execution records under `benchmarks/runs/`;
- the frozen Contract, Corpus, Judge, verifier bundle, and milestone state in
  each run;
- the offline replay matrix in `benchmarks/regression-matrix.json`.

The benchmark Source is the executable specification. A generated Target is
evidence from one dated run, not a reference implementation that may be copied
into a new blind case.

## Artifact roles

Every published run must keep these roles separate:

| Artifact | Role |
| --- | --- |
| Source | The original implementation whose behavior is being preserved. |
| `migration.json` | The machine-readable Behavior Contract: required public surfaces and atomic operations. |
| `parity-corpus.json` | Concrete inputs used to exercise the Contract; it does not define how a runtime starts. |
| Judge validation | Positive Source proof and targeted negative-control proof. |
| Freeze manifest | Source revision/tree digest plus the complete verifier bundle and comparison policy. |
| Target | The implementation produced during that dated migration run. |
| Report and result files | Replayable evidence and deterministic verdicts, not editable pass/fail labels. |

An operation is not covered merely because another operation on the same
surface has a passing case. Every required operation must have evidence and at
least one required Corpus case.

## Acceptance ladder

Replay and review should follow this order:

1. Validate the run artifact shape and Contract/Corpus references.
2. Verify the frozen Source revision, tree digest, and verifier bundle.
3. Replay the Source baseline and record inherited failures without treating
   them as new migration regressions.
4. Replay the Source and Target adapters with the same Corpus.
5. Require all configured required Target checks and all required parity cases
   to pass.
6. Run each declared broken-Target control and require the named required
   cases to fail under the same frozen Judge.
7. Require the final evaluator to return `VERIFIED` and the required operation
   coverage to be complete.
8. Re-run the complete dated matrix with
   `benchmarks/run_regression.py` before changing a release or benchmark claim.

The offline regression report may be `blocked` when a published run needs a
runtime dependency that is not installed in the current host. That is an
environment result, not evidence that the migration passed or failed. Provide
an explicit interpreter with `--python-executable` or
`--node-executable`, or run the benchmark in its documented isolated
environment. The harness never installs dependencies or requires a model.

## Baseline and regression policy

Failures present in the captured Source baseline are `inherited_failures`.
They must remain visible in the report. A later replay must not turn them into
new regressions merely because the baseline is not green.

A newly failing required Source check, newly failing parity case, or newly
failing required Target check is a regression and rejects the relevant
milestone or run. A missing runtime prerequisite is reported as `blocked`
before execution where the matrix can identify it.

## Judge integrity rules

The positive control must pass against Source. Each negative control must name
the mutation and the required case(s) it is expected to break. A random
optional mismatch is not sufficient evidence of Judge sensitivity.

After a freeze:

- do not delete a required Corpus case;
- do not change a required case to optional;
- do not remove a field from comparison;
- do not broaden a normalizer or tolerance;
- do not change evaluator or verifier-bundle files without rebuilding and
  revalidating the freeze;
- do not edit an old report to turn a failure into a pass.

If the Contract, Corpus, Judge, comparator policy, evaluator, or any frozen
verifier dependency changes, create a new freeze and replay the affected
matrix. The old dated evidence remains historical evidence.

## Security and execution boundary

The harness runs helper commands with `shell=False`, a minimum environment, a
temporary copy of each published run, and no credentials. This does not
guarantee OS-level network isolation. The report must keep
`network_isolation_guaranteed: false` unless a real sandbox provides that
property.

Do not use `NODE_TLS_REJECT_UNAUTHORIZED=0`, disable certificate validation, or
pass host secrets to make a replay green. Network access, package installation,
native code, external services, production resources, and unknown privileged
commands require a real sandbox boundary or a `PLAN_ONLY` decision.

## Commands

Run all available published runs:

```text
python benchmarks/run_regression.py \
  --root . \
  --matrix benchmarks/regression-matrix.json \
  --output benchmarks/regression-report.json
```

When a benchmark needs a local dependency environment, make the runtime
explicit without changing the Skill or the Contract:

```text
python benchmarks/run_regression.py \
  --root . \
  --python-executable PATH_TO_PYTHON \
  --node-executable PATH_TO_NODE \
  --output benchmarks/regression-report.json
```

The command returns `0` only when every selected run passes, `1` for failed or
blocked evidence, and `2` for invalid input or integrity failure. The report
also distinguishes `passed`, `failed`, `blocked`, and `invalid` per run.

The normal source-level verification commands remain:

```text
python -m unittest discover -s tests
python skills/migration-skill/scripts/validate_skill.py --root skills/migration-skill
```

See [`benchmarks/README.md`](../benchmarks/README.md) for the published run
layout and [`skills/migration-skill/references/verification.md`](../skills/migration-skill/references/verification.md)
for the core migration verification protocol.
