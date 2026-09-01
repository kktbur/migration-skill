# Host E2E result: Python CLI -> Node CLI

Test object: Migration Skill `v0.2.0-rc.1`, Contract schema 2, Freeze schema 3, Codex CLI `0.147.0` on Windows.

## Completed

- Model transport smoke: PASS on the earlier read-only TUN-path check; `UnknownIssuer` was not reproduced in that check.
- Follow-up workspace-write transport probe: `BLOCKED`. With a disposable workspace-local `CODEX_HOME`, the model connection failed with `UnknownIssuer` over WebSocket and then HTTPS fallback before the requested filesystem write was reached. TLS verification remained enabled.
- Local marketplace installation and enabled Plugin discovery: PASS.
- Fresh-session bundled Skill loading: PASS.
- Explicit `$migration-skill` invocation: PASS.
- Natural-language implicit selection: PASS; the model selected and loaded `migration-skill` without the Skill name in the prompt.
- The deterministic protocol replay in this isolated run: `VERIFIED`.
- Target began empty and the independently generated Node target passed its target checks.
- Required parity: `8/8`.
- M1, M2, and M3 were each accepted by the verifier ratchet.
- Frozen Judge rejected both targeted broken targets: `normal-json` greeting mutation and `invalid-option` exit-code mutation.

## Remaining gate

The installed Plugin Agent could not complete the write-enabled dogfood step. The first nested Codex `workspace-write` attempt returned `helper_unknown_error: setup refresh had errors` before even harmless commands could run. A follow-up with a disposable workspace-local `CODEX_HOME` reached model startup but failed on `UnknownIssuer` before the write command. A controlled `danger-full-access` workaround was rejected because it would remove the enforceable filesystem boundary.

The target in this evidence was therefore produced by the current Codex implementation session in the isolated run directory, not by a successful nested installed-Plugin write session. This is useful protocol evidence but does not satisfy the final Host E2E gate.

## Verdict

`host_e2e_status: BLOCKED` and `release_gate: NOT_CLEARED`.

Do not close Issue #16 or promote `v0.2.0` based on this run. Re-run the remaining Agent-write step on a Host where both model transport and nested `workspace-write` command execution are available, or perform it manually in a fresh Codex Desktop/CLI session with the same RC and clean network path. Do not disable TLS verification.
