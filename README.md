# webstack

> Brand-driven fullstack scaffolding with contract-first APIs and free-tier infra — for Claude Code.

`webstack` guides you through a structured fullstack build cycle:

1. **Brand identity & persona interview** — distill what your service stands for and who it serves.
2. **Design system extraction** — derive tokens, ShadCN theme, and component variants from identity + persona (Refactoring UI principles).
3. **Multi-repo scaffolding** — create `<project>-frontend/` (Next.js + ShadCN + Tailwind v4), `<project>-backend/` (Spring Boot 3 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec), `<project>-infrastructure/` (Terraform).
4. **Parallel feature development** — git worktrees per feature, OpenAPI 3.1 contract-first, parallel BE/FE implementer SubAgents.
5. **Free-tier deploy** — Vercel + Oracle Cloud Always Free + Supabase via Terraform IaC.

## Install

```text
# 1. Add this marketplace (one-time, replace <git-url> with the actual webstack repo URL):
/plugin marketplace add <git-url>

# 2. Install the plugin from the marketplace:
/plugin install webstack@webstack-marketplace
```

The marketplace name is `webstack-marketplace` (declared in `.claude-plugin/marketplace.json`); the plugin name is `webstack`. If you cloned the repo locally, point `marketplace add` at the local path. Per Claude Code's plugin docs, the marketplace add step is required before any `plugin install` will resolve.

## Quick start

```
cd <empty parent dir for your project>
/webstack:init             # 1회 — identity → design system → 3 repos + SETUP.md
# Sign up for Vercel/Oracle/Supabase per SETUP.md, fill .env, export
/webstack:infra            # 1회 — terraform plan → confirm → apply

# For each feature
/webstack:feature <name>   # plan → contract → parallel BE/FE → test → review → PR

# When ready to ship
/webstack:deploy           # FE auto-deploys via push, BE SCP+systemd
```

## What gets generated

Per project, `.webstack/` (parent dir):

```
.webstack/
├── manifest.yaml              project metadata
├── identity.md                brand archetype + tone
├── personas/primary.md        Cooper-format persona
├── design-system/             tokens.json + theme.css + component-variants.md
├── contracts/<feature>.yaml   OpenAPI 3.1 per feature
├── features/<feature>/        plan + status + worktree paths
└── SETUP.md                   infra signup guide
```

Three sibling git repos (created by init):

- `<project>-frontend/` — Next.js App Router + ShadCN + Tailwind v4 + RHF/Zod + TanStack Query.
- `<project>-backend/` — Spring Boot 3 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec + Spring Modulith + Flyway.
- `<project>-infrastructure/` — Terraform with vercel/vercel + oracle/oci + supabase/supabase providers.

## What's specialized (SubAgents)

- `feature-architect` — domain & route mapping after plan.
- `backend-implementer` / `frontend-implementer` — parallel impl in worktrees.
- `code-reviewer` — DDD/RSC/Clean Code review.
- `contract-drift-detective` — springdoc vs OpenAPI YAML diff.
- `test-runner` — KoTest + Vitest + Playwright.
- `terraform-plan-analyzer` — plan output classification + risk + free-tier impact.
- `security-auditor` — secret hygiene + deny rules + skip-permissions check.
- `design-system-architect` — tokens + variants from identity/persona.
- `brand-archetype-matcher` — Jung 12 archetype scoring.

## Security model

- AI never reads `.env*` files (deny rules + PreToolUse hooks).
- Tokens live in user shell environment; terraform reads them, AI doesn't see values.
- All terraform sensitive variables marked `sensitive = true`.
- All destructive operations (apply/destroy/deploy) require explicit confirmation.

## Tech stack (1차)

| Layer | Stack |
|---|---|
| Frontend | Next.js 15 + ShadCN + Tailwind v4 + RHF + Zod + TanStack Query + @hey-api/openapi-ts |
| Backend | Spring Boot 3 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec + Spring Modulith + JPA + Flyway + springdoc-openapi |
| Infra | Vercel + Oracle Cloud Always Free + Supabase + Terraform |
| Contract | OpenAPI 3.1 |

## Extending to new stacks

The split between `shared/` (tech-agnostic methodologies) and `docs/` (tech-specific guides) is intentional:

- To add support for a new stack: drop new docs into `docs/<frontend-or-backend-or-infra>-<stack>/`, add a parallel implementer SubAgent (`agents/<stack>-implementer.md`), add a sub-skill (`skills/build-<stack>/SKILL.md`).
- `shared/` is stable across stacks.

## License

MIT — see LICENSE.

## Contributing

PRs welcome. Run `npm run lint:md && npm run lint:json && npm run lint:yaml` before submitting.
