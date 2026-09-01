# ADR 0001: Skills-only Plugin distribution

- Status: Accepted
- Date: 2026-09-01
- Decision owners: Migration Skill maintainers

## Context

Migration Skill already has a usable raw Skill and a deterministic local
protocol. The next distribution step is to make that Skill discoverable and
installable as a Codex Plugin without introducing a second runtime. The
protocol's evidence artifacts must remain portable across Codex sessions and
must not become dependent on a mutable Plugin cache.

The Plugin is therefore a packaging and lifecycle boundary. It is not a
replacement for the `Contract -> Judge -> Freeze -> Ratchet` protocol, and it
does not make a general promise that every repository can be migrated
automatically.

## Decision

The repository root is a skills-only Codex Plugin. Its required manifest is:

```text
.codex-plugin/plugin.json
```

The manifest points to `./skills/`, and the canonical raw Skill lives at:

```text
skills/migration-skill/
├── SKILL.md
├── agents/openai.yaml
├── references/
└── scripts/
```

That directory is independently usable as a raw Skill: a user may copy or
reference `skills/migration-skill/` without installing the Plugin. The Plugin
adds discovery, versioned packaging, and the host's install/update/rollback/
uninstall lifecycle. It does not add an LLM SDK, MCP server, Docker
orchestrator, background Agent Runtime, or production integration.

The machine-readable compatibility policy is kept in
`docs/plugin-compatibility.json`. The current release candidate is Plugin `0.2.0-rc.1`, with
Contract schema `2` and Freeze schema `3`.

## Version compatibility

Plugin version, Contract schema, and Freeze schema are separate version
domains:

| Plugin range | Contract schema | Freeze schema | Policy |
| --- | ---: | ---: | --- |
| `0.2.0-rc.1` | 2 | 3 | Release candidate; supported by this package |
| `0.3.x` | 3 | 4 | Future; migration required |

A Plugin patch update may fix packaging or documentation without changing the
protocol. A Contract or Freeze schema change is a protocol migration and must
not be silently treated as a compatible Plugin update. A future package must
extend the compatibility document and add migration tests before claiming
support for a new combination.

## Lifecycle semantics

### Fresh install

Install the repository Plugin through the Codex Plugin mechanism using a
reviewed Git ref or release. Installation makes `migration-skill` discoverable
and exposes the canonical Skill. The raw Skill remains available for local
repository-scoped use, so Plugin installation is optional for the protocol
itself. A fresh install does not create or modify a user's `.migration/`
workspace.

### Upgrade

An upgrade changes the discoverable package for new work. Before resuming an
existing migration, the Skill must run the resume/freeze preflight and verify
the exact verifier bundle recorded in `freeze-manifest.json`. The preflight
checks the frozen file hashes, schema version, source revision/tree digest, and
the workspace-relative bundle paths. The newly installed Plugin must not be
allowed to replace or reinterpret that bundle silently.

If the upgraded package cannot verify the existing bundle, the migration is
`INVALIDATED` (or `PLAN_ONLY` when it can only be planned). The safe recovery is
to retain the evidence, restore a compatible package/bundle, or explicitly
re-run Inventory, Baseline, Judge validation, and Freeze. No evidence is
silently upgraded in place.

### Rollback

Rollback restores the previous Plugin package, but it does not delete the
migration workspace, target, accepted checkpoints, or benchmark evidence. A
rollback is usable for an in-progress migration only after the same frozen
bundle preflight succeeds. If the exact frozen verifier is unavailable, the
migration remains invalidated until evidence is rebuilt and re-frozen.

### Uninstall

Uninstall removes the Plugin from the host's installed/discoverable package
set. It must not remove a user's source tree, isolated target, `.migration/`
artifacts, or published benchmark evidence. Those files belong to the user and
are the recovery record for an interrupted migration. Reinstalling a compatible
Plugin may resume the work after preflight.

The exact host cache cleanup behavior is delegated to the Codex Plugin host;
this repository does not claim that a host's uninstall operation has been
tested on every Codex surface.

## Frozen verifier boundary

The Freeze artifact, not the currently installed Plugin, is the authority for
an in-progress migration. `freeze_contract.py` records the source evidence,
Contract, Corpus, Judge artifact, normalization/check specification, and the
complete verifier bundle. The bundle includes the helper dependencies that
define comparison and evaluation semantics, not only the evaluator entrypoint.

The following invariants apply:

1. A Plugin update cannot replace a frozen verifier file while a migration is
   in progress.
2. A changed verifier hash, Contract, Corpus, evaluator dependency, Source
   revision, or Source tree digest invalidates the freeze.
3. A schema mismatch is an explicit compatibility failure, not a best-effort
   parse or automatic downgrade.
4. A user may intentionally rebuild evidence, but that requires a new
   Inventory/Baseline/Judge/Freeze sequence and a new manifest.
5. `advance_milestone.py` remains the only authority that atomically accepts a
   verified checkpoint; Plugin lifecycle actions never advance a milestone.

When the active Skill comes from a Plugin cache, resume callers should pass
that installation's `skills/migration-skill/scripts/` directory to
`verify_resume.py --verifier-root`. The preflight compares the installed
bundle's labels and hashes with the frozen bundle and returns an explicit
`verifier-bundle-mismatch` invalidation before any target edit. A raw Skill
checkout may omit this option because its verifier root is already the one
selected by the caller.

Where the Plugin host uses a mutable installation cache, a migration should
use a workspace-local or copied verifier bundle whose hashes are recorded in
the Freeze manifest. The package update can change the Skill instructions for
future actions, but it cannot change the already-frozen Judge semantics.

## Non-goals and consequences

This decision intentionally does not add MCP. MCP may be useful as a future
integration, but it is not required to install, discover, or run this
skills-only Plugin. The deterministic helpers continue to use Python's
standard library and do not claim to provide network isolation.

The nested canonical path makes the Plugin structure explicit and prevents two
independently edited copies of `SKILL.md` from drifting. It is a small breaking
change for older checkouts that expected a root-level Skill; the README now
points those users to `skills/migration-skill/`.

The Plugin lifecycle is intentionally thin. It provides packaging and
compatibility metadata, while the existing local protocol remains responsible
for safety, evidence, verification, and deterministic verdicts.
