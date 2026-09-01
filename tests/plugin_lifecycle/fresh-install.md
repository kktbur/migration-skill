# Fresh Plugin install

This test covers the boundary between the repository Plugin package and a
Codex host. It deliberately separates checks that can run in a temporary
directory from checks that require a real Codex session.

## Offline/model checks

`test_lifecycle.py` stages the current root package into a temporary local
marketplace with this layout:

```text
marketplace/
├── .agents/plugins/marketplace.json
└── plugins/migration-skill/
    ├── .codex-plugin/plugin.json
    └── skills/migration-skill/
```

The test verifies the local source entry, Plugin manifest, canonical Skill
path, and the fact that installation does not create a `.migration/` folder.
It models a versioned install in a temporary cache only; it never writes to
the user's Codex home.

## Host steps

Run the probe without `--execute-host` to produce the marketplace and manual
instructions. If host mutation is explicitly authorized, repeat with
`--execute-host`, then start a new Codex session and check:

1. the marketplace is configured;
2. `migration-skill` is visible and installable;
3. the canonical `skills/migration-skill/SKILL.md` is discoverable.

The probe cannot start or inspect a new Codex session. The `$migration-skill`
invocation check therefore remains manual.

## Current result

The offline/model check is `PASS`. Host installation and discovery are
`BLOCKED` in the current environment because `codex-cli 0.147.0` reports that
it cannot resolve a home directory. No `HOME` or `CODEX_HOME` override was
applied and no host configuration was changed.
