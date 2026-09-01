# Plugin lifecycle test report

Date: 2026-09-01  
Lifecycle baseline: `migration-skill` `0.2.0`; release candidate: `0.2.0-rc.1`  
Protocol: Contract schema `2`, Freeze schema `3`  
Codex CLI observed: `0.147.0`

## Executive status

`BLOCKED` for complete host-level lifecycle proof. The deterministic package,
freeze-boundary, rollback, and evidence-isolation model tests are `PASS`. A
real `codex-cli 0.147.0` process also completed marketplace add, Plugin
discovery, installation, upgrade mismatch detection, rollback, and
uninstall/reinstall in a workspace-isolated `CODEX_HOME`. The latest RC host
attempt completed fresh-session loading plus explicit and natural-language
selection; the remaining Agent-generated Plugin write step is blocked by the
nested Windows `workspace-write` command sandbox, not by a reproduced TLS
`UnknownIssuer` error.

The Plugin distribution acceptance tracked by Issue #14 is complete. The
remaining model-backed host validation is tracked separately in Issue #16. The
release candidate must not be read as a final host-E2E or production-readiness
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
| Plugin discovery in a new model session | `PASS` | Fresh `codex-cli 0.147.0` session loaded the installed RC Skill |
| `$migration-skill` invocation | `PASS` | Explicit invocation completed read-only migration workflow selection |
| Natural-language invocation | `PASS` | Fresh session selected and loaded `migration-skill` without the Skill name in the prompt |
| Raw Skill package identity | `PASS` | Staged Plugin contains the same canonical `skills/migration-skill/` package |
| Installed Plugin verifier dogfood replay | `PASS` | `benchmarks/plugin-runs/20260901-plugin-python-node-001/` reports `VERIFIED`, 8/8 parity, and broken-target rejection |
| Agent-generated Plugin dogfood migration | `BLOCKED` | Nested Windows `workspace-write` returned `helper_unknown_error: setup refresh had errors` before command execution |
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

The latest RC host attempt is recorded under
`benchmarks/plugin-runs/20260901-host-e2e-python-node-001/dogfood/`. It proves
RC installation, fresh-session Skill loading, explicit invocation,
natural-language selection, a complete deterministic replay (`VERIFIED`, 8/8
parity, M1/M2/M3 accepted), and frozen-Judge rejection of two targeted broken
Targets. The Target in this run was generated by the current Codex session
after the nested Plugin write step failed; therefore this evidence does not
close Issue #16 or clear the final release gate.

The current local suite contains 55 tests and passes on the bundled Python
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

Do not publish the final `v0.2.0` release until a real host has produced
auditable evidence for Agent-generated Plugin dogfood migration from an empty
Target, in addition to the lifecycle checks already recorded here. That write
step is the remaining acceptance criterion in Issue #16. A host-level
`BLOCKED` result is not a successful lifecycle result.
