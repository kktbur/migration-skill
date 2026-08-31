# Blind benchmark: CommonJS → ESM

This case specification covers a runtime/module-format migration. It publishes only a CommonJS Source package, the Behavior Contract, parity Corpus, mutation plan, and bounded migration plan; it intentionally contains no ESM Target or reference implementation.

The package entrypoint exposes a default greeting function and a named `add` export. The parity adapter checks package-entrypoint loading, default and named exports, type/error behavior, and stable error messages without requiring a network service.

This case is a specification only. A future run must generate the ESM package in `generated-target/`, freeze the Judge, accept all bounded milestones, and prove that a broken Target is rejected.
