# ADR 0002: Isolated worktree boundary for in-place migration

- Status: Proposed
- Date: 2026-09-01
- Decision owners: Migration Skill maintainers

## Context

The default Migration Skill strategy writes an independent Target while the
Source remains readable and unchanged. An in-place request has a different
user expectation, but directly editing the current working tree would make
the Source identity, rollback boundary, and user's unrelated changes
ambiguous. A migration may also be interrupted between milestones, so a
reversible boundary must exist outside the active checkout.

## Decision

Future in-place support will use a dedicated Git worktree or a dedicated
migration branch. It will never write directly to the user's current working
tree. The current checkout remains the user's untouched workspace and the
migration checkout is the only mutable implementation workspace.

The lifecycle is:

```text
capture Source identity and working-tree state
        ↓
create dedicated migration branch/worktree
        ↓
Inventory → Baseline → Judge → Freeze
        ↓
Codex edits migration worktree only
        ↓
Judge + checks + ratchet accept checkpoints
        ↓
human reviews and merges the verified branch
```

### Source identity

Before any edit, record the Source commit when available, the Source tree
digest, and whether the caller's working tree is dirty. A dirty working tree
must not be silently folded into a migration. The caller must either provide a
clean revision or explicitly choose a captured working-tree snapshot whose
diff is recorded as input evidence. Unrelated dirty files remain outside the
migration scope.

### Branch and worktree ownership

The migration branch/worktree belongs to one migration identifier and one
Source identity. Its name and location are recorded in the migration state;
the protocol does not assume ownership of the user's default branch. The
branch is not pushed, merged, rebased, or deleted automatically.

### Checkpoints and rollback

Each accepted milestone records the Target revision or tree digest, result
digest, milestone ID, and verification evidence through the existing ratchet.
Rollback means returning to the last accepted checkpoint or abandoning the
dedicated worktree; it must not erase the Source evidence or `.migration/`
record. A rollback that cannot satisfy the frozen verifier preflight is
`INVALIDATED`, not silently repaired by changing the Judge.

### Merge policy

Only a human or an explicitly authorized repository workflow may merge the
verified migration branch. Before merge, rerun the final required checks on
the branch, confirm the Source identity has not changed, and review the diff
for unrelated files. A `VERIFIED` result is evidence for the branch; it is not
authorization to deploy or merge it.

## Consequences

This boundary makes interruptions and review recoverable, at the cost of an
extra worktree and an explicit merge step. It also means a dirty checkout may
become `PLAN_ONLY` until its input snapshot is clarified. The existing
isolated Target strategy remains the v1/v1.2 default; this ADR only records the
future in-place design and does not add an implementation.

## Non-goals

- Direct mutation of the active working tree.
- Automatic push, merge, force-reset, or branch deletion.
- Production deployment or database migration.
- Treating a worktree as a network or privilege sandbox.
