# Changelog

All notable changes to webstack will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-02

> First marketplace release. Aligns the plugin with 2026 mainstream Claude Code plugin practices, fixes plugin/agent/hook schema bugs found in pre-publish audit, and migrates hooks to the JSON-output contract.

### Changed (publish-readiness fixes)

- **Plugin manifest cleanup**: `plugin.json` adds `homepage`, drops the meaningless `engines.claude-code: ">=2.0.0"` (no canonical Claude Code engines field exists; the value let every version pass), version bumped to `0.2.0`.
- **Marketplace source format**: `marketplace.json` plugin `source` migrated from the development string `"./"` to the canonical object form `{"source": "github", "repo": "cares0/webstack"}` so `/plugin marketplace add https://github.com/cares0/webstack` resolves on user machines. `homepage` placeholder filled.
- **README placeholders filled**: `<git-url>` and `<user>` replaced with the live `cares0/webstack` URL throughout `README.md` and `package.json`. README scrubbed of Korean phrasing; a separate `README.ko.md` mirror was added for Korean readers.
- **CI plugin metadata validator rewritten**: the previous workflow asserted `display_name`/`tagline`/`categories` on `marketplace.json` — none of which exist in the actual or canonical schema, meaning CI was either red or enforcing the wrong contract. Now validates the real keys (`name`, `owner`, `plugins[].{name, description, source}`) and accepts both string and object `source`.
- **SubAgent `tools` frontmatter added** (was missing across all 10 agents): each agent now declares its tool allowlist explicitly per the `subagents` reference (comma-separated string). Read-only agents (feature-architect, code-reviewer, brand-archetype-matcher) cannot Write/Edit/Bash anymore — previously the prose said "read-only" but the harness placed no actual restriction. Implementer agents keep the full toolset.
- **Destructive skills marked `disable-model-invocation: true`**: `init`, `infra`, `deploy`, `build-be`, `build-fe` no longer auto-fire on inferred user intent. `feature` remains auto-invocable for ergonomic flow. `build-be`/`build-fe` descriptions clarified as internal sub-skills (not user-facing slash commands).
- **SubAgent → SubAgent invocation removed**: `backend-implementer` and `build-be` Phase 5 no longer instruct delegating to the `contract-drift-detective` SubAgent (Claude Code only supports single-level SubAgents reliably). The phase now does an inline drift sanity check; the canonical drift report stays in the main `/webstack:feature` Phase 7, which already orchestrates `contract-drift-detective` from the main agent.
- **Required reads → Lazy reference**: every skill and agent that previously instructed "read these 8–12 docs once at session start" now uses a `Reference docs (lazy — read on demand)` section. Docs are loaded only when the corresponding phase is reached, sharply reducing per-invocation token cost while preserving discoverability.
- **Hooks migrated to JSON output**: `block_env_read.py` and `block_env_bash.py` now emit `hookSpecificOutput.permissionDecision: "deny"` JSON on stdout (current recommended pattern) instead of the deprecated `exit 2 + stderr` legacy contract. Block reasons are surfaced to the model verbatim.
- **`block_env_bash.py` fast-path**: a single regex (`\benv\b|\.env|printenv|TOKEN|KEY|SECRET|PASSWORD|\$`) short-circuits the heavier scan for the vast majority of innocuous Bash calls (git/ls/pnpm/gradle/etc.), eliminating per-Bash Python scan cost while still catching `bare env`, `env|grep`, `cat .env*`, `printenv *_TOKEN/_KEY/_SECRET/_PASSWORD`, and `echo $*_TOKEN`. Verified against false positives like `git push origin development` and `ls vendor/`.
- **`session_start.sh` ancestor walk**: the hint now fires whether the session starts in the project root or in any sub-repo (e.g., inside `myapp-frontend/src/`). It walks up from `$PWD` looking for `.webstack/` and reports the discovered root explicitly.
- **`docs/superpowers/` excluded from the published package**: the 247KB implementation plan and 51KB design spec produced by the `superpowers` plugin during development were tracked in git and would have shipped to every marketplace user. Added to `.gitignore` and removed from the index via `git rm -r --cached`.

## [Unreleased — pre-publish audit, folded into 0.2.0]

> Post-v0.1.0 audit (2026-04-26) — pre-marketplace. Aligns the plugin with 2026 mainstream practices.

### Changed

