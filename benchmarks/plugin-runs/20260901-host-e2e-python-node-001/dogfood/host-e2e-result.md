# Host E2E result: Python CLI -> Node CLI

Test object: Migration Skill `v0.2.0-rc.1`, Contract schema 2, Freeze schema 3, Codex CLI `0.147.0` on Windows.

## Completed

- Model transport smoke: PASS; `UnknownIssuer` did not reproduce on the tested TUN path.
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

The installed Plugin Agent could not complete the write-enabled dogfood step. The nested Codex `workspace-write` sandbox returned `helper_unknown_error: setup refresh had errors` before even harmless commands could run. A controlled `danger-full-access` workaround was rejected because it would remove the enforceable filesystem boundary.

The target in this evidence was therefore produced by the current Codex implementation session in the isolated run directory, not by a successful nested installed-Plugin write session. This is useful protocol evidence but does not satisfy the final Host E2E gate.

## Verdict

`host_e2e_status: BLOCKED` and `release_gate: NOT_CLEARED`.

Do not close Issue #16 or promote `v0.2.0` based on this run. Re-run the remaining Agent-write step on a Host where nested `workspace-write` command execution is available, or perform it manually in a fresh Codex Desktop/CLI session with the same RC and clean network path.
