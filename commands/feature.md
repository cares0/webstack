---
description: Add a new feature to an existing webstack project — creates parallel worktrees in frontend and backend repos, runs plan and OpenAPI contract interviews, orchestrates parallel BE/FE implementer SubAgents, runs tests and reviews, generates PR. Use as `/webstack:feature <feature-name>`.
---

The user invoked `/webstack:feature`. Execute the **feature** skill (`skills/feature/SKILL.md`).

## Argument

- ARGUMENTS should contain the feature name (kebab-case).
- If empty: ask user for the feature name first.

## Steps

1. Validate the feature name (kebab-case, [a-z0-9-]+, length 3-40).
2. Invoke the feature skill via the Skill tool: `Skill(skill="feature")`. Pass the feature name as initial context.
3. The skill body will run P0–P8 with checkpoints.

ARGUMENTS: $ARGUMENTS