- **Plugin entry points**: removed `commands/` directory (4 thin-wrapper files). Slash commands `/webstack:{init,feature,infra,deploy}` now load directly from `skills/<name>/SKILL.md`. Per Claude Code's plugin docs, `commands/` and `skills/` create the same slash commands and "skill takes precedence"; the wrapper layer was redundant.
- **IaC tool**: Terraform → **OpenTofu** (CNCF Sandbox, MPL 2.0, native state encryption). HCL syntax preserved; CLI is `tofu` instead of `terraform`. Provider sources resolve via `registry.opentofu.org` (mirror of Terraform Registry — `vercel/vercel`, `oracle/oci`, `supabase/supabase` work unchanged).
- **Frontend architecture**: adopted **FSD-lite** (5-layer Feature-Sliced Design adapted for Next.js App Router). `src/{app, widgets, features, entities, shared}/` with one-way imports enforced by `eslint-plugin-boundaries`. ShadCN primitives moved to `src/shared/ui/`; generated SDK to `src/shared/api/generated/`; feature schemas to `src/features/<feature>/model/schema.ts`.
- **Backend architecture**: clarified **Modulith module ↔ bounded context** mapping. Modules are domain-shaped (one per BC); hexagonal layers (`domain/`, `application/`, `infrastructure/`) live **inside** each module, not at the project top level. `hexagonal.md` + `spring-modulith.md` package-structure examples now consistent.
- **SubAgent rename**: `terraform-plan-analyzer` → `tofu-plan-analyzer` (with all skills/docs/scenarios cross-references updated).
- **Tech versions**: pin to latest mainstream stable. Spring Modulith 2.x (BOM), KoTest 6.x, Next.js 16+, React 19 (with `useActionState` / `useFormStatus` / `useOptimistic` documented), Zod v4, Tailwind v4.x. Spring Boot version resolved via Initializr metadata at scaffold time (no hardcoded outdated patch).

### Added

- `docs/frontend/fsd-architecture.md` — FSD-lite layer system, import rules, mapping to ShadCN/codegen/Zod/TanStack Query.
- TestContainers integration guidance — `docs/backend/kotest-behavior-spec.md` "Integration testing with TestContainers" section + `docs/backend/jpa-patterns.md` "Verifying migrations with TestContainers" section + `skills/build-be/SKILL.md` Phase 4.5 (mandatory TestContainers spec for any feature touching persistence).
- Infra gotcha boxes — Vercel 45-min per-build hard limit, Oracle Cloud 90-day idle reclamation prevention (cron health-check pattern), Supabase 7-day pause + ~30s cold start + RLS scope decision matrix.
- Pragmatism notes — `shared/methodologies/ddd.md` "When NOT to apply DDD" expanded; `shared/methodologies/hexagonal.md` "Pragmatism — when is the full layer cost worth it?" new section. `agents/feature-architect.md` outputs a "DDD scope decision" (`thin-crud` / `standard-DDD` / `rich-domain`) per feature.
- React 19 form hooks (`useActionState`, `useFormStatus`, `useOptimistic`) section in `docs/frontend/server-components.md`.
- Client Component `use(params)` pattern + `generateStaticParams` note in `docs/frontend/nextjs-app-router.md`.
- `Last verified: 2026-04-26` footer on every reference doc, with cadence guidance (per major upstream release or every two months).

### Fixed

- Cross-doc inconsistency where `shared/methodologies/hexagonal.md` showed top-level `domain/`/`application/`/`infrastructure/` while `docs/backend/spring-modulith.md` showed module-as-BC layout. Both now consistent: module = BC, hexagonal layers inside.

### Removed

- **Bundled authentication via Supabase Auth.** webstack no longer treats Supabase as an Auth provider. `docs/infrastructure/supabase-setup.md` was rewritten to scope Supabase to **managed Postgres only** (no Auth, Storage, Realtime, Edge Functions in webstack). The `Auth integration with Spring`, `API keys` (anon/service_role), `Row Level Security`, and `supabase CLI` sections were removed; `Why Supabase for DB + Auth` was rewritten as `Why Supabase (managed Postgres)`.
- `supabase_anon_key` and `supabase_service_role_key` outputs from `infrastructure/outputs.tf`. The remaining Supabase-derived outputs are `database_url` (pooled) and `database_direct_url` (Flyway).
- `bearerAuth` securityScheme + `'401' Unauthorized` responses from `shared/templates/openapi-spec-template.yaml`. Each project adds these back per feature when an auth path actually requires them.
- `(auth)/login` / `(auth)/signup` example route group from `docs/frontend/nextjs-app-router.md` (replaced with `(marketing)/about` to keep the example unauthenticated).
- `Supabase service_role JWT pattern` and `SUPABASE_SERVICE_ROLE_KEY` checks in `agents/security-auditor.md` were generalized to provider-agnostic backend-secret patterns (DB connection strings, generic provider tokens). The auditor still flags any token-shaped or DB-URL string in the frontend bundle.

