---
name: build-fe
description: Implementation guide for frontend code from an OpenAPI 3.1 contract using Next.js App Router + ShadCN + Tailwind v4 + RHF/Zod + TanStack Query. Invoked by the frontend-implementer SubAgent. Can also be followed by main agent for fallback / debug scenarios.
---

# build-fe skill — frontend implementation guide

Operates inside a frontend repo's `.worktrees/<feature>/`.

## Inputs

- `worktree_path`, `contract_path`, `plan_path`, `architect_report`, `design_system_path`.

## Required reads

- `shared/methodologies/tdd.md`
- `shared/methodologies/clean-code.md`
- `shared/methodologies/api-first.md`
- `docs/frontend/nextjs-app-router.md`
- `docs/frontend/server-components.md`
- `docs/frontend/shadcn-customization.md`
- `docs/frontend/tailwind-v4.md`
- `docs/frontend/rhf-zod.md`
- `docs/frontend/tanstack-query.md`

## Pre-conditions

- worktree on branch `feature/<feature_name>`. Clean.
- `pnpm install` baseline; `pnpm typecheck` and `pnpm lint` pass on main.

## Phase 1: Codegen

1. Verify `openapi-ts.config.ts` references the contract path (or pattern that includes it).
2. Run `pnpm gen:api` (or `pnpm dlx @hey-api/openapi-ts`).
3. Inspect output under `src/api/generated/`. Don't hand-edit.
4. Commit: `feat(api): regen client from <feature> contract`.

## Phase 2: Routes

For each route from architect/plan:

1. Create `src/app/<segment>/<route>/page.tsx` — Server Component default. Imports + renders.
2. Add `loading.tsx` (Suspense fallback skeleton).
3. Add `error.tsx` (`'use client'`; user-friendly error UI with retry).
4. Add `layout.tsx` if route group needs shared layout.
5. Add `metadata` export for SEO.
6. Server Component fetches data via generated SDK (`getXyz()` from `@/api/generated/sdk`) — returns Promise of typed data.

Commit per route.

## Phase 3: Server / Client split

For interactive components:

1. Identify which leaf components need state/event/browser-only APIs → Client.
2. Create `src/components/<feature>/<Component>.tsx`. Add `'use client'` only if needed.
3. Compose: Server pages render Server components, which embed `<ClientComponent>` islands.
4. Pass minimal props; serializable only.

For non-interactive: stays Server.

Commit per component.

## Phase 4: Forms + data

For each form:

1. Define Zod schema in `src/components/<feature>/schema.ts` — single source for client and server validation.
2. Build form with RHF + ShadCN Form components: `<FormField>`, `<FormControl>`, `<FormMessage>`. zodResolver bridges.
3. Submit handler:
   - Mutation case: TanStack Query `useMutation` calling generated SDK.
   - Server Action case: `'use server'` action that re-runs `schema.parse(formData)` then calls service.
4. On success: invalidate relevant queries (`queryClient.invalidateQueries({ queryKey: [...] })`). Toast or redirect per UX.
5. On error: surface field-level errors via RHF setError or general error toast.

For each data fetch:

1. Server Component path: direct `await sdk.getXyz()` — typed.
2. Client interactive path: `useQuery({ queryKey, queryFn })`. Use generated `useGetXyzQuery()` if @hey-api TanStack plugin enabled.

Commit per form / per query group.

## Phase 5: Tests

1. Component tests (Vitest + RTL):
   - `<feature>/<Component>.test.tsx` — render, basic interaction (click, input), accessibility (`getByRole`, `findByLabelText`).
2. Form tests:
   - Successful submit with mock mutation: assert mutation called with parsed data.
   - Validation error: enter invalid input, assert `findByText(/required/i)` or similar.
3. Page integration test (optional in 1차 unless complex orchestration).
4. E2E with Playwright (only for critical user journeys flagged in plan):
   - `e2e/<feature>.spec.ts` — covers happy path end-to-end.

Run all: `pnpm typecheck && pnpm lint && pnpm test --run`. Must pass.

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
