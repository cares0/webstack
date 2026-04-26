# TanStack Query

> Reference for build-fe SubAgent. Covers TanStack Query v5 (formerly React Query) patterns: queries, mutations, cache, optimistic updates, suspense, RSC handoff, and integration with `@hey-api/openapi-ts`-generated hooks.

## Why TanStack Query for client state

Server state and client state are different problems. Client state (a modal open, a form draft) lives only in this browser tab and the component owns it. Server state (the current user's projects, a paginated list) is owned by a remote system, may change without this client's input, and must be cached, deduplicated, and revalidated.

TanStack Query treats every fetch as a cache entry keyed by a stable identifier. Multiple components requesting the same key share one network request. Mutations invalidate cache entries by tag, triggering automatic refetches. Stale-while-revalidate semantics deliver the cached value instantly and refresh in the background. The library handles retries, focus refetch, request cancellation, dependent queries, and pagination, all without ad-hoc `useEffect` plumbing.

In webstack the alternative for the entire app is Server Components plus props (see `docs/frontend/server-components.md`); TanStack Query is reserved for surfaces that mutate or update without route navigation.

## Setup

Install:

```bash
pnpm add @tanstack/react-query
pnpm add -D @tanstack/react-query-devtools
```

Wrap the app once at the highest Client Component (typically a `Providers` component imported by the root layout):

```tsx
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 60_000, gcTime: 5 * 60_000, retry: 1 },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

`useState` ensures a single `QueryClient` per browser tab even with React 18 strict mode double-mount. For RSC handoff, the same `QueryClient` is reused across hydration via `<HydrationBoundary>` (see "Pre-fetch on server" below).

## QueryKey design

A query key is an array. The first element identifies the resource type; subsequent elements scope it by parameters.

```ts
['users']                                  // list
['users', { filter: 'active', page: 2 }]   // filtered list
['users', userId]                          // single resource
['users', userId, 'projects']              // nested list
```

Two principles:

1. **Hierarchical** — invalidating `['users']` invalidates everything beneath it. Invalidating `['users', userId]` invalidates only that user.
2. **Stable** — object keys are deep-compared. Always include parameters in the same order, with stable serialization.

webstack convention: query keys mirror the OpenAPI `operationId`. `getProjects` becomes `['getProjects', params]`; `getProject` with `{id}` becomes `['getProject', { id }]`. The hey-api TanStack Query plugin (below) generates these for you.

## useQuery basics

```tsx
import { useQuery } from '@tanstack/react-query';

function ProjectList() {
  const { data, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ['projects', { archived: false }],
    queryFn: ({ signal }) => fetchProjects({ archived: false }, { signal }),
    staleTime: 30_000,
    gcTime: 10 * 60_000,
    retry: 1,
    refetchOnWindowFocus: true,
    enabled: true,
  });

  if (isPending) return <Skeleton />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  return <ul>{data.map((p) => <li key={p.id}>{p.name}</li>)}</ul>;
}
```

- **`staleTime`** — how long data is considered fresh. While fresh, no refetch on remount/focus. Default 0 (always stale).
- **`gcTime`** (formerly `cacheTime`) — how long inactive cache entries are kept before garbage collection. Default 5 min.
- **`retry`** — number of retries on failure. Default 3 — too aggressive for forms; webstack default is 1.
- **`refetchOnWindowFocus`** — auto-refetch when the tab regains focus. Useful for dashboards; disable for static content.
- **`enabled: false`** — skip the query until prerequisites resolve (e.g., wait for an authenticated user).
- **`signal`** — `AbortSignal` for cancellation; pass to fetch.

## useMutation

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';

function CreateProject() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (input: CreateProjectInput) => createProject(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (error) => {
      toast.error(error.message);
    },
    onSettled: () => {
      // runs after success or error
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        mutation.mutate({ name: data.get('name') as string });
      }}
    >
      <input name="name" />
      <button disabled={mutation.isPending}>
        {mutation.isPending ? 'Creating…' : 'Create'}
      </button>
    </form>
  );
}
```

`mutate` returns `void`; `mutateAsync` returns a Promise (use when callers need to await). `onMutate` runs before the request and returns a context object that flows to `onError` for rollback (see "Optimistic updates"). `onSuccess` and `onError` run after; `onSettled` runs in both cases.

## Optimistic updates

The pattern is snapshot → optimistic write → mutate → rollback on error → invalidate on settle.

```ts
const toggleStar = useMutation({
  mutationFn: (id: string) => api.starProject(id),
  onMutate: async (id) => {
    await queryClient.cancelQueries({ queryKey: ['projects'] });
    const previous = queryClient.getQueryData<Project[]>(['projects']);
    queryClient.setQueryData<Project[]>(['projects'], (old) =>
      old?.map((p) => (p.id === id ? { ...p, starred: !p.starred } : p)),
    );
    return { previous };
  },
  onError: (_err, _id, ctx) => {
    if (ctx?.previous) queryClient.setQueryData(['projects'], ctx.previous);
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] });
  },
});
```

`cancelQueries` prevents an in-flight refetch from overwriting the optimistic state. The `previous` snapshot in the context lets `onError` restore the cache. `onSettled` triggers a refetch to reconcile with server truth.

Use optimistic updates when:

- The mutation is high-frequency (likes, stars, sortable lists).
- The server response is predictable enough to model client-side.
- A 100-500 ms latency would make the UI feel unresponsive.

