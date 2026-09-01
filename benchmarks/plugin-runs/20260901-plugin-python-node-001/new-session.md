# New-session invocation attempt

The local marketplace and `migration-skill@migration-skill-dev` `0.2.0`
Plugin were installed in a workspace-isolated `CODEX_HOME`. A fresh
non-interactive Codex session was then started with a prompt containing
`$migration-skill` and explicit instructions not to modify files.

Observed result:

- Codex emitted `thread.started` and `turn.started`.
- Model transport then failed with TLS `invalid peer certificate: UnknownIssuer`
  while connecting to the Responses endpoint.
- No final model response was produced, so explicit Skill invocation is not
  marked as passed.
- The natural-language trigger was not run after the same transport failure.

This is host transport evidence, not a Plugin or verifier failure. The run
therefore remains `BLOCKED` for full model-backed dogfood and Issue #14 is not
closed by this artifact.
