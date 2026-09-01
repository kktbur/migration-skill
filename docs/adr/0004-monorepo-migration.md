# ADR 0004: Sharded monorepo migration plan

- Status: Proposed
- Date: 2026-09-01
- Decision owners: Migration Skill maintainers

## Context

A monorepo contains multiple packages, workspaces, tools, and public
boundaries. Treating the entire repository as one prompt hides dependency
cycles, expands the rollback boundary, and makes a passing package-level
check insufficient evidence for dependents. The existing single-repository
protocol needs a workspace-level plan before it can safely handle this shape.

## Decision

Future monorepo support will create explicit migration shards and a dependency
DAG before editing. The design sequence is:

```text
Workspace inventory
        ↓
package and workspace graph
        ↓
strongly connected component detection
        ↓
public-boundary evidence
        ↓
migration shards
        ↓
dependency DAG and bounded milestones
```

### Workspace inventory

Inventory must identify package manifests, workspace declarations, source and
test roots, build/test commands, generated outputs, public exports, and
package-manager lockfiles. It must distinguish package source from generated
or vendored content and preserve evidence paths for inferred boundaries.

### Graph and cycles

Edges represent package dependencies that can affect the selected migration.
Strongly connected components are not split by guesswork. A cyclic component
is one shard unless an explicit public boundary and a verified cycle-breaking
plan are available. A graph with unresolved package discovery is `PLAN_ONLY`.

### Shards and milestones

Each shard has a stable identity, source digest, public operations, affected
dependents, required checks, and rollback boundary. Milestones follow the DAG:
dependencies are migrated and verified before their affected dependents, or a
documented compatibility seam is introduced and tested. A single milestone
must not span the whole monorepo merely for convenience.

### Digest and affected scope

The future evidence model should retain a workspace digest, package/shard
digests, dependency-edge digest, and public-surface digest. When a shard
changes, revalidation covers that shard and its affected dependents; an
unchanged independent shard is not silently treated as newly verified.

## Verification boundary

Every shard uses the same Contract/Judge/Freeze/Ratchet rules as a single
repository. Cross-shard public operations require cases at the consumer
boundary, not only unit tests inside the provider. A final `VERIFIED` result
requires all required shards, affected dependents, and public operations to be
covered; a percentage of migrated packages cannot substitute for a required
gap.

## Non-goals for this phase

- No monorepo Agent Runtime or graph parser is implemented here.
- No one-shot super-prompt for the whole workspace.
- No parallel milestone execution yet.
- No automatic package publishing, deployment, or production traffic change.

Parallel migration is a later design topic. It is allowed only after shard
identities, dependency independence, merge conflict handling, and a final
cross-shard parity gate are specified and tested.

## Consequences

The shard model increases inventory and planning work, but makes ownership,
rollback, affected-scope revalidation, and evidence review explicit. It also
gives the protocol a safe place to stop when cycles or public boundaries are
not understood instead of presenting partial monorepo coverage as complete.
