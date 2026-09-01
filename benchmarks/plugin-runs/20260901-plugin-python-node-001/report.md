# Installed Plugin dogfood and lifecycle run

Run: `20260901-plugin-python-node-001`  
Plugin: `migration-skill@migration-skill-dev` `0.2.0`  
Host: Windows, `codex-cli 0.147.0`

## Scope

This run uses a workspace-isolated `CODEX_HOME`. It does not change the real
user Codex home, global environment variables, production services, or
credentials. The existing blind Python CLI → Node CLI target is used as the
small fixture. The verifier bundle is copied from the installed Plugin cache
into this run before Freeze, so a Plugin cache upgrade cannot silently erase
the frozen evidence.

## Results

| Check | Result |
| --- | --- |
| Local marketplace add | `PASS` |
| Plugin discovery through host CLI | `PASS` |
| Plugin install and enabled listing | `PASS` |
| Installed Plugin verifier replay | `VERIFIED` |
| Required parity | `8/8` |
| Broken-target rejection | `PASS` |
| Upgrade to `0.2.1-test` | `PASS` |
| Resume after verifier mutation | `INVALIDATED: verifier-bundle-mismatch` |
| Rollback to `0.2.0` | `PASS` |
| Resume after rollback | `ready` |
| Uninstall preserves Source/Target/`.migration/` | `PASS` |
| Reinstall and resume | `PASS`, `ready` |
| New-session `$migration-skill` invocation | `BLOCKED` |
| Natural-language invocation | `BLOCKED` |

The installed verifier replay ran the current Plugin scripts through Contract,
Corpus, parity, Judge, Freeze, evaluator, checkpoint, and resume preflight.
The final deterministic evaluator was `VERIFIED` with eight of eight required
cases passing. The deliberately broken Target was rejected.

The upgrade test changed `compare_results.py` only to change the verifier
bundle hash. The frozen workspace snapshot remained available, and the active
`0.2.1-test` bundle caused resume to return
`verifier-bundle-mismatch`. Restoring `0.2.0` returned `ready`. Removing and
reinstalling the Plugin left the Source, Target, `.migration/`, state, Freeze,
and checkpoint evidence intact.

## Remaining host blocker

The host CLI can add the marketplace, discover the Plugin, install it, and
list it as enabled in the isolated home. A new `codex exec` session reached
session startup, but model transport failed with TLS
`invalid peer certificate: UnknownIssuer`. Therefore this run does not claim
that a new model session loaded `$migration-skill`, accepted the natural
language trigger, or generated the Target itself through the Plugin.

That last part must be completed in a normal authenticated Codex Desktop or
PowerShell environment with a working API transport before Issue #14 can be
closed and `v0.2.0` released as fully host-verified.

The complete machine-readable evidence is in this directory. The raw blind
benchmark remains separate under `benchmarks/runs/`.

The exact new-session attempt and transport failure are recorded in
[`new-session.md`](new-session.md).
