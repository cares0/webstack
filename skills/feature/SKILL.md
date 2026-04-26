---
name: feature
description: Use when adding a new feature to an existing webstack project (.webstack/manifest.yaml exists). Creates parallel git worktrees in frontend and backend repos; runs feature plan and OpenAPI contract interviews; orchestrates parallel backend-implementer and frontend-implementer SubAgents inside the worktrees; runs test-runner, code-reviewer, and contract-drift-detective; produces a PR creation guide. N times per project, parallel-safe.
---

# feature skill — webstack feature workflow

You are running `/webstack:feature <name>`. Coordinate parallel subagents across two worktrees, but interact with the user yourself for design decisions.

## Required reads

- `shared/methodologies/api-first.md`
- `shared/methodologies/ddd.md`
- `shared/methodologies/clean-code.md`
- `shared/conventions/git-workflow.md`
- `shared/conventions/conventional-commits.md`
- `shared/conventions/pr-template.md`
- `shared/templates/prd-template.md`
- `shared/templates/openapi-spec-template.yaml`

## Pre-flight (P0)

1. Verify `<project_root>/.webstack/manifest.yaml` exists. If not: tell user to run `/webstack:init` first; abort.
2. Validate `<feature_name>`: kebab-case, [a-z0-9-]+, length 3-40, not already used (`.webstack/features/<name>/` shouldn't exist; if it does, ask: resume or rename?).
3. Check both repos clean: `cd <fe-repo> && git status --porcelain` empty; same for backend. If dirty: tell user to commit/stash; abort.
4. Confirm with user: "About to create worktrees for `<feature_name>` in `<fe-repo>` and `<be-repo>`. Proceed?"

## Phase 1: Worktree creation

For each repo (frontend, backend):

```bash
cd <repo>
git fetch origin
git worktree add .worktrees/<feature_name> -b feature/<feature_name> origin/main
```

Record absolute paths in `<project_root>/.webstack/features/<feature_name>/worktree-paths.yaml`:

```yaml
feature: <name>
created_at: <ISO timestamp>
worktrees:
  frontend: <absolute-path>
  backend: <absolute-path>
branches:
  frontend: feature/<feature_name>
  backend: feature/<feature_name>
```

## Phase 2: plan-feature interview (Planner role)

Use `shared/templates/prd-template.md` as scaffold. Walk user through:

- Goal (1 sentence).
- User stories: which persona (cite from `.webstack/personas/`), action, benefit.
- Screens / routes (table: route / auth / desc / server-or-client).
- Functions / behaviors.
- Business rules (invariants).
- Data model impact (new aggregates? schema migration?).
- Non-functional requirements.
- Out of scope.

Write `<project_root>/.webstack/features/<feature_name>/plan.md`.

Checkpoint: "Plan captured. Proceed to architect analysis?"

## Phase 2.5: Architect analysis

Invoke `feature-architect` SubAgent with `project_root`, `feature_name`, `plan_path`. Receive markdown report.

Show user the architect's domain mapping suggestion. Two paths:

- Accept (proceed to contract).
- Refine plan (back to P2, edit plan.md, re-invoke architect).

If architect surfaces `CLARIFICATION NEEDED:`: resolve with user, re-invoke until clean.

## Phase 3: sync-contract — OpenAPI YAML

1. Copy `shared/templates/openapi-spec-template.yaml` to `<project_root>/.webstack/contracts/<feature_name>.yaml`.
2. Substitute `<feature>`, `<resource>` per architect report and plan.
3. For each endpoint suggested:
   - Define request body schema (use plan + architect aggregate fields).
   - Define response schemas (success + error).
   - Define query/path parameters.
   - Add `tags`, `operationId`, `summary` per architect.
4. Show user the YAML diff (or full content). Ask for review.

Checkpoint: "Contract finalized. Proceed to parallel implementation?"

## Phase 4-5: Parallel implementation (backend-implementer + frontend-implementer)

Invoke both SubAgents in **parallel** using Task tool's multiple parallel calls:

### Task call 1: backend-implementer

- worktree_path: `<be-worktree>`
- contract_path: `<contract>`
- plan_path: `<plan>`
- architect_report: <architect's markdown report>
- project_root: `<project_root>`

### Task call 2: frontend-implementer

- worktree_path: `<fe-worktree>`
- contract_path: `<contract>`
- plan_path: `<plan>`
- architect_report: <architect's markdown report>
- design_system_path: `<project_root>/.webstack/design-system/`

Wait for both to complete.

Handle escalations: if either returns `CLARIFICATION NEEDED:`, resolve with user via AskUserQuestion or natural Q&A, then re-invoke that SubAgent (only the one that escalated) with the answer prepended to inputs.

Repeat escalation loop until both produce successful status (`be-status.md` + `fe-status.md` written, "Definition of Done" satisfied).

## Phase 6: Test runner

Invoke `test-runner` SubAgent with both worktrees. Receive structured report.

If failures (Critical or 1+ failing test):

- Show report to user. Ask: "Failures found — re-invoke implementers to fix, or pause for manual?"
- If re-invoke: feed failures into the relevant implementer's prompt. Loop until tests pass.

## Phase 7: Review (parallel)

Invoke `code-reviewer` and `contract-drift-detective` in **parallel**.

Wait for both. Aggregate findings.

If Critical findings:

- Show all to user.
- Ask: "Re-invoke implementers to address Critical, or accept and address in a follow-up PR?"
- If re-invoke: feed each implementer the relevant Critical items as new clarifications. Loop until clean.

## Phase 8: PR generation guidance

For each repo, in its worktree:

1. Push: `cd <worktree> && git push -u origin feature/<feature_name>`.
2. Generate PR title from feature plan: `feat(<scope>): <feature_name> — <one-liner>`.
3. Compose PR body using `shared/conventions/pr-template.md`. Cross-link the other repo's PR (after both pushed).
4. Run: `gh pr create --title "..." --body "..."`. Capture URL.

Update `.webstack/manifest.yaml`:

- features list: add entry with status=in_review, both PR URLs.

Print summary:

> Feature `<name>` ready for review.
>
> - Backend PR: <url>
> - Frontend PR: <url>
> - Plan: `<path>`
> - Contract: `<path>`
> - Status: `<be-status.md path>` + `<fe-status.md path>`
>
> After merging both PRs, you can clean up worktrees with:
> `git worktree remove .worktrees/<name>` in each repo.

## Escalation Protocol

Beyond SubAgent escalations: if the plan turns out fundamentally inconsistent (e.g., persona conflict with feature, contract impossible to satisfy with chosen stack), stop and ask user.

## Style

- Communicate phase progress with one-line announcements ("Phase 4-5: invoking implementers in parallel...").
- After parallel SubAgents return, show a 2-3 line summary of each before deciding next step.
