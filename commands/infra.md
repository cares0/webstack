---
description: Apply or modify infrastructure (Vercel + Oracle Cloud + Supabase via Terraform). Run after init when user has signed up and exported tokens. Always shows plan and asks for explicit confirmation before any apply/destroy.
---

The user invoked `/webstack:infra`. Execute the **infra** skill (`skills/infra/SKILL.md`).

## Pre-conditions

- `<project_root>/.webstack/manifest.yaml` exists (init has been run).
- The user has signed up for Vercel/Oracle/Supabase and filled `<infra-repo>/.env`.
- The user has exported environment variables in the current shell.

## Steps

1. Invoke the infra skill: `Skill(skill="infra")`.
2. The skill runs P0 (security-auditor pre-flight) → P1 (terraform plan) → P2 (terraform-plan-analyzer) → P3 (user confirmation) → P4 (apply, only if confirmed) → P5 (manifest update).
3. Never skip the confirmation phase. Apply/destroy require explicit `apply` (and `I understand` for high-risk) typed by the user.

ARGUMENTS: $ARGUMENTS
