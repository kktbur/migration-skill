# Plugin uninstall and reinstall

Plugin lifecycle data and user migration data have different ownership. The
host package may be removed; the migration workspace must remain recoverable.

## Offline/model checks

The test removes only the temporary installed Plugin directory and verifies
that the Source, generated Target, `.migration/`, frozen manifest, state, and
results are unchanged. It then reinstalls the compatible verifier snapshot and
confirms that resume preflight returns `ready`.

## Host steps

After a real host uninstall, inspect the migration workspace independently of
the Plugin cache. Reinstall a compatible Plugin version, start a new session,
run resume preflight, and continue only when the frozen verifier and Target
checkpoint match.

## Current result

The deterministic uninstall/reinstall isolation test is `PASS`. Host uninstall
and reinstall are not executed automatically because they mutate Codex host
state; they remain manual and are blocked in the current environment.
