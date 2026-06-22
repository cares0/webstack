---
name: init
description: Use when starting a new fullstack web service from scratch (empty parent directory, no .webstack/ yet). Conducts identity, persona, and design system interviews; scaffolds three git repositories (frontend, backend, infrastructure); generates the design system tokens, ShadCN theme, and component variants; outputs a SETUP.md guide for the user to sign up for free-tier infrastructure (Vercel, Oracle Cloud, Supabase). Run once per project.
disable-model-invocation: true
---

# init skill — webstack project setup

You are running `/webstack:init` for a new webstack project. Follow this phase flow strictly. The user expects deliberate, checkpoint-gated progress — never skip phases or auto-merge decisions.

## Reference docs (lazy — read on demand)

These references are loaded **lazily** — do NOT preload at P0. When a phase below names a doc, Read it at that point only. The list here is for discoverability.

- `shared/methodologies/brand-identity-discovery.md`
- `shared/methodologies/persona-creation.md`
- `shared/methodologies/design-system-extraction.md`
- `shared/methodologies/api-first.md`
- `docs/frontend/nextjs-app-router.md`
- `docs/frontend/shadcn-customization.md`
- `docs/frontend/tailwind-v4.md`
- `docs/backend/spring-modulith.md`
- `docs/infrastructure/setup-guide.md`
- `shared/conventions/git-workflow.md`
- `docs/frontend/accessibility.md`
- `docs/frontend/performance.md`
- `docs/cross-cutting/owasp-top10-cheatsheet.md`
- `docs/cross-cutting/pre-commit-hooks.md`
- `docs/cross-cutting/adr-and-c4.md`
- `docs/infrastructure/ci-cd.md`
- `docs/infrastructure/free-tier-safety.md`

## Pre-flight (P0)

1. Verify cwd is the intended **parent directory** (will hold `.webstack/` + 3 sibling repos). Ask user to confirm with `pwd`.
2. Verify directory is empty (`ls` shows nothing or only intended seed files like a README).
3. Verify CLI tooling: `git --version`, `gh --version` (required for repo create), `node --version` (≥20), `pnpm --version`, `tofu --version` (OpenTofu — warning if missing, only needed in infra phase). Report missing.
4. Ask user for project name (kebab-case). Validate.
5. Confirm: "Ready to start identity interview for `<project>`. Proceed?"

## Phase 1: Identity interview

Use AskUserQuestion (or natural Q&A) to capture, in order:

1. **One-line definition** — "Describe the service in one sentence."
2. **Core values (pick 3)** — present a curated list of 30 with multi-select.
3. **Tone keywords (3-7)** — free-text or pick from suggestions.
4. **Category** — B2B/B2C/B2B2C/SaaS/marketplace/etc., multi-select.
5. **Brand archetype self-pick** — list the 12 with one-line each; allow "unsure".
6. **Reference assets (optional)** — Figma URL / mood board image path. Do NOT auto-fetch URLs; just record.

Invoke `brand-archetype-matcher` SubAgent with the captured intake. Receive primary + supplemental archetype + confidence.

If confidence Low: ask user to confirm/refine. Re-invoke if needed.

Write `<project_root>/.webstack/identity.md` per the `identity.md` schema in `shared/schemas.md`.

Checkpoint: "Identity captured. Proceed to persona?"

## Phase 2: Persona interview

For the **primary** persona, capture (one section at a time):

- Name (made-up), age, occupation, location.
- Goals (end / experience / life — see persona-creation.md).
- Pain points with current alternatives.
- Usage context (device, environment, frequency, attention level).
- Quote (one line that captures their attitude).

Optionally add a secondary persona (ask user; default skip in 1차).

Write `<project_root>/.webstack/personas/primary.md` (and `secondary.md` if applicable).

Checkpoint: "Persona captured. Proceed to design system extraction?"

## Phase 3: Design system extraction

Invoke `design-system-architect` SubAgent with the four inputs the agent declares (see `agents/design-system-architect.md`):

- `identity_path`: absolute path to `<project_root>/.webstack/identity.md`
- `personas_dir`: absolute path to `<project_root>/.webstack/personas/`
- `output_dir`: absolute path to `<project_root>/.webstack/design-system/` (the agent will create this dir if absent)
- `reference_assets` (optional): list of absolute paths to user-provided mood images / Figma exports captured during P1 step 6 — pass an empty list if none

