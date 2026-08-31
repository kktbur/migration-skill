# CommonJS → ESM benchmark report

**Run:** `20260831-commonjs-to-esm-001`  
**Date:** 2026-08-31  
**Final deterministic status:** `VERIFIED`

## Result

- Source: CommonJS package with a default greeting export, named `add` export, and explicit error behavior.
- Target: independently generated native Node.js ESM package; the blind case did not contain a prebuilt Target.
- Contract: 3 atomic operations covering the default export, named export, and error semantics.
- Corpus: 7 required cases, including Unicode, numeric boundary, and invalid-input cases.
- Milestones: M1, M2, and M3 accepted by the verification ratchet.
- Target checks: 3/3 passed.
- Final parity: 7/7 required cases passed.
- Source regressions: 0; Source tree digest remained unchanged after the run.
- Frozen verifier: schema v3 with all 15 Python verifier-bundle files frozen.

The target uses `package.json` with `"type": "module"` and an `exports` entry,
native `export default`/named exports, and ESM adapters/tests. The package
self-reference is exercised through the public package name rather than by
reaching into a private implementation module. This follows Node's explicit
module-format rules documented in the [ECMAScript modules documentation](https://nodejs.org/api/esm.html)
and [package documentation](https://nodejs.org/api/packages.html).

## Judge validation

The Source positive control passed. Three targeted mutations were run against
copied Source implementations before Freeze:

1. Change the default greeting; the Judge detected `default-greet`.
2. Change the empty-name error message; the Judge detected `empty-name-error`.
3. Change the named add result; the Judge detected `named-add`.

All 3/3 controls were detected by the required case and operation. No hand-
written boolean Judge flags were used.

## Broken Target rejection

After the successful run, three copies of the generated Target were deliberately
changed. The same frozen Judge returned `negative_control_passed` for each:

| Broken Target | Expected detected case | Result |
| --- | --- | --- |
| Default greeting changed | `default-greet` | rejected |
| Error message changed | `empty-name-error` | rejected |
| Named add result changed | `named-add` | rejected |

The corresponding check suites also failed, while the parity runner remained
able to produce the targeted observable mismatch used by the Judge.

## Resume and replay record

- Intact final Target checkpoint: `ready`.
- Target copy modified after the checkpoint: `invalidated` with exit code 1.
- Freeze manifest, Contract, Corpus, Judge validation, every milestone result,
  target checks, parity results, and final evaluator result are preserved under
  `.migration/`.
- The benchmark used Node.js `v24.19.0`, required no network service, and was
  given no credentials.

Timing, token usage, repair-round count, and human-intervention count were not
instrumented by this v1.2 run and are marked unavailable in `report.json`.
