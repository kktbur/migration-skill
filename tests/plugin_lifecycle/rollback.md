# Plugin rollback

Rollback changes the installed Plugin package, not the user's migration
evidence.

## Offline/model checks

The test creates compatible `0.2.0` and incompatible `0.2.1-test` verifier
directories. It removes the test version, restores the compatible bundle, and
runs resume preflight. Before and after snapshots of `source/`,
`generated-target/`, and `.migration/` must be identical, and the preflight
must return `ready`.

## Host steps

On a real host, roll back the installed Plugin after the upgrade mismatch is
detected. Do not copy the new bundle over the frozen workspace. Re-run resume
preflight and confirm the exact frozen bundle is available before continuing.

## Current result

The temporary filesystem rollback and evidence-preservation test is `PASS`.
Real Codex host rollback is not claimed because host installation is currently
blocked by home-directory resolution.
