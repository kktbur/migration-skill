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

## Offline regression replay

The published runs are maintained by [`run_regression.py`](run_regression.py)
and [`regression-matrix.json`](regression-matrix.json). The harness copies each
selected dated run to a temporary directory and replays its frozen Contract
validation, resume preflight, checks, Source/Target parity, evaluator, and
explicit broken-Target controls. It does not call a model, install packages,
use credentials, or require network access.

```text
python benchmarks/run_regression.py \
  --root . \
  --matrix benchmarks/regression-matrix.json \
  --output benchmarks/regression-report.json
```

Use `--python-executable` or `--node-executable` when a run's documented
runtime dependencies are available in an explicit local environment. Missing
dependencies are reported as `blocked`, not silently installed. The harness
uses a minimum environment and `shell=False`, but
`network_isolation_guaranteed` is intentionally `false`: real network or
native-code isolation requires a separate sandbox.

`regression-report.json` is a generated, path-free evidence snapshot. Recreate
it rather than editing it when a run or verifier changes.

The published Python CLI Source test is locale-sensitive on Windows because
the historical fixture did not pin subprocess text encoding. The Windows CI
job therefore does not run that replay smoke; it still runs the full protocol
unit suite, compilation, and Skill validation. A local Windows run with a
compatible UTF-8 environment can execute the same harness directly.

## Planned matrix

| Migration | What it demonstrates | Current status |
| --- | --- | --- |
| Python CLI → Node CLI | Cross-language command behavior, exit codes, JSON output, and error paths | Blind case implemented; [run 20260831-python-cli-to-node-cli-001](runs/20260831-python-cli-to-node-cli-001/) is `VERIFIED` and includes broken-Target rejection |
| Flask → FastAPI | Framework migration across HTTP routes and error behavior | Blind case implemented; [run 20260831-flask-to-fastapi-001](runs/20260831-flask-to-fastapi-001/) is `VERIFIED` with 21/21 parity and broken-Target rejection |
| CommonJS → ESM | Runtime/module-format migration and package entrypoints | Blind case implemented; [run 20260831-commonjs-to-esm-001](runs/20260831-commonjs-to-esm-001/) is `VERIFIED` with 7/7 parity and broken-Target rejection |

The first fixture in `tests/test_migration_scripts.py` is intentionally small and dependency-free. It exercises a Python command implementation through the portable adapter protocol and mutation validation; it is evidence for the verifier, not a claim that a Codex-generated Node target has already been verified. The Python CLI → Node CLI, Flask → FastAPI, and CommonJS → ESM dated runs are public migration evidence. The three blind cases are in [`cases/python-cli-to-node-cli/`](cases/python-cli-to-node-cli/), [`cases/flask-to-fastapi/`](cases/flask-to-fastapi/), and [`cases/commonjs-to-esm/`](cases/commonjs-to-esm/).

## Adding a benchmark

Add a self-contained blind fixture only when its Source and adapters can be inspected without credentials or production services. Include the Contract, Corpus, migration plan, mutation plan, check specification, and a short case README; do not add a reference Target. If dependencies or network access are required, document the sandbox boundary and keep the default CI path offline.

## Directory layout

```text
benchmarks/
├── cases/
│   ├── python-cli-to-node-cli/
│   ├── flask-to-fastapi/
│   └── commonjs-to-esm/
├── runs/
├── regression-matrix.json
└── regression-report.json
```

## Run record

A published run should contain `source/`, `generated-target/`, `.migration/`, `environment.json`, `prompt.md`, `report.json`, and `report.md`. The report must state Source revision/tree digest, Target digest, Python/Node and Codex versions when available, milestone and repair counts, manual interventions, parity counts, source regressions, and the final deterministic verdict. After a `VERIFIED` run, execute the same frozen Judge against a deliberately broken Target and publish the resulting failure as negative evidence.

The regression matrix is the maintenance gate for these dated records. A
complete host with the required benchmark dependencies should return all runs
as `passed`; a host without one of those dependencies must report that run as
`blocked` and must not be presented as a new migration verdict.
