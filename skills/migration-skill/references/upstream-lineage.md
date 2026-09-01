# Upstream lineage

This skill is an original Codex-native implementation of a machine-verifiable migration protocol, not a code fork.

## `gpt-migrate`

The primary reference is [`joshpxyne/gpt-migrate`](https://github.com/joshpxyne/gpt-migrate). Its README and `main.py` show the useful workflow shape: setup, recursive dependency-aware migration, target execution, generated tests, and log-driven debugging. This project deliberately does not copy its LLM client, prompt hierarchy, Tree-sitter downloader, Docker lifecycle, or file-output parser.

The useful lineage is:

```text
gpt-migrate's migration / run / debug loop
        ↓
Codex-native repository operations
        ↓
Contract → Corpus → Frozen Judge → Ratchet
```

## Methodological references

- **Anthropic Code Migration Kit**: Judge-before-migration, old code as executable specification, portable parity harness, mutation validation, dependency mapping, and gap inventory.
- **GitHub Next Crane**: bounded milestones, persistent state, verification ratchet, deterministic completion gates, and checkpoint-oriented execution.
- **OpenAI sandboxed migration examples**: trusted-host versus isolated-execution boundaries and keeping credentials outside the execution workspace.

These references influence the protocol, but no source file, LLM SDK, prompt tree, Agent Runtime, GitHub workflow engine, Tree-sitter runtime, Docker orchestrator, or MCP service is vendored from them. The intended differentiation is a reusable local protocol whose Contract, Corpus, verifier bundle, operations, and checkpoint state can be inspected and machine-verified.

If future work copies a third-party file, add its license, copyright, attribution, and modified notice before distribution.
