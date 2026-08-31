# Benchmark prompt

Migrate this Python CLI to a Node.js CLI while preserving the externally observable behavior described by `migration.json` and `parity-corpus.json`.

Use the Migration Skill protocol. Keep `source/` read-only, generate the Target under `generated-target/`, validate the Judge before Freeze, and execute exactly the bounded milestones in `migration-plan.json`. Before each new edit, run the resume preflight. Accept a milestone only through the deterministic milestone evaluator and atomic checkpoint script. Do not modify required cases, comparators, evaluator, or frozen verifier assets to make a result pass.

The case is intentionally blind: there is no reference Target. Use only the Source, Contract, Corpus, Plan, mutation plan, and the supplied Migration Skill scripts.
