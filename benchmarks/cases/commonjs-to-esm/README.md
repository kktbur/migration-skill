# Blind benchmark: CommonJS → ESM

This case specification covers a runtime/module-format migration. It publishes only a CommonJS Source package, the Behavior Contract, parity Corpus, mutation plan, and bounded migration plan; it intentionally contains no ESM Target or reference implementation.

The package entrypoint exposes a default greeting function and a named `add` export. The parity adapter checks package-entrypoint loading, default and named exports, type/error behavior, and stable error messages without requiring a network service.

This case directory remains specification-only and contains no ESM Target. The
completed dated run [20260831-commonjs-to-esm-001](../../runs/20260831-commonjs-to-esm-001/)
generated the Target independently, froze the Judge, accepted all three
bounded milestones, passed 7/7 parity cases, and rejected three deliberately
broken Targets with the same frozen Judge.