The agent writes `tokens.json`, `theme.css`, and `component-variants.md` to `output_dir` and returns a summary message.

Show the user a brief textual summary (palette name, type families, density). Offer 3 paths:

- Accept as-is.
- Iterate (re-invoke architect with feedback).
- Manual override (user edits `tokens.json` directly, then re-runs architect to regenerate `theme.css` + variants).

Checkpoint: "Design system finalized. Proceed to repo scaffolding?"

## Phase 4: Frontend repo scaffolding

webstack frontends use **FSD-lite** (5 layers under `src/`: `app`, `widgets`, `features`, `entities`, `shared`). The init scaffolds the empty layer skeleton + lint enforcement; features/entities/widgets are populated later by `/webstack:feature`.

1. `gh repo create <project>-frontend --private --clone` (or `--public` per user preference). If `gh` not configured: instruct user to run `gh auth login`.
2. `git clone` into sibling dir.
3. `cd <project>-frontend && pnpm dlx create-next-app@latest . --ts --tailwind --app --src-dir --no-eslint --import-alias "@/*"` (latest Next.js stable; App Router default).
4. Replace generated `app/globals.css` (or `src/app/globals.css`) with content adapted from `<project_root>/.webstack/design-system/theme.css`. Ensure `@import "tailwindcss"` and `@theme {}` block.
5. **Create FSD-lite skeleton** under `src/`:

   ```
   src/
   ├── app/                            # Next.js App Router routes + FSD app-layer (providers, layout, styles)
   │   ├── layout.tsx                  # already created by create-next-app — wrap with QueryProvider
   │   ├── page.tsx                    # already created — replaceable later
   │   ├── globals.css
   │   └── providers/
   │       └── QueryProvider.tsx       # 'use client'; QueryClientProvider + ReactQueryDevtools
   ├── widgets/                        # composite UI (filled by /webstack:feature)
   │   └── .gitkeep
   ├── features/                       # user-facing interactions (filled by /webstack:feature)
   │   └── .gitkeep
   ├── entities/                       # domain entities (filled by /webstack:feature)
   │   └── .gitkeep
   └── shared/
       ├── ui/                         # ShadCN primitives land here (Step 7)
       ├── api/
       │   └── generated/              # @hey-api/openapi-ts output (Phase added per feature)
       │       └── .gitkeep
       ├── lib/
       │   └── utils.ts                # cn() etc — written by ShadCN init
       ├── config/
       │   └── .gitkeep
       └── hooks/
           └── .gitkeep
   ```

6. **Configure ShadCN with FSD aliases.** Run `pnpm dlx shadcn@latest init` and respond with:
   - Style: New York (current default).
   - Base color: per design system theme.
   - CSS variables: yes.
   - Components alias: `@/shared/ui` (overrides default `@/components`).
   - Utils alias: `@/shared/lib/utils`.
   - UI alias: `@/shared/ui`.
   - Lib alias: `@/shared/lib`.
   - Hooks alias: `@/shared/hooks`.

   The resulting `components.json` should match the layout shown in `docs/frontend/shadcn-customization.md`. Verify before continuing — ShadCN's prompts change between releases.
7. Install ShadCN initial components: button, card, input, form, label, badge, dialog, sheet, dropdown-menu, tooltip. (`shadcn add <name>` for each.) They land in `src/shared/ui/` per the alias.
8. Apply component-variants.md cva extensions to `src/shared/ui/button.tsx` etc.
9. Install + configure: `react-hook-form`, `zod`, `@hookform/resolvers/zod`, `@tanstack/react-query`, `@tanstack/react-query-devtools`, `@hey-api/openapi-ts`, `@hey-api/client-fetch`, `eslint`, `eslint-config-next`, `eslint-plugin-boundaries`.
10. Add `openapi-ts.config.ts` with `output: 'src/shared/api/generated'` and `input` pointing to `../.webstack/contracts/` (glob — runtime: each feature has its own).
11. **Configure FSD layer enforcement** via `eslint.config.mjs` (or `.eslintrc.cjs` if older toolchain). Use `eslint-plugin-boundaries` with the 5 elements (`app`, `widgets`, `features`, `entities`, `shared`) and the dependency rule `app > widgets > features > entities > shared` (each layer can only import from layers strictly below). Same-layer imports (widget→widget, feature→feature, entity→entity) are denied. See `docs/frontend/fsd-architecture.md` for the rule layout.
12. Add `package.json` scripts: `typecheck`, `lint`, `test` (Vitest), `format`, `gen:api` (openapi-ts).
13. Initial commit: "feat: init <project>-frontend (Next.js + ShadCN + Tailwind v4 + FSD-lite)".
14. `git push -u origin main`.

