---
description: Deploy frontend (Vercel auto-deploy on push to main) and/or backend (Oracle Cloud SCP + systemd) after feature merge. Pre-flight runs security-auditor and test-runner; user explicitly chooses target.
---

The user invoked `/webstack:deploy`. Execute the **deploy** skill (`skills/deploy/SKILL.md`).

## Pre-conditions

- Infrastructure already provisioned (`/webstack:infra` was run successfully).
- Both repos' main branches are clean and pushed.
- Tests pass on main (skill verifies).

## Steps

1. Invoke the deploy skill: `Skill(skill="deploy")`.
2. The skill runs P0 (pre-flight: security + test) → P1 (target selection: FE/BE/both) → P2-3 (deploy actions) → P4 (result + manifest update).
3. Never auto-deploy without explicit `deploy` confirmation.

ARGUMENTS: $ARGUMENTS
