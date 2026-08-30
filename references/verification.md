# Verification rules

## Baseline is evidence, not a demand for perfection

The source may already have failures. Record them as `inherited_failures` in `baseline.json`. A migration is rejected only for a failure that was green in the baseline and becomes non-green later.

## Required gates

`VERIFIED` requires all of the following:

- freeze integrity is intact;
- the source has no new regression;
- required target static/build/test checks pass;
- every required parity case matches;
- every required public surface has required cases and coverage;
- no required gap remains;
- Judge positive and negative controls have both been validated.

Optional cases may remain in `PARTIALLY_VERIFIED`, but must be listed in the report.

## Comparison semantics

`exact` compares decoded values without tolerance. `text-normalized` converts CRLF/CR to LF and removes trailing whitespace per line. `json-semantic` compares parsed JSON values, so object key order does not matter but missing fields, changed types, and changed null semantics still fail. `exit-code` compares integer exit codes. `snapshot` is an exact snapshot comparison.

Do not invent tolerance during a failing migration. If dynamic values make a comparison unstable, add a deterministic adapter or an explicitly documented normalizer, rerun it against the source, and create a new freeze.

## Ratchet

Every accepted checkpoint must preserve the previous accepted required gates. A lower result is a rejected checkpoint that requires repair or rollback. Scores and percentages are report-only; they never override required failures.