Checkpoint: "Frontend repo created and pushed. Proceed to backend?"

## Phase 5: Backend repo scaffolding

1. `gh repo create <project>-backend --private --clone`.
2. `git clone` into sibling dir.
3. **Authentication decision (one-time, per project)**. Ask the user via `AskUserQuestion`:

   > "Will this project need user authentication? webstack does not bundle an auth provider — if yes, the recommended path is **self-implemented Spring Security** (JWT + BCrypt or OAuth2 social login). See `docs/recipes/spring-security-auth.md` for the full guide.
   >
   > - **Yes — add Spring Security baseline** (recommended for any user-facing product). Adds `spring-boot-starter-security` to the Initializr deps, links the recipe in SETUP.md, and the first auth-related feature can follow the recipe.
   > - **No — skip for now**. The Spring app starts without Spring Security on the classpath. You can add it later via a feature PR if/when authentication becomes a requirement."

   Record the choice as `needs_auth: true|false` in `.webstack/manifest.yaml` under `project.needs_auth`. The downstream Initializr deps and SETUP.md branch on this value.

4. Use Spring Initializr API or curl to generate base. Resolve `<latest-stable>` against https://start.spring.io at run time (do **not** hardcode an outdated patch — the CI flow will fail-fast if Initializr rejects an unsupported version):

   ```bash
   # Look up the current default at https://start.spring.io and substitute below.
   # Spring Boot 4.0.x line (GA 2025-11): Java 17 baseline; 21 and 25 also supported. webstack defaults to javaVersion=21 (a current LTS) below — bump to 25 if you want the latest LTS. Resolve bootVersion dynamically so an outdated patch never gets hardcoded.
   BOOT_VERSION="$(curl -s https://start.spring.io/metadata/client | python3 -c 'import json,sys; print(json.load(sys.stdin)["bootVersion"]["default"])')"

   # Base deps (always). Add 'security' conditionally below.
   DEPS="web,validation,data-jpa,flyway,actuator,configuration-processor"
   # If user answered "Yes" in Step 3:
   #   DEPS="$DEPS,security"
   # Resolve from the manifest you just wrote, not from a literal — keep this command shape.

   curl https://start.spring.io/starter.zip \
     -d type=gradle-project-kotlin \
     -d language=kotlin \
     -d bootVersion=$BOOT_VERSION \
     -d baseDir=. \
     -d groupId=<org-or-com.example> \
     -d artifactId=<project> \
     -d packageName=com.<org>.<project> \
     -d javaVersion=21 \
     -d dependencies=$DEPS \
     -o starter.zip && unzip starter.zip && rm starter.zip
   ```

5. Edit `build.gradle.kts` to add:
   - KoTest: `testImplementation("io.kotest:kotest-runner-junit5:<v>")`, `kotest-assertions-core`, `kotest-extensions-spring`.
   - MockK: `testImplementation("io.mockk:mockk:<v>")`, `com.ninja-squad:springmockk:<v>`.
   - Spring Modulith: `org.springframework.modulith:spring-modulith-starter-core` + `spring-modulith-starter-jpa` + `spring-modulith-events-jpa`.
   - springdoc-openapi-starter-webmvc-ui.
   - Postgres driver (`org.postgresql:postgresql`) and HikariCP (default).
   - **If `needs_auth=true`**: do not add JWT libraries here — `docs/recipes/spring-security-auth.md` walks the user through choosing between `spring-boot-starter-security-oauth2-resource-server` (Nimbus, default for Spring; renamed from `spring-boot-starter-oauth2-resource-server` in Spring Boot 4) or `io.jsonwebtoken:jjwt-*` and applying the right `SecurityFilterChain`. Init only ensures `spring-boot-starter-security` is on the classpath via the Initializr dep added in Step 4.
