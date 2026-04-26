# webstack — Claude Code project guide

> Add to your project CLAUDE.md (via `import` or copy) for AI awareness when working on a webstack-managed project.

## Project type

This is a **webstack** project. Three sibling git repos (`*-frontend`, `*-backend`, `*-infrastructure`) coordinate via `.webstack/` metadata in the parent directory.

## How to interact

Use these slash commands:

- `/webstack:init` — initial scaffolding (run once, in parent dir).
- `/webstack:feature <name>` — add a feature (creates parallel worktrees in FE+BE).
- `/webstack:infra` — apply/modify terraform IaC.
- `/webstack:deploy` — deploy FE (Vercel) and/or BE (Oracle).

Don't manually edit:

- `.webstack/design-system/theme.css` — regenerate via design-system-architect (re-run init P3).
- `*/src/api/generated/` (frontend) — regenerate via `pnpm gen:api`.
- `*/build/generated-src/` (backend, jOOQ) — regenerate via Gradle task.

Manually edit (these are sources of truth):

- `.webstack/identity.md`, `.webstack/personas/*.md`, `.webstack/contracts/<feature>.yaml`, `.webstack/features/<feature>/plan.md`.
- All hand-written code under `<frontend>/src/` (except `generated/`) and `<backend>/src/main/kotlin`.

## Architecture conventions

### Backend (DDD/Hexagonal)

- Domain layer is pure Kotlin — no Spring, JPA, Jackson imports.
- Aggregate root is the only public entry to the aggregate; cross-aggregate refs by ID only.
- Application service is `@Transactional`, controller and repository are not.
- Repository interface in `domain/`, implementation in `infrastructure/persistence/`.
- DTOs at HTTP boundary; commands at application boundary; domain entities never leak to HTTP.

### Frontend (App Router)

- Server Component default. Add `'use client'` only when state/effects/event handlers/browser APIs needed.
- One Zod schema per form, used both client-side (RHF) and server-side (`schema.parse(formData)`).
- Generated SDK in `src/api/generated/` is read-only.
- Tailwind classes via design tokens (CSS variables); no inline styles for theme values.

## Security

- `.env*` files are protected — AI cannot Read them or `cat` them.
- Tokens go in your shell environment via `set -a && source .env && set +a` (manual each session).
- All terraform-applied changes require explicit `apply` confirmation (high-risk needs `I understand` second confirmation).
- Never enable `--dangerously-skip-permissions` in a webstack project.

## Worktrees

- Feature work happens in `<repo>/.worktrees/<feature-name>/` (both FE and BE).
- Same `feature/<name>` branch in both.
- After PR merge: `git worktree remove .worktrees/<name>` per repo (manual, with confirmation).

## Methodology references

- `shared/methodologies/ddd.md`
- `shared/methodologies/hexagonal.md`
- `shared/methodologies/api-first.md`
- `shared/methodologies/tdd.md`
- `shared/methodologies/clean-code.md`
- `docs/frontend/`, `docs/backend/`, `docs/infrastructure/`

When in doubt, read these.

## When this guide and your project's specific instructions conflict

User project CLAUDE.md > webstack CLAUDE.md > webstack defaults.
