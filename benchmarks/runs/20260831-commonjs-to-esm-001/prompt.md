# Blind migration prompt

Migrate the CommonJS package in `source/` to an independently writable ESM
package in `generated-target/`.

Preserve the externally observable package behavior described by
`.migration/migration.json` and `.migration/parity-corpus.json`. Work through
the bounded milestones in `.migration/migration-plan.json`, run the frozen
Source/Target checks and parity after each milestone, and do not modify the
Source or weaken the Contract, Corpus, comparator, Judge, or evaluator.

The Target must use native Node.js ESM semantics (`package.json` with
`type: module`, ESM exports, and an ESM adapter) while preserving default and
named exports, numeric validation, error names, and error messages.
