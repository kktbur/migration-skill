# Migration prompt

Migrate the blind Flask Source in `source/` to an independently generated
FastAPI Target in `generated-target/`.

Preserve the observable behavior declared by `.migration/migration.json` and
exercised by `.migration/parity-corpus.json`. Work through the three bounded
milestones in `.migration/migration-plan.json`. The Source is read-only after
baseline and Judge freeze. Do not copy a prebuilt Target or weaken the
Contract, Corpus, comparator, evaluator, or required gates.
