# Blind benchmark: Python CLI → Node CLI

This case is the first v1.2 cross-language benchmark. The versioned case contains only the Python Source, Behavior Contract, parity Corpus, mutation plan, and a three-milestone plan. It intentionally contains no Target or reference implementation.

The public operation is `main-cli/invoke`. The eight cases are input instances of that one operation: normal JSON/text output, uppercase, Unicode, empty input, invalid option, missing argument, and invalid format.

## Run protocol

The benchmark runner creates a separate run directory and gives Codex only:

```text
source/
migration.json
parity-corpus.json
migration-plan.json
mutation-plan.json
migration-skill/
```

Codex writes the generated implementation into `generated-target/` and supplies a target adapter there. The generated target is not part of this blind case. A complete run should preserve `.migration/`, the prompt, environment summary, accepted checkpoints, final verdict, and deliberately broken-target Judge result under `benchmarks/runs/<run-id>/`.

Validate the case metadata without executing a Target:

```text
python ../../../skills/migration-skill/scripts/validate_contract.py --contract migration.json --corpus parity-corpus.json
python ../../../skills/migration-skill/scripts/validate_plan.py --plan migration-plan.json --contract migration.json --corpus parity-corpus.json
python -m unittest discover -s source
```

The case is not itself a claim of `VERIFIED`; that claim requires a published run whose frozen Judge passes Source and rejects the specified mutations.