Skip optimistic updates for mutations whose server-side validation could meaningfully change the result.

## Cache invalidation

```ts
queryClient.invalidateQueries({ queryKey: ['projects'] });          // mark all 'projects' queries stale
queryClient.invalidateQueries({ queryKey: ['projects', projectId] }); // a specific project
queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'projects' }); // arbitrary predicate
queryClient.removeQueries({ queryKey: ['projects', projectId] });   // hard remove (logout, delete)
queryClient.setQueryData(['projects', projectId], updatedProject);  // direct cache write
```

Tag-based invalidation: a list query keyed `['projects']` is invalidated whenever any project mutates. A detail query keyed `['projects', projectId]` is invalidated on per-record edits. Cross-resource invalidation (creating a project should refresh the user's quota) requires explicit `invalidateQueries` calls in the mutation's `onSuccess`.

## Suspense integration

`useSuspenseQuery` throws a Promise while loading and an error while erroring, so a parent `<Suspense>` and `error.tsx` boundary handle the states.

```tsx
'use client';

import { useSuspenseQuery } from '@tanstack/react-query';
import { Suspense } from 'react';

function Projects() {
  const { data } = useSuspenseQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });
  return <ProjectList projects={data} />;
}

export function ProjectsSection() {
  return (
    <Suspense fallback={<ProjectsSkeleton />}>
      <Projects />
    </Suspense>
  );
}
```

Pairs naturally with Next.js App Router `loading.tsx` (segment-level fallback) and `error.tsx` (segment-level error UI). `useSuspenseQuery` requires that the cache be populated before render — typically via the prefetch handoff below.

## Pre-fetch on server

For the common case of "render this list immediately on first load," prefetch in a Server Component and stream the cache to the client:

```tsx
// app/projects/page.tsx (Server Component)
import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query';
import { Projects } from './Projects';

export default async function Page() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: ['projects'],
    queryFn: () => fetch(`${process.env.API_URL}/projects`).then((r) => r.json()),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <Projects />
    </HydrationBoundary>
  );
}
```

The Server Component runs `prefetchQuery` against a fresh `QueryClient`, dehydrates its state into the RSC payload, and the client's `<HydrationBoundary>` rehydrates entries into the global `QueryClient` before children mount. `useQuery`/`useSuspenseQuery` hits the cache immediately with no network round-trip.

This works because the server-rendered HTML and the client-side hydrated tree share the same query keys.

## Generated client (@hey-api/openapi-ts) integration

`@hey-api/openapi-ts` reads an OpenAPI spec and generates a typed TypeScript SDK. With its TanStack Query plugin enabled, it also emits typed `useQuery` / `useMutation` hooks per operation:

```ts
// generated by hey-api
export const getProjectsQueryOptions = (params: GetProjectsParams) => ({
  queryKey: ['getProjects', params],
  queryFn: ({ signal }) => getProjects(params, { signal }),
});

export function useGetProjectsQuery(params: GetProjectsParams) {
  return useQuery(getProjectsQueryOptions(params));
}

export function usePostProjectsMutation() {
  return useMutation({
    mutationFn: (body: CreateProjectInput) => postProjects(body),
  });
}
```

webstack convention: prefer the generated hooks. Hand-write a `useQuery` only when the generated form is insufficient — typically because the call needs to combine two operations or set unusual cache options. Hand-written hooks reuse the generated `*QueryOptions` factory:

```ts
const result = useQuery({
  ...getProjectsQueryOptions({ archived: false }),
  refetchInterval: 10_000, // override for live dashboard
});
```

Configure the plugin in `openapi-ts.config.ts`:

```ts
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8080/v3/api-docs',
  output: 'src/api/generated',
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    {
      name: '@tanstack/react-query',
      queryOptions: true,
      mutationOptions: true,
      infiniteQueryOptions: true,
    },
  ],
});
```

Run `pnpm openapi-ts` after backend OpenAPI changes; commit the generated output (or gitignore + run on CI — webstack default is to commit so PR diffs surface the API surface change).

## webstack convention

- **Query keys mirror operationId.** `useGetProjectsQuery(params)` produces `['getProjects', params]`. Manual queries follow the same convention so invalidation stays consistent.
- **Mutations call the generated SDK.** Form `onSubmit` invokes `mutate(values)` from a generated `usePost…Mutation`; on success, `queryClient.invalidateQueries({ queryKey: ['getProjects'] })` (matching the corresponding GET).
- **One QueryClient per app.** Defined in `Providers.tsx` at the root layout. Tests instantiate a fresh client per test.
- **Server Component pre-fetch for above-the-fold lists.** Use `prefetchQuery` + `HydrationBoundary` so the first paint has data; subsequent updates flow through the client cache.
- **No `useEffect` + `fetch`.** Every server data dependency goes through TanStack Query (or a Server Component), never a hand-rolled effect.
- **Devtools off in production.** `<ReactQueryDevtools initialIsOpen={false} />` ships dev-only via `process.env.NODE_ENV === 'development'` guard if needed.

## Sources

- TanStack Query: https://tanstack.com/query/latest
- Suspense + RSC handoff: https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr
- @hey-api TanStack Query plugin: https://heyapi.dev/openapi-ts/plugins/tanstack-react-query
- @hey-api/openapi-ts: https://heyapi.dev/openapi-ts
