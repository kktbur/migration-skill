# Verification rules

## Baseline is evidence, not a demand for perfection

The Source may already have failures. Record them as `inherited_failures` in `baseline.json`. A migration is rejected only for a failure that was green in the baseline and becomes non-green later. A command that cannot execute, times out, or changes the Source tree during capture is an evidence failure, not an inherited test failure.

## Adaptive required gates

`completion_gates.required_check_kinds` controls which quality categories are required. A small CLI may require `test` and parity without fabricating a build or static command. Every configured individual check with `required: true` must still pass. Unconfigured categories are reported as informational rather than automatically failing the migration.

## Required conditions for VERIFIED

`VERIFIED` requires all of the following:

- Freeze integrity is intact, including the complete verifier bundle;
- the Source has no new regression compared with its baseline;
- configured required target checks pass;
- every required parity case matches;
- every required public surface has declared operations, evidence, and coverage;
- no required gap remains;
- Judge positive and targeted negative controls have both been validated;
- all milestones in the validated migration plan are accepted. The last target checkpoint is validated before the next edit by `verify_resume.py`; the final evaluator does not compare a later Target digest with an older checkpoint.

Optional cases may remain in `PARTIALLY_VERIFIED`, but must be listed in the report. A percentage or score is report-only and never overrides a required failure.

## Parity runner and comparator

`run_parity.py` invokes one explicit Source or Target adapter per Corpus case. The adapter receives JSON on stdin and returns `{"status":"passed","observed":...}` on stdout. Adapter failures, timeouts, invalid JSON, and missing `observed` values fail the corresponding case.

Schema v2 compares an explicit `whole` value or a set of explicit `fields`. `exact` compares decoded values without tolerance. `text-normalized` converts CRLF/CR to LF and removes trailing whitespace per line. `json-semantic` compares parsed JSON values, so object key order does not matter but missing fields, changed types, and changed null semantics still fail. `exit-code` compares integer exit codes, and `snapshot` is exact.

Do not invent tolerance during a failing migration. If dynamic values make a comparison unstable, add a deterministic adapter or an explicitly documented normalizer, rerun it against the Source, validate the Judge, and create a new Freeze.

## Judge validation

The positive control must be a passing compare artifact with no required failures. Each negative control must name a required case and a mutation result in which that case is actually mismatched. An unrelated optional mismatch, a free-standing `negative_control: true`, or a pair of hand-written booleans is not evidence. `validate_judge.py` emits the only artifact accepted by `freeze_contract.py`.

## Milestone Gate and Ratchet

`evaluate_milestone.py` evaluates only the current milestone. Future required cases may be missing, while every current required case and every previously protected case must pass. `advance_milestone.py` performs the atomic `state.json` update. Its proof-set rule is:

```text
previously protected cases/checks ⊆ current passing proof set
```

A missing protected item, missing current gate, unmet dependency, or invalid target digest is rejected and requires repair or rollback. Verification scores remain report-only and are not the acceptance rule.

Before a new milestone edit, `verify_resume.py` compares the current Target revision/tree digest with the last accepted checkpoint. If a user or another process changed the Target, the preflight is `invalidated` and the migration must stop until the checkpoint is rebuilt or explicitly re-approved.

## Completion states

Use exactly one of:

```text
VERIFIED
PARTIALLY_VERIFIED
BLOCKED
PLAN_ONLY
INVALIDATED
```

`PLAN_ONLY` is appropriate when no reliable baseline/Judge can be built or Judge validation fails. `INVALIDATED` means frozen evidence or a checkpoint changed. `BLOCKED` means evidence is valid but required regressions/gaps remain.
