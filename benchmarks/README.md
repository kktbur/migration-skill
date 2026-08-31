# Migration benchmarks

These benchmark definitions are the public evidence plan for the protocol. They are intentionally separate from the deterministic helper tests: a helper test proves that a verifier rule works, while a benchmark proves that Codex can use the protocol to produce a real target implementation.

## Required benchmark record

Each benchmark run should preserve:

- source revision and tree digest;
- Contract, Corpus, Judge-validation artifact, and freeze manifest;
- target revision/tree digest and accepted milestone list;
- source inherited failures and any new regressions;
- target check and parity results;
- build failures, repair rounds, manual interventions, elapsed time, and token usage when available;
- final deterministic evaluator result.

Do not publish a `VERIFIED` claim from a benchmark unless the complete artifact chain is reproducible and a deliberately broken Target is rejected by the same frozen Judge.

## Planned matrix

| Migration | What it demonstrates | Current status |
| --- | --- | --- |
| Python CLI → Node CLI | Cross-language command behavior, exit codes, JSON output, and error paths | Protocol fixture covered by unit tests; public end-to-end benchmark run pending |
| Flask → FastAPI | Framework migration across HTTP routes and error behavior | Benchmark specification pending a dependency-free published fixture |
| CommonJS → ESM | Runtime/module-format migration and package entrypoints | Benchmark specification pending a dependency-free published fixture |

The first fixture in `tests/test_migration_scripts.py` is intentionally small and dependency-free. It exercises a Python command implementation through the portable adapter protocol and mutation validation; it is evidence for the verifier, not a claim that a Codex-generated Node target has already been verified.

## Adding a benchmark

Add a self-contained fixture only when its source and target can be run without credentials or production services. Include the Contract, Corpus, adapter(s), check specification, mutation plan, and a short report. If dependencies or network access are required, document the sandbox boundary and keep the default CI path offline.
