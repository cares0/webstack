---
description: Initialize a new fullstack web project (identity → persona → design system → repo scaffolds → infra setup guide). Run once per project.
---

The user invoked `/webstack:init`. Execute the **init** skill (located at `skills/init/SKILL.md`) which defines the full phase flow.

## Pre-conditions

- Current working directory should be the **parent directory** that will hold `.webstack/` and the three sibling repos.

## Steps

1. Invoke the init skill via the Skill tool: `Skill(skill="init")`. The skill body will guide you through P0–P6 + completion.
2. Stay in interview/checkpoint discipline — do not skip phases.
3. If user provided arguments (e.g., a project name), pass them as context to phase 0.

ARGUMENTS: $ARGUMENTS