6. Create the Modulith + Hexagonal package skeleton. Modules (top-level packages) map 1:1 to bounded contexts; **hexagonal layers live inside each module**. At init time we don't know the BCs yet, so create only the application root + a `core/` placeholder module that the first feature will rename or split:

   ```
   src/main/kotlin/com/<org>/<project>/
   ├── <Project>Application.kt
   └── core/                              # placeholder module — first feature renames or replaces
       ├── package-info.java              # @org.springframework.modulith.ApplicationModule(displayName="Core")
       ├── domain/
       ├── application/
       └── infrastructure/
           ├── http/
           ├── persistence/
           └── config/
   ```

   The `core/` package is just a placeholder so `./gradlew test` / Modulith's verifier can run on day one. The first `/webstack:feature` invocation will (per the architect's BC mapping) either rename `core/` to a real BC name or add sibling modules (`billing/`, `catalog/`, `order/`, …) — never recreate the top-level `domain/` / `application/` / `infrastructure/` directories.

7. Create `src/main/resources/application.yml` with spring profiles (default, dev) + flyway + JPA + springdoc paths. **If `needs_auth=true`**, also add a stub `SecurityConfig` permitting all requests by default (`SecurityFilterChain.permitAll()`) so the app boots out-of-the-box; `docs/recipes/spring-security-auth.md` walks the user through tightening it for the first auth feature.
8. Create `src/main/resources/db/migration/V1__init.sql` (empty migration placeholder, comment).
9. Create initial KoTest spec to ensure the test runner works: `<Project>ApplicationTests.kt` (one passing test) and `ModulithBoundaryTest.kt` calling `ApplicationModules.of(<Project>Application::class.java).verify()` so the build fails fast on any future module-boundary violation.
10. Initial commit + push.

Checkpoint: "Backend repo created. Proceed to infrastructure?"

## Phase 5.5: Optional integrations

Use `AskUserQuestion` for 4 questions. Save each response to `<project_root>/.webstack/manifest.yaml` under `optional_integrations`. SETUP.md conditional sections (defined in `docs/infrastructure/setup-guide.md`) are activated/deactivated based on these flags.

### Q1 — Observability (Sentry + Grafana Cloud + UptimeRobot)

> "Activate observability stack? Backend gets OTel agent + Micrometer + Logback JSON encoder dependencies. Frontend gets Sentry SDK + Error Boundary. SETUP.md gets the signup walkthrough. Small projects can skip and enable later via `recipes/observability-setup.md`."

- **Yes** → BE `build.gradle.kts` adds OTel + Micrometer + Logback encoder, FE adds `@sentry/nextjs`, SETUP.md gets `## Observability setup` section, manifest `observability: true`.
- **No** → no changes. Reference docs remain in `docs/`.
- default: **No**.

### Q2 — Internationalization (next-intl)

> "Multi-language support? Adds next-intl + middleware + `[locale]` segment + `messages/` directory."

- **Yes** → next-intl dependency + middleware + `[locale]` scaffold, manifest `i18n: true`.
- **No** → no changes.
- default: **No**.

### Q3 — Automated dependency upgrades (Renovate)

> "Install Renovate? Strongly recommended. 3-repo `renovate.json` written; user installs the GitHub App per recipes/renovate-setup.md."

- **Yes** → 3 repos get `renovate.json`, SETUP.md gets `## Renovate setup` section pointing to the recipe, manifest `renovate: true`.
- **No** → no changes.
- default: **Yes** (strongly recommended).

### Q4 — Release management (git-cliff + Vercel Rolling Releases)

> "Activate release management now? Recommended after first production deploy."

- **Yes** → git-cliff `cliff.toml` + GitHub release workflow + Vercel Rolling Releases setup notes, manifest `release_management: true`.
- **No** → no changes. Activate later via `recipes/release-management-setup.md`.
- default: **No**.

### Manifest schema

Append `optional_integrations` to `<project_root>/.webstack/manifest.yaml` (in addition to the existing `project.needs_auth` field set in Phase 5):

