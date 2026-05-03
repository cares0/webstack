# Caching strategies (Next.js 16 App Router)

> Reference for `frontend-implementer` SubAgent and `build-fe` skill.
> Practical guide to Next.js 16's caching layers, when to opt in/out, and how to drive revalidation from mutations.

## What is Next.js caching

Next.js 16 App Router operates four distinct caching layers that work together to minimize redundant work and network round-trips.

**1. Request Memoization (per-render deduplication).** Powered by React's built-in `cache()`. Within a single server render pass, duplicate `fetch()` calls to the same URL are collapsed to one network request. The result is discarded after the render — it does not persist across requests.

**2. Data Cache (persistent, server-side).** A persistent cache keyed by URL + options that survives across requests. In Next.js 16's Cache Components model this is populated by `'use cache'` functions. It enables ISR-style behavior: serve stale content instantly, regenerate in the background, swap when ready.

**3. Full Route Cache (build-time HTML + RSC payload).** At build time Next.js pre-renders eligible route segments into HTML and RSC payload. On a cache hit the CDN or edge serves this with zero function invocation. With Cache Components enabled, Partial Prerendering (PPR) is the default: `'use cache'` segments land in the static shell; dynamic parts stream in via `<Suspense>`. Accessing runtime APIs (`cookies()`, `headers()`) or omitting `'use cache'` makes that segment dynamic.

**4. Router Cache (client-side, per-session).** The browser-side cache managed by the Next.js router. RSC payload for previously visited routes is replayed on back/forward navigation without a server round-trip. The server communicates the stale window via `x-nextjs-stale-time` (minimum 30 seconds). Calling `revalidateTag`, `revalidatePath`, or `updateTag` from a Server Action immediately purges all Router Cache entries.

```
User request
    │
    ▼  hit → instant response
┌──────────────────┐
│   Router Cache   │  client memory (per-session)
└──────┬───────────┘
       │ miss
       ▼  hit → CDN response
┌──────────────────────┐
│  Full Route Cache    │  build-time HTML + RSC payload (CDN/edge)
└──────┬───────────────┘
       │ miss / expired
       ▼  hit → Data Cache response
┌──────────────────┐
│   Data Cache     │  persistent server-side ('use cache' / fetch)
└──────┬───────────┘
       │ miss / expired
       ▼
┌──────────────────────┐
│ Request Memoization  │  per-render dedup (React.cache)
│ + origin fetch       │
└──────────────────────┘
```

## Why this approach

webstack runs on **Vercel Hobby** (free tier) with function execution limits and bandwidth caps. The Spring Boot backend on **Oracle Always Free** (2 vCPU, 1 GB RAM) is not globally distributed — cold backend latency can exceed 300 ms.

Correct caching delivers:

- **Cost:** Static shell served from CDN — zero function invocations for pure-read pages until the revalidation window expires.
- **UX:** Instant navigation from Router Cache for previously visited routes; near-instant TTFB from Full Route Cache for common pages.
- **Correctness:** Mutations trigger targeted revalidation so users see their own writes immediately without invalidating unrelated caches.

## webstack convention

### Enable Cache Components

webstack frontends opt in to Cache Components in `next.config.ts`:

```ts
// next.config.ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  cacheComponents: true,
}

export default nextConfig
```

This activates `'use cache'`, `cacheLife`, `cacheTag`, and PPR as the default rendering model.

### `'use cache'` directive + `cacheLife`

Apply `'use cache'` at the data-function or component level. Always call `cacheLife` explicitly inside every `'use cache'` scope — relying on the implicit `default` profile (15 min revalidate, never expires) makes behavior hard to audit:

```ts
// src/entities/project/api/queries.ts
import { cacheLife, cacheTag } from 'next/cache'
import { ProjectsService } from '@/shared/api/generated'

export async function listProjects(workspaceId: string) {
  'use cache'
  cacheLife('minutes')   // regenerate every ~1 min, serve stale for 5 min
  cacheTag('projects')
  cacheTag(`workspace-${workspaceId}`)
  return ProjectsService.listProjects({ query: { workspaceId } })
}

export async function getProjectById(id: string) {
  'use cache'
  cacheLife('hours')     // detail pages change less frequently
  cacheTag(`project-${id}`)
  cacheTag('projects')
  return ProjectsService.getProjectById({ path: { id } })
}
```

Built-in `cacheLife` profiles:

