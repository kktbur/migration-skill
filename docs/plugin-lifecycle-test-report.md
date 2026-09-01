# Plugin lifecycle test report

Date: 2026-09-01  
Plugin: `migration-skill` `0.2.0`  
Protocol: Contract schema `2`, Freeze schema `3`  
Codex CLI observed: `0.147.0`

## Executive status

`BLOCKED` for complete host-level lifecycle proof. The deterministic package,
freeze-boundary, rollback, and evidence-isolation model tests are `PASS`, but
the real Codex host has not yet completed fresh install, discovery, explicit
invocation, natural-language invocation, or Plugin dogfood migration.

Issue #14 remains open. This report must not be read as a release or closeout
claim.

The host probe reported that the current environment cannot resolve a Codex
home directory. The environment had `USERPROFILE` present but no usable
`HOME`/`CODEX_HOME` for the CLI's configuration lookup. No task-specific
`HOME` or `CODEX_HOME` value was supplied, and no host configuration or Plugin
cache was changed.

## Results

| Test | Result | Evidence / limitation |
| --- | --- | --- |
| Local marketplace staging | `PASS` | `tests/plugin_lifecycle/marketplace/.agents/plugins/marketplace.json` and temporary staging test |
| Filesystem-model fresh install | `PASS` | Versioned temporary install; no user `.migration/` is created |
| Host fresh install | `BLOCKED` | Codex home-directory resolution failed; host execution is opt-in |
| Plugin discovery in a new session | `MANUAL_REQUIRED` | The probe cannot create or inspect a new Codex session |
| `$migration-skill` invocation | `MANUAL_REQUIRED` | Requires a new host session |
| Natural-language invocation | `MANUAL_REQUIRED` | Requires a new host session |
| Raw Skill package identity | `PASS` | Staged Plugin contains the same canonical `skills/migration-skill/` package |
| Installed Plugin dogfood migration | `NOT_RUN` | Do not relabel the historical raw Skill benchmark as Plugin dogfood |
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
has produced auditable evidence for fresh install, discovery, explicit and
natural-language invocation, Plugin dogfood migration, upgrade mismatch,
rollback, uninstall, and reinstall. A host-level `BLOCKED` result is not a
successful lifecycle result.
