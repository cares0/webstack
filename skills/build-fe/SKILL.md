---
name: build-fe
description: Internal sub-skill — implementation guide for frontend code from an OpenAPI 3.1 contract using Next.js App Router + ShadCN + Tailwind v4 + RHF/Zod + TanStack Query, organized via FSD-lite (5 layers under src/). Invoked by the frontend-implementer SubAgent only; not a user-facing slash command.
disable-model-invocation: true
---

# build-fe skill — frontend implementation guide

Operates inside a frontend repo's `.worktrees/<feature>/`. webstack uses **FSD-lite** layering: `src/{app, widgets, features, entities, shared}/` with one-way imports (app > widgets > features > entities > shared). See `docs/frontend/fsd-architecture.md` for the full ruleset.

## Inputs

- `worktree_path`, `contract_path`, `plan_path`, `architect_report`, `design_system_path`.

## Reference docs (lazy — read on demand)

These references are loaded **lazily** — do NOT preload before Phase 1. When a phase below names a doc, Read it at that point only.

- `shared/methodologies/tdd.md`
- `shared/methodologies/clean-code.md`
- `shared/methodologies/api-first.md`
- `docs/frontend/fsd-architecture.md`
- `docs/frontend/nextjs-app-router.md`
- `docs/frontend/server-components.md`
- `docs/frontend/shadcn-customization.md`
- `docs/frontend/tailwind-v4.md`
- `docs/frontend/rhf-zod.md`
- `docs/frontend/tanstack-query.md`

## Pre-conditions

- worktree on branch `feature/<feature_name>`. Clean.
- `pnpm install` baseline; `pnpm typecheck` and `pnpm lint` pass on main.
- `eslint-plugin-boundaries` configured for the 5 FSD layers (init scaffolds it).

## Phase 1: Codegen

1. Verify `openapi-ts.config.ts` references the contract path (or pattern that includes it) and `output: 'src/shared/api/generated'`.
2. Run `pnpm gen:api` (or `pnpm dlx @hey-api/openapi-ts`).
3. Inspect output under `src/shared/api/generated/`. Don't hand-edit.
4. Commit: `feat(api): regen client from <feature> contract`.

## Phase 2: Routes (Next.js App Router under src/app/)

For each route from architect/plan:

1. Create `src/app/<segment>/<route>/page.tsx` — Server Component default. Imports widgets/features and entity-scoped queries; assembles them. No business logic in `page.tsx`.
2. Add `loading.tsx` (Suspense fallback skeleton, optionally importing widgets' Skeleton variants).
3. Add `error.tsx` (`'use client'`; user-friendly error UI with retry).
4. Add `layout.tsx` if route group needs shared layout. Layouts compose with the root `src/app/layout.tsx`.
5. Add `metadata` (or `generateMetadata`) export for SEO.
6. Server Component fetches data via the generated SDK (`getXyz()` from `@/shared/api/generated/sdk`) or via an entity-scoped query helper (`@/entities/<entity>/api/queries`) — returns Promise of typed data.

Commit per route.

## Phase 3: Slices (widgets / features / entities)

Map architect's component breakdown to FSD slices:

- **widget** — composite UI used across multiple pages (header, sidebar, dashboard card grid). Lives at `src/widgets/<widget>/`. Server Component by default; interactive leaves only.
- **feature** — user-facing interaction (`create-project`, `delete-comment`, `filter-projects`, `login`). Lives at `src/features/<feature>/`. Typically `'use client'` at the form/UI leaf since features almost always involve interaction.
- **entity** — display + read-side queries for a domain object (`project`, `user`, `comment`). Lives at `src/entities/<entity>/`. Server Component for display; `'use client'` only when the entity component itself wraps an interactive primitive.

For each slice:

1. Create the directory: `src/<layer>/<slice>/{ui,api,model}/` (omit subdirs that aren't needed; UI-only entities skip `api/` and `model/`).
2. Place Server-Component-friendly files first; mark `'use client'` only on the leaves that need state/events/browser APIs.
3. Pass minimal serializable props across the server→client boundary.
4. Export the slice's public surface via `src/<layer>/<slice>/index.ts` (barrel). Consumers import via `@/<layer>/<slice>` only — never via a deeper path.

Commit per slice.

## Phase 4: Forms + data

For each form (lives in a feature slice):

1. Define Zod schema in `src/features/<feature>/model/schema.ts` — single source for client and server validation. If the request body Zod schema is emitted by `@hey-api/openapi-ts`, import it from `@/shared/api/generated` and `.extend(...)` for client-only fields.
2. Build the form at `src/features/<feature>/ui/<Form>.tsx` with RHF + ShadCN Form components: `<FormField>`, `<FormControl>`, `<FormMessage>` from `@/shared/ui/form`. zodResolver bridges.
3. Submit handler:
   - Mutation case: `useMutation` from `src/features/<feature>/api/mutations.ts` (a thin wrapper over the generated mutation hook in `@/shared/api/generated`).
   - Server Action case: `'use server'` action at `src/features/<feature>/api/actions.ts` that re-runs `schema.parse(formData)` then calls service.
4. On success: invalidate the corresponding entity query (`queryClient.invalidateQueries({ queryKey: ['getProjects'] })`). Toast or redirect per UX.
5. On error: surface field-level errors via RHF setError or general error toast.

For each data fetch:

1. Server Component path (in `src/app/<route>/page.tsx`): direct `await getProject(...)` from `@/shared/api/generated/sdk` — typed. Or call an entity helper if it exists.
2. Client interactive path (in a feature or widget Client Component): `useQuery` from `src/entities/<entity>/api/queries.ts` (wrapper over the generated `useGetXyzQuery()`).

Commit per form / per query group.

## Phase 5: Tests

Tests live next to the slice they exercise.

1. Component tests (Vitest + RTL):
   - `src/features/<feature>/ui/<Component>.test.tsx` or `src/entities/<entity>/ui/<Display>.test.tsx` — render, basic interaction, accessibility (`getByRole`, `findByLabelText`).
2. Form tests:
   - `src/features/<feature>/ui/<Form>.test.tsx` — successful submit with mock mutation: assert mutation called with parsed data.
   - Validation error: enter invalid input, assert `findByText(/required/i)` or similar.
3. Page integration test (optional in 1차 unless complex orchestration). Lives at `src/app/<route>/page.test.tsx`.
4. E2E with Playwright (only for critical user journeys flagged in plan):
   - `e2e/<feature>.spec.ts` — covers happy path end-to-end.

Run all: `pnpm typecheck && pnpm lint && pnpm test --run`. The lint step includes `eslint-plugin-boundaries` (FSD layer rule) — failures here mean a slice is importing across an FSD boundary it shouldn't. Fix the import direction; do not weaken the boundary config to make tests pass.

Commit per test group.

## Output

Write `<project_root>/.webstack/features/<feature>/fe-status.md` per frontend-implementer agent's spec.

## Escalation Protocol

`CLARIFICATION NEEDED: <question>` for layout/UX/copy ambiguity.

## Style

- Generated SDK is read-only.
- One Zod schema per form; reuse for server validation.
- Server-first by default.
- Commit per logical unit (route / component / form / test group).
