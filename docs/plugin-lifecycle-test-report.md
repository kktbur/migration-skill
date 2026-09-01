# Plugin lifecycle test report

Date: 2026-09-01  
Plugin: `migration-skill` `0.2.0`  
Protocol: Contract schema `2`, Freeze schema `3`  
Codex CLI observed: `0.147.0`

## Executive status

`BLOCKED` for complete host-level lifecycle proof. The deterministic package,
freeze-boundary, rollback, and evidence-isolation model tests are `PASS`. A
real `codex-cli 0.147.0` process also completed marketplace add, Plugin
discovery, installation, upgrade mismatch detection, rollback, and
uninstall/reinstall in a workspace-isolated `CODEX_HOME`. The model-backed
new-session invocation and Agent-generated Plugin dogfood remain blocked by
the host's TLS transport.

Issue #14 remains open. This report must not be read as a release or closeout
claim.

The default host probe still reports that the ambient environment has no
usable `HOME`/`CODEX_HOME` for the CLI's configuration lookup. The follow-up
used a workspace-local, disposable `CODEX_HOME` only for the child CLI
process. System `%TEMP%` is rejected by this CLI because it refuses to create
helper binaries there, so the isolated directory was placed under the project
workspace and deleted after the test. No real user Codex home or global
environment variable was changed.

## Results

| Test | Result | Evidence / limitation |
| --- | --- | --- |
| Local marketplace staging | `PASS` | `tests/plugin_lifecycle/marketplace/.agents/plugins/marketplace.json` and temporary staging test |
| Filesystem-model fresh install | `PASS` | Versioned temporary install; no user `.migration/` is created |
| Host fresh install in isolated `CODEX_HOME` | `PASS` | `codex plugin marketplace add` and `codex plugin add` completed |
| Plugin discovery through host CLI | `PASS` | `codex plugin list --available` and installed listing showed `migration-skill@migration-skill-dev` |
| Plugin discovery in a new model session | `BLOCKED` | `codex exec` could not complete model transport |
| `$migration-skill` invocation | `BLOCKED` | Session startup reached the API transport, which failed with TLS `UnknownIssuer` |
| Natural-language invocation | `BLOCKED` | Same model transport blocker; no trigger claim is made |
| Raw Skill package identity | `PASS` | Staged Plugin contains the same canonical `skills/migration-skill/` package |
| Installed Plugin verifier dogfood replay | `PASS` | `benchmarks/plugin-runs/20260901-plugin-python-node-001/` reports `VERIFIED`, 8/8 parity, and broken-target rejection |
| Agent-generated Plugin dogfood migration | `BLOCKED` | No model-backed new-session invocation was completed |
| Upgrade verifier mismatch | `PASS` | Active bundle hash change returns `verifier-bundle-mismatch` |
| Rollback recovery | `PASS` | Compatible bundle resumes and user evidence snapshots are unchanged |
| Uninstall preserves data | `PASS` | Temporary Plugin removal leaves Source, Target, and `.migration/` intact |
| Reinstall resume | `PASS` | Compatible temporary reinstall returns `ready` |
| Historical Python CLI → Node CLI evidence | `PASS` | Existing raw benchmark is `VERIFIED` and broken Target is rejected |

## What was actually tested

`tests/plugin_lifecycle/test_lifecycle.py` uses only the Python standard
library and temporary directories. It stages the root Plugin, models a
versioned cache, copies the published benchmark as immutable evidence, checks
the frozen verifier bundle, deliberately mutates a test upgrade, rolls it
back, removes the model install, and reinstalls a compatible snapshot.

`verify_resume.py --verifier-root PATH` now compares the active installed
verifier's file labels and SHA-256 hashes with the frozen
`verifier_bundle.files`. A mismatch invalidates resume without modifying the
frozen workspace.

The existing benchmark at
`benchmarks/runs/20260831-python-cli-to-node-cli-001/` remains historical raw
Skill evidence. Its `report.json` says `VERIFIED` and its broken-target
negative evidence says `failed`; it was not presented as an installed Plugin
run.

The isolated host dogfood evidence at
`benchmarks/plugin-runs/20260901-plugin-python-node-001/` is deliberately
narrower: it proves that the installed Plugin's verifier bundle can replay the
published Source/Target evidence and preserve the lifecycle boundary. It does
not claim that the unavailable model session generated the Target.

The current local suite contains 46 tests and passes on the bundled Python
runtime. The suite does not invoke `--execute-host`.

## Host probe

The safe default is:

```text
python tests/plugin_lifecycle/run_host_lifecycle.py \
  --plugin-root PATH_TO_REPOSITORY \
  --marketplace-root TEMP_MARKETPLACE \
  --output host-lifecycle.json
```

This stages a local marketplace and records manual steps only. The destructive
host actions require an explicit `--execute-host` flag and are run with
`shell=False`; their output is capped and redacted. The probe still cannot
automate the new-session Skill-discovery or trigger checks.

## Acceptance rule

Do not close Issue #14 or publish the final `v0.2.0` release until a real host
has produced auditable evidence for a new-session Skill discovery, explicit
and natural-language invocation, and Agent-generated Plugin dogfood
migration, in addition to the lifecycle checks already recorded here. A
host-level `BLOCKED` result is not a successful lifecycle result.
