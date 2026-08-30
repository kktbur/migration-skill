# Safety and isolation

The helper scripts are deterministic command runners, not a security sandbox.

## Command review

Before executing a check, inspect its argv and classify it. Ask for authorization or stop for commands that deploy, delete, write production data, change cloud resources, alter credentials, require privileged access, or run unknown install scripts.

Commands such as package installation, integration tests, cloud SDK calls, native builds, and external API probes may use the network. `shell=False` prevents shell parsing; it does not block network access.

## Source handling

Inventory the original source without executing project code. If a baseline command needs to create caches or generated files, run it in a disposable source copy or a sandbox. Keep the original revision and tree digest as the evidence anchor.

## Secrets

Do not copy `.env`, SSH keys, cloud configuration, credential files, or API tokens into the target or `.migration/`. Use environment injection outside the recorded artifacts when a user-authorized test genuinely requires a secret. Never serialize environment values.

## Sandbox decision

Use a real Docker or sandbox boundary for native code, unknown scripts, external services, or high-risk repositories when the host provides one. If a reliable boundary is unavailable, return `PLAN_ONLY` or ask the user to authorize the specific execution. Never report a subprocess wrapper as network isolation.