| Profile   | `stale` | `revalidate` | `expire` | Use case |
|-----------|---------|-------------|---------|---------|
| `seconds` | 30 s    | 1 s         | 1 min   | Live/real-time data |
| `minutes` | 5 min   | 1 min       | 1 hour  | Frequently updated lists |
| `hours`   | 5 min   | 1 hour      | 1 day   | Entity detail pages |
| `days`    | 5 min   | 1 day       | 1 week  | Blog posts, docs |
| `weeks`   | 5 min   | 1 week      | 30 days | Newsletters, podcasts |
| `max`     | 5 min   | 30 days     | 1 year  | Legal, archived content |
| `default` | 5 min   | 15 min      | never   | Fallback (avoid implicit use) |

### Generated SDK calls

The generated SDK in `src/shared/api/generated/` wraps raw `fetch`. Apply caching in a wrapper function in `src/entities/<entity>/api/queries.ts`, not inside the generated code:

```ts
// src/entities/project/api/queries.ts
import { cacheLife, cacheTag } from 'next/cache'
import { ProjectsService } from '@/shared/api/generated'

export async function listProjects() {
  'use cache'
  cacheLife('minutes')
  cacheTag('projects')
  return ProjectsService.listProjects()
}
```

Server Components in `src/app/<route>/page.tsx` and `src/widgets/<widget>/` call these wrappers directly with `await`.

### Personalized / auth-bearing requests

Data that requires a session cookie or `Authorization` header **must not** use `'use cache'` at the Data Cache level — it would share one user's data with another. Render it at request time and wrap with `<Suspense>`:

```ts
// src/entities/user/api/queries.ts
import { cookies } from 'next/headers'
import { UserService } from '@/shared/api/generated'

// No 'use cache' — reads session, must be dynamic
export async function getCurrentUser() {
  const token = (await cookies()).get('session')?.value
  return UserService.getMe({ headers: { Authorization: `Bearer ${token}` } })
}
```

To cache per-user data, extract the user ID outside the cache boundary and pass it as an argument:

```ts
export async function getUserProfile(userId: string) {
  'use cache'
  cacheLife('hours')
  cacheTag(`user-${userId}`)
  return UserService.getUserById({ path: { id: userId } })
}
```

## Revalidation patterns

### Tag-based on-demand revalidation (preferred)

Call `revalidateTag` in Server Actions after mutations. Tag granularity matters: too coarse evicts unrelated entries; too fine misses related views.

```ts
// src/features/project/api/mutations.ts
'use server'

import { revalidateTag } from 'next/cache'
import { ProjectsService } from '@/shared/api/generated'
import { createProjectSchema, updateProjectSchema } from '../model/schema'

export async function createProject(formData: FormData) {
  const parsed = createProjectSchema.parse(Object.fromEntries(formData))
  await ProjectsService.createProject({ body: parsed })
  revalidateTag('projects')
}

export async function updateProject(id: string, formData: FormData) {
  const parsed = updateProjectSchema.parse(Object.fromEntries(formData))
  await ProjectsService.updateProject({ path: { id }, body: parsed })
  revalidateTag(`project-${id}`)  // specific record
  revalidateTag('projects')       // and the list containing it
}

export async function deleteProject(id: string) {
  await ProjectsService.deleteProject({ path: { id } })
  revalidateTag(`project-${id}`)
  revalidateTag('projects')
}
```

### `revalidatePath` for route-wide invalidation

Use `revalidatePath` when a mutation affects multiple unrelated data sources on the same URL. This is a blunt instrument — prefer `revalidateTag` for targeted invalidation:

```ts
import { revalidatePath } from 'next/cache'

export async function publishReport(id: string) {
  await ReportService.publish({ path: { id } })
  revalidatePath(`/reports/${id}`)
}
```

### Decision guide

**`revalidateTag` vs `revalidatePath`:**

- One entity type mutated → `revalidateTag('entity-type')` + `revalidateTag('entity-id')`.
- Multiple entity types on one URL → `revalidatePath('/that/route')`.

**ISR (`'use cache'` + `cacheLife`) vs SSR (no cache):**

- User-specific / auth-bearing → no `'use cache'`; dynamic `<Suspense>`.
- Shared data, change cadence matches a `cacheLife` profile → use that profile.
- Real-time (sub-minute) → `cacheLife('seconds')` or skip caching.

## Coordinating with TanStack Query

webstack uses two separate cache layers that must stay in sync:

