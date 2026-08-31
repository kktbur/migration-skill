# Python CLI → Node CLI fixture

This is a small, dependency-free cross-language fixture for exercising the public adapter protocol. It covers a happy path, an empty-input boundary, an error path, exit codes, and JSON output.

It is intentionally a benchmark fixture rather than a claim that Codex has already migrated this code. To run the deterministic parity portion from this directory:

```text
python ../../scripts/validate_contract.py --contract migration.json --corpus parity-corpus.json
python ../../scripts/run_parity.py --root source --contract migration.json --corpus parity-corpus.json --profile source --var PYTHON=python --output source-parity.json
python ../../scripts/run_parity.py --root target --contract migration.json --corpus parity-corpus.json --profile target --var PYTHON=python --output target-parity.json
python -m unittest discover -s source
node target/test.js
```

The final compare/freeze/mutation steps should be performed in a temporary migration workspace so generated evidence is not committed into the fixture. The other planned benchmark families are described in [`../README.md`](../README.md).
