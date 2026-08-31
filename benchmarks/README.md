# Migration benchmarks

These benchmark definitions are the public evidence plan for the protocol. They are intentionally separate from the deterministic helper tests: a helper test proves that a verifier rule works, while a benchmark proves that Codex can use the protocol to produce a real target implementation.

Benchmark cases are blind inputs. A case never contains a pre-made Target or reference implementation. Generated Targets belong only to a dated run directory, alongside the prompt and evidence needed to replay that run.

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
| Python CLI → Node CLI | Cross-language command behavior, exit codes, JSON output, and error paths | Blind case implemented; [run 20260831-python-cli-to-node-cli-001](runs/20260831-python-cli-to-node-cli-001/) is `VERIFIED` and includes broken-Target rejection |
| Flask → FastAPI | Framework migration across HTTP routes and error behavior | Blind case implemented; [run 20260831-flask-to-fastapi-001](runs/20260831-flask-to-fastapi-001/) is `VERIFIED` with 21/21 parity and broken-Target rejection |
| CommonJS → ESM | Runtime/module-format migration and package entrypoints | Blind case specification implemented; no Target claim |

The first fixture in `tests/test_migration_scripts.py` is intentionally small and dependency-free. It exercises a Python command implementation through the portable adapter protocol and mutation validation; it is evidence for the verifier, not a claim that a Codex-generated Node target has already been verified. The Python CLI → Node CLI and Flask → FastAPI dated runs are public migration evidence; CommonJS → ESM remains specification-only. The three blind cases are in [`cases/python-cli-to-node-cli/`](cases/python-cli-to-node-cli/), [`cases/flask-to-fastapi/`](cases/flask-to-fastapi/), and [`cases/commonjs-to-esm/`](cases/commonjs-to-esm/).

## Adding a benchmark

Add a self-contained blind fixture only when its Source and adapters can be inspected without credentials or production services. Include the Contract, Corpus, migration plan, mutation plan, check specification, and a short case README; do not add a reference Target. If dependencies or network access are required, document the sandbox boundary and keep the default CI path offline.

## Directory layout

```text
benchmarks/
├── cases/
│   ├── python-cli-to-node-cli/
│   ├── flask-to-fastapi/
│   └── commonjs-to-esm/
└── runs/
```

## Run record

A published run should contain `source/`, `generated-target/`, `.migration/`, `environment.json`, `prompt.md`, `report.json`, and `report.md`. The report must state Source revision/tree digest, Target digest, Python/Node and Codex versions when available, milestone and repair counts, manual interventions, parity counts, source regressions, and the final deterministic verdict. After a `VERIFIED` run, execute the same frozen Judge against a deliberately broken Target and publish the resulting failure as negative evidence.
