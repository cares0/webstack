# webstack

> Brand-driven fullstack scaffolding with contract-first APIs and free-tier infra — for Claude Code.

`webstack` guides you through a structured fullstack build cycle:

1. **Brand identity & persona interview** — distill what your service stands for and who it serves.
2. **Design system extraction** — derive tokens, ShadCN theme, and component variants from identity + persona (Refactoring UI principles).
3. **Multi-repo scaffolding** — create `<project>-frontend/` (Next.js + ShadCN + Tailwind v4), `<project>-backend/` (Spring Boot 3 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec), `<project>-infrastructure/` (OpenTofu).
4. **Parallel feature development** — git worktrees per feature, OpenAPI 3.1 contract-first, parallel BE/FE implementer SubAgents.
5. **Free-tier deploy** — Vercel + Oracle Cloud Always Free + Supabase via OpenTofu IaC.

## Install

```text
# 1. Add this marketplace (one-time):
/plugin marketplace add https://github.com/cares0/webstack

# 2. Install the plugin from the marketplace:
/plugin install webstack@webstack-marketplace
```

The marketplace name is `webstack-marketplace` (declared in `.claude-plugin/marketplace.json`); the plugin name is `webstack`. If you cloned the repo locally for development, point `marketplace add` at the local path instead of the GitHub URL. Per Claude Code's plugin docs, the marketplace add step is required before any `plugin install` will resolve.

> Korean version: see [README.ko.md](README.ko.md).

## Quick start

```
cd <empty parent dir for your project>
/webstack:init             # one-time — identity → design system → 3 repos + SETUP.md
# Sign up for Vercel/Oracle/Supabase per SETUP.md, fill .env, export
/webstack:infra            # one-time — tofu plan → confirm → apply

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
- `<project>-infrastructure/` — OpenTofu with vercel/vercel + oracle/oci + supabase/supabase providers.

## What's specialized (SubAgents)

- `feature-architect` — domain & route mapping after plan.
- `backend-implementer` / `frontend-implementer` — parallel impl in worktrees.
- `code-reviewer` — DDD/RSC/Clean Code review.
- `contract-drift-detective` — springdoc vs OpenAPI YAML diff.
- `test-runner` — KoTest + Vitest + Playwright.
- `tofu-plan-analyzer` — plan output classification + risk + free-tier impact.
- `security-auditor` — secret hygiene + deny rules + skip-permissions check.
- `design-system-architect` — tokens + variants from identity/persona.
- `brand-archetype-matcher` — Jung 12 archetype scoring.

## Security model

- AI never reads `.env*` files (deny rules + PreToolUse hooks).
- Tokens live in user shell environment; OpenTofu reads them, AI doesn't see values.
- All OpenTofu sensitive variables marked `sensitive = true`.
- All destructive operations (apply/destroy/deploy) require explicit confirmation.

## Authentication

webstack does not bundle authentication. During `/webstack:init` Phase 5, the user is asked whether the project will need user authentication:

- **Yes** → `spring-boot-starter-security` is added to the backend's classpath; `docs/recipes/spring-security-auth.md` is linked from the project's SETUP.md and walks through self-implemented JWT + BCrypt (or OAuth2 social login) using Spring Security 6 directly. Supabase Auth is **not** used.
- **No** → the backend ships without Spring Security. Add it later via a feature PR if/when authentication becomes a requirement.

Supabase is used **strictly as managed Postgres** in webstack — Auth, Storage, Realtime, Edge Functions are out of scope. Swapping to AWS RDS / Neon / self-hosted Postgres later is a `<infra>/supabase.tf` + `DATABASE_URL` change, not a re-platform.

## Tech stack (initial release)

| Layer | Stack |
|---|---|
| Frontend | Next.js 16+ App Router + React 19 + ShadCN + Tailwind v4 + RHF + Zod v4 + TanStack Query v5 + @hey-api/openapi-ts. **FSD-lite** layering (`src/{app, widgets, features, entities, shared}/`). |
| Backend | Spring Boot 3 + Kotlin + DDD/Hexagonal + Spring Modulith 2.x (one module per bounded context) + KoTest BehaviorSpec 6.x + JPA + Flyway + springdoc-openapi + TestContainers (`@ServiceConnection`). Spring Security is **opt-in at init** for projects that need authentication — see `docs/recipes/spring-security-auth.md`. |
| Infra | Vercel (Hobby) + Oracle Cloud Always Free (Ampere A1 ARM) + Supabase (managed Postgres only — no Auth/Storage/Realtime/Edge) + **OpenTofu** 1.10+ |
| Contract | OpenAPI 3.1 |

## Extending to new stacks

The split between `shared/` (tech-agnostic methodologies) and `docs/` (tech-specific guides) is intentional:

- To add support for a new stack: drop new docs into `docs/<frontend-or-backend-or-infra>-<stack>/`, add a parallel implementer SubAgent (`agents/<stack>-implementer.md`), add a sub-skill (`skills/build-<stack>/SKILL.md`).
- `shared/` is stable across stacks.

## Troubleshooting

**Slash command `/webstack:init` not found after install.**
Run `/reload-plugins` in Claude Code. If still missing, verify `/plugin list` shows `webstack` enabled. Plugin commands appear under the namespace `/<plugin-name>:<skill-name>`, not as bare `/init`.

**`/webstack:infra` fails at the OpenTofu CLI check.**
webstack pins OpenTofu ≥ 1.10. Install with `brew install opentofu` (macOS) or via the official installer (https://opentofu.org/docs/intro/install/), then re-run. The CLI is `tofu`, not `terraform` — webstack uses `tofu` for forward compatibility with state encryption and CNCF governance.

**Spring Modulith verifier test fails after first feature.**
Most likely a cross-module import landed in `<module-b>/application/...` or `<module-b>/infrastructure/...` from another module. Cross-module collaboration must go through published events (`@ApplicationModuleListener`), not direct service injection. See `docs/backend/spring-modulith.md` "Module dependency rules".

**`pnpm lint` fails with `eslint-plugin-boundaries` errors.**
The frontend follows FSD-lite (5 layers, one-way imports `app > widgets > features > entities > shared`). A failure here means a slice imported from a higher layer or sideways. Fix the import direction; do not relax the lint config. See `docs/frontend/fsd-architecture.md`.

**Vercel build fails with "Build exceeded maximum allowed duration".**
The Hobby plan has a 45-minute per-build hard limit (regardless of monthly minutes remaining). If your Next.js build exceeds it, reduce `generateStaticParams` set, move to ISR / on-demand revalidation, or upgrade to Vercel Pro for the 60-minute limit. See `docs/infrastructure/vercel-setup.md`.

**Oracle Cloud VM disappeared after a few weeks.**
OCI's Always Free tier reclaims idle VMs (typically after extended idleness — exact threshold per Oracle's FAQ). webstack documents two preventions: monthly OCI Console login or a cron-driven health-check from any always-on host. Re-running `/webstack:infra` + `/webstack:deploy` restores the backend in minutes once tokens are re-exported. See `docs/infrastructure/oracle-cloud-setup.md` "Resource reclamation prevention".

**Supabase project's first request after a quiet week takes ~30 seconds.**
Free Supabase projects pause after 7 days of inactivity and resume on the next request. Set up a periodic health-check cron, or upgrade to Pro. See `docs/infrastructure/supabase-setup.md` "Pause behavior gotcha".

## License

MIT — see LICENSE.

## Contributing

PRs welcome. Run `npm run lint:md && npm run lint:json && npm run lint:yaml` before submitting.
