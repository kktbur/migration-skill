# Migration report

- Migration: Python CLI → Node CLI
- Run: `20260831-python-cli-to-node-cli-001`
- Source tree: read-only; no Source regression detected
- Milestones accepted: `M1`, `M2`, `M3`
- Required parity: `8/8`
- Final deterministic state: `VERIFIED`
- Frozen Judge negative control: a `hello` → `goodbye` Target mutation returned `failed`
- Resume preflight: `ready` on the accepted Target; a tampered Target returned `invalidated`

The detailed public run report is in `../report.md`; machine-readable evidence is in `../report.json` and `results/`.
