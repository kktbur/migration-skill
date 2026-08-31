# Flask → FastAPI benchmark report

**Run:** `20260831-flask-to-fastapi-001`  
**Date:** 2026-08-31  
**Final deterministic status:** `VERIFIED`

## Result

- Source: Flask, 21 public behavior tests, no new regression.
- Target: independently generated FastAPI implementation.
- Contract: 5 atomic HTTP operations.
- Corpus: 21 required cases, 21/21 final parity.
- Milestones: M1, M2, M3 accepted by the ratchet.
- Judge: positive source control passed; 3/3 targeted negative controls detected.
- Resume: final checkpoint `ready`; tampered target `invalidated`.
- Frozen verifier: manifest schema 3 with the complete Python verifier bundle.

The three post-freeze broken-target controls were rejected by the same frozen
Judge:

1. changing the missing-user status from 404 to 200;
2. changing missing-name validation from 400 to 422;
3. dropping the `name` field from a found-user response.

## Reproduction artifacts

- [Contract](.migration/migration.json)
- [Parity Corpus](.migration/parity-corpus.json)
- [Migration plan](.migration/migration-plan.json)
- [Mutation plan](.migration/mutation-plan.json)
- [Baseline](.migration/baseline.json)
- [Judge validation](.migration/judge-validation.json)
- [Freeze manifest](.migration/freeze-manifest.json)
- [Final evaluator result](.migration/results/migration-result.json)
- [Final target parity](.migration/results/parity-result.json)
- [Ratchet state](.migration/state.json)

The benchmark dependencies were installed in a temporary virtual environment
outside the repository. No credentials were provided and no network service or
production resource was used during benchmark execution.

Machine-local executable and workspace paths in generated result metadata are
redacted for publication; verdict fields and cryptographic digests are
unchanged.

Timing, token usage, repair-round count, and human-intervention count were not
instrumented by this v1.2 run and are marked as unavailable in `report.json`.