```yaml
optional_integrations:
  observability: false        # Q1
  i18n: false                 # Q2
  renovate: true              # Q3 (default Yes)
  release_management: false   # Q4
```

Existing webstack projects without this field default to all-`false` except `renovate: true`. SubAgents (`code-reviewer`, `feature-architect`, etc.) read this section per their "Project flags (read first)" sections.

Checkpoint: "Optional integrations decided. Proceed to infrastructure repo?"

## Phase 6: Infrastructure repo + SETUP.md

1. `gh repo create <project>-infrastructure --private --clone`. Clone.
2. Create directory structure (see `docs/infrastructure/terraform-modules.md`):

   ```
   <project>-infrastructure/
   ├── main.tf
   ├── variables.tf
   ├── outputs.tf
   ├── vercel.tf
   ├── oracle.tf
   ├── supabase.tf
   ├── .env.template
   ├── .gitignore
   └── .claude/settings.local.json
   ```

3. Write `main.tf` with provider blocks (vercel/vercel, oracle/oci, supabase/supabase) and `terraform { required_providers { ... } }`.
4. Write `variables.tf` declaring all token/credential variables with `sensitive = true`. Match `.env.template`.
5. Write empty stub `vercel.tf`, `oracle.tf`, `supabase.tf` with comments — they get populated by user/agent in `/webstack:infra`.
6. Write `.env.template` (placeholders only — see the `.env.template` schema in `shared/schemas.md`).
7. Write `.gitignore` covering `.env*`, `.terraform/`, `*.tfstate*`, `*.tfvars*`.
8. Write `.claude/settings.local.json` with these exact deny patterns (the security contract — embed verbatim, do not improvise):

   ```json
   {
     "permissions": {
       "deny": [
         "Read(./.env)",
         "Read(./.env.local)",
         "Read(**/.env)",
         "Read(**/.env.local)",
         "Read(**/.env.production)",
         "Read(**/.env.development)",
         "Read(**/.env.staging)",
         "Read(**/.env.test)",
         "Bash(cat .env*)",
         "Bash(printenv *_TOKEN)",
         "Bash(printenv *_KEY)",
         "Bash(printenv *_SECRET)",
         "Bash(printenv *_PASSWORD)",
         "Bash(env)",
         "Bash(env|grep -i token)",
         "Bash(env|grep -i key)",
         "Bash(env|grep -i secret)",
         "Bash(echo $*_TOKEN)"
       ]
     }
   }
   ```

   These 18 patterns + the plugin's `hooks/hooks.json` PreToolUse rules form a layered defense: deny rules block at Claude Code permission layer, hooks block at the helper-script layer. Both must agree — do not weaken either. (The `.env.production`/`.env.development`/`.env.staging`/`.env.test` Read denies cover Next.js's environment-specific files, which can hold secrets; `.env.template`/`.env.example` remain readable.)
9. Write `SETUP.md` (use `docs/infrastructure/setup-guide.md` as template; substitute `<project>` placeholders with the actual project name). **If `needs_auth=true`** in `manifest.yaml`, append a final section to SETUP.md titled "## Authentication next steps" that points to `docs/recipes/spring-security-auth.md` and notes that webstack does not provision an ID provider — the user implements auth themselves with Spring Security per the recipe when adding the first auth-bearing feature.
10. Initial commit + push.

Checkpoint: "Infrastructure repo created. SETUP.md written."

## Completion

1. Write `<project_root>/.webstack/manifest.yaml` with all collected metadata (see the `manifest.yaml` schema in `shared/schemas.md`).
2. Print final message:
   > Init complete. Your project is at `<project_root>/`. Three repos created. Design system at `.webstack/design-system/`. Next:
   > 1. Read `<infrastructure-repo>/SETUP.md` and sign up for Vercel, Oracle Cloud, Supabase.
   > 2. Issue tokens, fill `.env`, export.
   > 3. Run `/webstack:infra` to provision.

## Escalation Protocol

If a phase encounters a blocker (missing CLI, gh auth missing, Spring Initializr down, etc.): clearly report and ask user how to proceed. Do not skip phases.

## Style

- One phase at a time, with explicit checkpoints.
- Show 1-3 line summary of phase outcome before next checkpoint.
- Never auto-commit user-named decisions (e.g., archetype) without confirmation.
