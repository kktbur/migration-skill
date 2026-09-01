# Post-v1 roadmap and boundaries

This document records deferred work so future contributors do not silently expand the v1 safety model.

## Plugin distribution (v0.2 lifecycle validation)

The repository now contains a skills-only Plugin at `.codex-plugin/plugin.json`
and the canonical raw Skill under `skills/migration-skill/`. The remaining v0.2
work is host-level lifecycle validation: fresh install, discovery, explicit
invocation, upgrade mismatch detection, rollback, uninstall, and reinstall.
Plugin registration is distribution plumbing; it is not a replacement for the
Contract/Judge/Freeze protocol.

Before calling the Plugin lifecycle complete:

1. validate the package in a fresh Codex session;
2. document the exact installed `SKILL.md` path and trigger behavior;
3. prove that an incompatible active verifier bundle blocks resume;
4. prove rollback and reinstall preserve `.migration/` and Target evidence;
5. preserve the standard-library-only offline test path;
6. review permissions and do not make GitHub, Exa, MCP, or network access hard dependencies.

## In-place and strangler migration

In-place migration is deferred. When introduced, it must operate on an explicit Git branch or worktree and retain a reversible boundary. A strangler migration needs explicit ownership of each public operation, routing/traffic policy, rollback behavior, and production authorization; those concerns are outside the local v1 evaluator.

## Large monorepos

Large monorepos need partition-aware inventory, dependency graph/SCC handling, workspace-level Contracts, and a checkpoint namespace that cannot confuse sibling packages. Until those pieces exist, a large or high-risk monorepo should produce a plan or a bounded package migration rather than claiming one-click completion.

## Maintenance loop

Protocol changes should update the schema validator, public helper tests, mutation tests, freeze bundle behavior, references, CI, and benchmark evidence together. Any change to comparator semantics, environment policy, operation coverage, or evaluator gates requires a new tool version and a new Freeze for existing migrations.
