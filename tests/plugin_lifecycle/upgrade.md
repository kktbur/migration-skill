# Plugin upgrade and frozen-verifier mismatch

An installed Plugin update may change the Skill available for future work, but
it must not silently change the verifier for an in-progress migration.

## Offline/model checks

The lifecycle test copies the published Python CLI → Node CLI run into a
temporary directory. The benchmark's own `freeze-manifest.json` and verifier
snapshot remain unchanged. A compatible `0.2.0` verifier bundle passes
`verify_resume.py` with `--verifier-root`.

The test then creates a separate `0.2.1-test` install and appends a harmless
comment to `common.py`. This changes the bundle hash without changing the
frozen workspace. Resume preflight returns `invalidated` with reason
`verifier-bundle-mismatch`. The frozen verifier is never overwritten.

## Host steps

With a real host, install `0.2.0`, accept at least one milestone, then install
the test update. Start a new session and run the resume preflight using the
active Plugin verifier root. The session must stop before editing and require
either rollback to a compatible bundle or a complete new
Inventory/Baseline/Judge/Freeze sequence.

## Current result

The deterministic mismatch test is `PASS`. Real host upgrade and new-session
resume are not yet proven; they remain part of the current Issue #14 host
blocker.
