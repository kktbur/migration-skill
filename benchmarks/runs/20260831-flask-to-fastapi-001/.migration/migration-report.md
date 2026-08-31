# Migration report

## Deterministic verdict

The final evaluator returned `VERIFIED`. The freeze manifest remained intact,
the Source tree digest matched the frozen baseline, no new Source regression
was found, all configured Target test checks passed, all 21 required parity
cases passed, and all five required public operations were covered.

## Accepted checkpoints

| Milestone | Scope | Required proof |
| --- | --- | --- |
| M1 | FastAPI startup and health | `health` + `target-m1-tests` |
| M2 | User lookup and search | M1 proof + 7 lookup/search cases + `target-m2-tests` |
| M3 | User creation and deletion | M1/M2 proof + 13 write/delete cases + `target-m3-tests` |

The state file records M1, M2, and M3 as accepted and protects the complete
21-case proof set.

## Negative evidence

The frozen Judge detected each targeted mutation in its required case. The
negative evidence is stored under `.migration/results/` with the corresponding
broken-target parity output.

## Engineering observations

- Windows Unicode transport required ASCII-safe JSON on the parity wire.
- Flask and FastAPI do not choose the same default behavior for empty 204
  responses; the Contract explicitly freezes the response content type.
- FastAPI's default request validation can produce 422, so the target parses
  the request body manually to preserve the source's 400 behavior.
