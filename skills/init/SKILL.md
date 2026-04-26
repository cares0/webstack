---
name: init
description: Use when starting a new fullstack web service from scratch (empty parent directory, no .webstack/ yet). Conducts identity, persona, and design system interviews; scaffolds three git repositories (frontend, backend, infrastructure); generates the design system tokens, ShadCN theme, and component variants; outputs a SETUP.md guide for the user to sign up for free-tier infrastructure (Vercel, Oracle Cloud, Supabase). Run once per project.
---

# init skill — webstack project setup

You are running `/webstack:init` for a new webstack project. Follow this phase flow strictly. The user expects deliberate, checkpoint-gated progress — never skip phases or auto-merge decisions.

## Required reads (read once at session start)

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

## Pre-flight (P0)

1. Verify cwd is the intended **parent directory** (will hold `.webstack/` + 3 sibling repos). Ask user to confirm with `pwd`.
2. Verify directory is empty (`ls` shows nothing or only intended seed files like a README).
3. Verify CLI tooling: `git --version`, `gh --version` (required for repo create), `node --version` (≥20), `pnpm --version`, `terraform --version` (warning if missing — only needed in infra phase). Report missing.
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

Write `<project_root>/.webstack/identity.md` per the schema in spec §8.2.

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

1. `gh repo create <project>-frontend --private --clone` (or `--public` per user preference). If `gh` not configured: instruct user to run `gh auth login`.
2. `git clone` into sibling dir.
3. `cd <project>-frontend && pnpm dlx create-next-app@latest . --ts --tailwind --app --src-dir --no-eslint --import-alias "@/*"` (Next.js 15+, App Router default).
4. Replace generated `app/globals.css` with content adapted from `<project_root>/.webstack/design-system/theme.css`. Ensure `@import "tailwindcss"` and `@theme {}` block.
5. `pnpm dlx shadcn@latest init` — choose New York or default per design system style. Use generated `components.json` baseColor matching theme.
6. Install ShadCN initial components: button, card, input, form, label, badge, dialog, sheet, dropdown-menu, tooltip. (`shadcn add <name>` for each.)
7. Apply component-variants.md cva extensions to `components/ui/button.tsx` etc.
8. Install + configure: `react-hook-form`, `zod`, `@hookform/resolvers/zod`, `@tanstack/react-query`, `@tanstack/react-query-devtools`, `@hey-api/openapi-ts`, `@hey-api/client-fetch`.
9. Add `openapi-ts.config.ts` pointing to `../.webstack/contracts/` (glob — runtime: each feature has its own).
10. Add `package.json` scripts: `typecheck`, `lint`, `test` (Vitest), `format`, `gen:api` (openapi-ts).
11. Initial commit: "feat: init <project>-frontend (Next.js + ShadCN + Tailwind v4)".
12. `git push -u origin main`.

Checkpoint: "Frontend repo created and pushed. Proceed to backend?"

## Phase 5: Backend repo scaffolding

1. `gh repo create <project>-backend --private --clone`.
2. `git clone` into sibling dir.
3. Use Spring Initializr API or curl to generate base:

   ```bash
   curl https://start.spring.io/starter.zip \
     -d type=gradle-project-kotlin \
     -d language=kotlin \
     -d bootVersion=3.3.0 \
     -d baseDir=. \
     -d groupId=<org-or-com.example> \
     -d artifactId=<project> \
     -d packageName=com.<org>.<project> \
     -d javaVersion=21 \
     -d dependencies=web,validation,security,data-jpa,flyway,actuator,configuration-processor \
     -o starter.zip && unzip starter.zip && rm starter.zip
   ```

4. Edit `build.gradle.kts` to add:
   - KoTest: `testImplementation("io.kotest:kotest-runner-junit5:<v>")`, `kotest-assertions-core`, `kotest-extensions-spring`.
   - MockK: `testImplementation("io.mockk:mockk:<v>")`, `com.ninja-squad:springmockk:<v>`.
   - Spring Modulith: `org.springframework.modulith:spring-modulith-starter-core` + `spring-modulith-starter-jpa` + `spring-modulith-events-jpa`.
   - springdoc-openapi-starter-webmvc-ui.
   - Postgres driver (`org.postgresql:postgresql`) and HikariCP (default).
5. Create Hexagonal layered package structure (placeholder `package-info.java` for each module):

   ```
   src/main/kotlin/com/<org>/<project>/
   ├── domain/
   ├── application/
   ├── infrastructure/
   │   ├── http/
   │   ├── persistence/
   │   └── config/
   └── <project>Application.kt
   ```

6. Create `src/main/resources/application.yml` with spring profiles (default, dev) + flyway + JPA + springdoc paths.
7. Create `src/main/resources/db/migration/V1__init.sql` (empty migration placeholder, comment).
8. Create initial KoTest spec to ensure the test runner works: `<Project>ApplicationTests.kt` (one passing test).
9. Initial commit + push.

Checkpoint: "Backend repo created. Proceed to infrastructure?"

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
6. Write `.env.template` (placeholders only — see spec §10.2).
7. Write `.gitignore` covering `.env*`, `.terraform/`, `*.tfstate*`, `*.tfvars*`.
8. Write `.claude/settings.local.json` with deny rules (see spec §10.2).
9. Write `SETUP.md` (use `docs/infrastructure/setup-guide.md` as template; substitute `<project>` placeholders with the actual project name).
10. Initial commit + push.

Checkpoint: "Infrastructure repo created. SETUP.md written."

## Completion

1. Write `<project_root>/.webstack/manifest.yaml` with all collected metadata (see spec §8.1).
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
