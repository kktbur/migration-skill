# Python CLI → Node CLI benchmark run

Run ID: `20260831-python-cli-to-node-cli-001`

This is the first published v1.2 blind benchmark run. The case supplied only the Python Source, Contract, Corpus, migration plan, mutation plan, and Migration Skill scripts. The Node Target was generated in this run and was not present in the versioned case.

| Measurement | Result |
| --- | --- |
| Migration | Python CLI → Node CLI |
| Source LOC | 99 |
| Generated Target LOC | 98 |
| Milestones | 3/3 accepted |
| Required parity | 8/8 |
| Source regressions | 0 |
| Final deterministic verdict | `VERIFIED` |
| Token usage | unavailable |

The run accepted M1 (normal JSON/text), M2 (invalid option, missing argument, invalid format), and M3 (empty input, Unicode, uppercase). The Source tree was not modified. The freeze manifest is schema v3 and relocatable with its workspace; the complete verifier bundle, Contract, Corpus, Judge-validation artifact, and check specification were verified before the final verdict.

## Negative evidence

After the successful run, a copy of the generated Target was deliberately changed from `hello` to `goodbye`. The same frozen Judge returned `failed` and identified required mismatches in `normal-json`, `normal-text`, `uppercase`, and `unicode`. This is evidence that the Judge rejects a broken Target, not just that it accepts the correct one.

## Replay record

The run keeps the Source/Target check results, every milestone result and checkpoint, the final evaluator result, the Resume preflight results, the Target-tamper invalidation result, the prompt, and the environment summary under this directory. `migration-skill/scripts/` is the verifier snapshot used by the v3 freeze.