### Added (auth opt-in)

- **Init Phase 5 question**: `/webstack:init` now asks during backend scaffolding whether the project will need user authentication. Answer is recorded as `project.needs_auth` in `manifest.yaml`.
  - **Yes** → `spring-boot-starter-security` is included in Spring Initializr deps; a permissive default `SecurityFilterChain` boots out-of-the-box; SETUP.md appends an "Authentication next steps" section pointing to the recipe below.
  - **No** → Spring Security is not on the classpath. The user can add it later via a feature PR.
- **`docs/recipes/spring-security-auth.md`** — full self-implemented Spring Security 6 + JWT (Nimbus) + BCrypt recipe. Covers the `auth/` Modulith module shape (DDD aggregate / hexagonal layers), `TokenIssuer` / `TokenVerifier` / `PasswordHasher` ports, `SecurityFilterChain`, refresh-token rotation cookie strategy, frontend integration via the `src/features/auth/` slice, and a security checklist (lockout, rate limiting, CORS, HTTPS, etc.). webstack does not bundle an external IdP — the recipe is the documented path for projects that opt in.
- `feature-architect` SubAgent now treats the `Auth:` field in its report as conditional: only filled when `needs_auth=true` AND the feature touches an authenticated endpoint. The first auth-bearing feature triggers a `CLARIFICATION NEEDED:` for strategy choice.
- Test scenario `02-feature.md` switched from a `user-login` mock to a `note-create` (unauthenticated) feature so the scenario does not depend on the auth opt-in.

## [0.1.0] - 2026-04-26

### Deferred to v0.2

- Destructive-bash hooks (`rm -rf` / `git push --force` confirmation gating). Spec §13 originally listed PreToolUse hooks for "위험한 명령" but v0.1 ships secret-isolation hooks only (block_env_read.py + block_env_bash.py). Destructive-bash protection arrives in v0.2.
- Pact consumer-driven contract testing — drift detection via springdoc only in v0.1.
- Accessibility auditor SubAgent (WCAG checks).
- DB schema designer / migration planner / infra cost estimator SubAgents.
- Real-provider API integration tests (would burn quota; manual sandbox only).
- Pre-commit secret scanning (gitleaks/trufflehog) auto-setup — flagged as SUGGESTION only.
- Remote OpenTofu state backend (Supabase Postgres / S3-compatible) with mandatory state encryption.

### Added

- Initial plugin skeleton: `.claude-plugin/plugin.json`, `marketplace.json`
- 4 user-facing slash commands: `/webstack:init`, `/webstack:feature`, `/webstack:infra`, `/webstack:deploy`
- 6 skills (init, feature, infra, deploy, build-be, build-fe — last two as sub-skills)
- 10 SubAgents (feature-architect, backend-implementer, frontend-implementer, test-runner, code-reviewer, contract-drift-detective, tofu-plan-analyzer, security-auditor, design-system-architect, brand-archetype-matcher)
- 30 reference documents (8 methodologies + 3 conventions + 5 templates + 5 frontend + 4 backend + 5 infrastructure)
- PreToolUse hooks for `.env*` Read protection + SessionStart hook
- 4 E2E test scenarios (init, feature, infra, security)
- GitHub Actions CI (markdownlint, jsonlint, yamllint, plugin metadata validation)

### Tech Stack

- Hardcoded for the initial release: NextJS + ShadCN + Tailwind v4 / Spring Boot 3 + Kotlin + KoTest BehaviorSpec + DDD/Hexagonal / Vercel + Oracle Cloud + Supabase + OpenTofu
- Modularization: pluggable per `docs/<stack>/`

### Architecture

- `shared/` (SSOT, tech-agnostic) + `docs/` (tech-specific) split
- Main agent orchestrates Skills; large-context, consistency, and isolation tasks delegated to SubAgents
- True parallel feature development via multi-repo + git worktrees
- OpenAPI 3.1 contract-first; `@hey-api/openapi-ts` for FE codegen; AI hand-writes BE; springdoc drift verification
- Secrets: environment variables + Claude Code deny rules + OpenTofu `sensitive` flag
