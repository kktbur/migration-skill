# ADR 0003: Operation-based strangler migration boundary

- Status: Proposed
- Date: 2026-09-01
- Decision owners: Migration Skill maintainers

## Context

Some migrations cannot replace a whole application at once. A service may
have independent public operations, or old and new modules may need to coexist
while behavior is established. Calling this a "strangler migration" must not
silently imply production traffic switching, gateway mutation, or data-plane
authority.

## Decision

Future strangler support will be operation-based. Each old operation is mapped
to a new implementation, exercised by the same frozen Judge, and retired from
the migration plan only after its required evidence is accepted.

```text
operation A: old → new → parity → accept
operation B: old → new → parity → accept
operation C: old → new → parity → accept
        ↓
all scoped old operations retired from the plan
```

The plan must record, for every operation:

- the old and new implementation boundaries;
- the routing or dispatch intent in local test execution;
- dependencies and data assumptions;
- the required Contract operation and Corpus cases;
- the fallback boundary before acceptance;
- the checkpoint and evidence that permits retirement.

The Source remains available as the reference implementation until all
required operations are accepted. A missing route, untested fallback, or
unresolved shared-state assumption keeps the operation `BLOCKED` or
`PARTIALLY_VERIFIED`.

## Safety boundary

This protocol may produce a local routing plan, migration implementation, and
verification evidence. It must not:

- switch production traffic;
- modify a real gateway, load balancer, service mesh, or DNS record;
- write a production database;
- rotate credentials or change production configuration;
- claim that local parity proves concurrency, capacity, or operational safety.

Any future production integration must be a separately authorized system with
its own deployment and rollback controls.

## Acceptance and retirement

An operation is eligible for retirement only when its required cases pass on
Source and Target, the Judge has valid negative controls, the frozen verifier
is intact, and the milestone ratchet accepts the checkpoint. Retiring an
operation means removing it from the local migration scope; it does not mean
deleting Source code or changing production routing.

The final local completion condition is that every required scoped operation
has an accepted new implementation and no required gap remains. The phrase
"old operations = 0" is therefore a plan-completeness statement, not a
production cutover assertion.

## Consequences

Operation-level decomposition makes rollback and evidence local, but it
requires an explicit public-operation inventory and can expose shared state
that a whole-application rewrite would hide. The design favors smaller
verified slices over a single routing prompt. It is a future design only; no
strangler executor or production router is introduced by this ADR.
