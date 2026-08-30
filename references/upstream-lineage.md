# Upstream lineage

This skill is an original Codex-native implementation of the workflow idea, not a code fork.

## `gpt-migrate`

The primary reference is [`joshpxyne/gpt-migrate`](https://github.com/joshpxyne/gpt-migrate). Its README and `main.py` show the useful workflow shape: setup, recursive dependency-aware migration, target execution, generated tests, and log-driven debugging. The implementation deliberately does not copy its LLM client, prompt hierarchy, Tree-sitter downloader, Docker lifecycle, or file-output parser.

The following upstream issues became design requirements:

- [#2](https://github.com/joshpxyne/gpt-migrate/issues/2): bound large inputs instead of constructing unbounded prompts;
- [#5](https://github.com/joshpxyne/gpt-migrate/issues/5): let the agent inspect dependencies across files;
- [#26](https://github.com/joshpxyne/gpt-migrate/issues/26): preserve internal functions and consumers rather than relying on incomplete per-file context;
- [#44](https://github.com/joshpxyne/gpt-migrate/issues/44): record and control oversized command/evidence payloads.

## Methodological references

The project plan also draws on the Judge-before-migration, executable-spec, bounded-milestone, and verification-ratchet patterns identified in the supplied research. Those patterns are expressed here as Contract, Corpus, freeze manifest, state checkpoints, and deterministic evaluator rather than copied runtime code.

No source file from the referenced projects is vendored. If future work copies a third-party file, add its license, copyright, attribution, and modified notice before distribution.