- **Next.js Data Cache** — server-side, populated by `'use cache'`, invalidated by `revalidateTag`/`revalidatePath`.
- **TanStack Query cache** — client-side, per-session, invalidated by `queryClient.invalidateQueries`.

### Prefetch on server, mutate on client

For a route that renders a list on first load and supports in-page mutations, use `prefetchQuery` + `HydrationBoundary` in the Server Component (see `docs/frontend/tanstack-query.md` § "Pre-fetch on server" for the full pattern). The `listProjects` query function should be the same `'use cache'` wrapper used by the Server Component — TanStack Query hits the Next.js Data Cache on the server and the TQ in-memory cache on the client:

```tsx
// src/app/projects/page.tsx (Server Component)
import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query'
import { listProjects } from '@/entities/project/api/queries'  // 'use cache' wrapper
import { ProjectsWidget } from '@/widgets/projects'

export default async function ProjectsPage() {
  const queryClient = new QueryClient()
  await queryClient.prefetchQuery({ queryKey: ['projects'], queryFn: listProjects })
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ProjectsWidget />
    </HydrationBoundary>
  )
}
```

### Dual-cache invalidation after mutations

Server Actions call `revalidateTag` (Next.js cache); the TanStack Query `onSuccess` calls `invalidateQueries` (client cache):

```ts
// src/features/project/ui/CreateProjectForm.tsx  (excerpt)
'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createProject } from '../api/mutations'   // Server Action

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (formData: FormData) => createProject(formData),
    onSuccess: () => {
      // Server Action already called revalidateTag('projects') on the server.
      // Now purge the client-side TanStack Query cache too.
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
```

This dual-invalidation ensures:

1. The **Next.js Data Cache** is purged — the next SSR request fetches fresh data.
2. The **TanStack Query cache** is marked stale — the in-page widget refetches immediately.

## Anti-patterns

**Setting `cache: 'no-store'` (or skipping `'use cache'`) everywhere.** Treating every fetch as dynamic eliminates PPR and Full Route Cache, draining the Vercel Hobby function quota on reads that could be cache hits. Reserve dynamic rendering for genuinely user-specific or real-time data.

**Forgetting `cacheTag` on data that other features mutate.** A `'use cache'` function without `cacheTag('projects')` is unreachable by `revalidateTag('projects')`. The stale list stays in the Data Cache until `cacheLife` expires naturally. Always add a tag at the entity-type level (`'projects'`) and optionally at the entity-id level (`'project-<id>'`).

**Mixing `next: { revalidate: N }` (fetch option) with `'use cache'` / `cacheLife`.** The `next.revalidate` fetch option is part of the pre-16 caching model (without `cacheComponents: true`). With Cache Components enabled, use `'use cache'` + `cacheLife` exclusively — do not apply both on the same function. The same applies to route segment config (`export const revalidate = 60`).

**Mutating from a Client Component without server revalidation.** A TanStack Query `mutationFn` that calls a raw `fetch()` (not a Server Action) clears the TQ client cache via `invalidateQueries` but leaves the Next.js Data Cache and Full Route Cache stale. A new browser tab will still see old data. Always use a Server Action as the `mutationFn` so `revalidateTag` runs server-side.

**Omitting `cacheLife` inside `'use cache'`.** Nested `'use cache'` scopes with short lifetimes propagate their TTL upward to any outer scope that has no explicit `cacheLife`. The implicit `default` profile (15 min revalidate, never expires) is hard to audit. Always call `cacheLife` explicitly in every `'use cache'` scope.

## Sources

- **Next.js docs — Caching (Cache Components):** https://nextjs.org/docs/app/getting-started/caching — _authoritative; v16.2.4, 2026-04-10_
- **Next.js docs — `use cache` directive:** https://nextjs.org/docs/app/api-reference/directives/use-cache — _authoritative; v16.2.4, 2026-04-10_
- **Next.js docs — `cacheLife` API:** https://nextjs.org/docs/app/api-reference/functions/cacheLife — _authoritative; v16.2.4, 2026-04-10_
- **Next.js docs — Caching without Cache Components (previous model / `fetch` + `unstable_cache`):** https://nextjs.org/docs/app/guides/caching-without-cache-components — _authoritative; v16.2.4_
- **Next.js llms.txt:** https://nextjs.org/docs/llms.txt — _authoritative; version index confirming v16.2.4_

---

_Last verified: 2026-05-04 (Next.js 16.2.4 / React 19)._
