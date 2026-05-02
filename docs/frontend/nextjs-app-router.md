# Next.js App Router

> Reference for `build-fe` SubAgent and frontend-implementer. Covers the file-based routing model introduced in Next.js 13, stabilized through Next.js 15, and refined in Next.js 16+ (current stable as of 2026-04-26).

## Why App Router (vs Pages Router)

The App Router is built on top of React Server Components (RSC). Files under `app/` default to running on the server, sending zero JavaScript to the client unless the component opts in with `'use client'`. This shifts the default cost model: data-fetching code, secrets, ORM access, and large dependencies stay on the server, while only interactive leaves are hydrated.

Layouts in the App Router compose by nesting. Each `layout.tsx` segment wraps everything below it without re-rendering when navigating between sibling routes. The Pages Router did not preserve layout state across navigation; the App Router does. The same shift gives streaming via `loading.tsx` and granular error isolation via `error.tsx` per segment, which Pages Router could not express without bespoke `_app.tsx` plumbing.

For new projects in 2026, the Pages Router is in maintenance mode (long-term security fixes only). webstack assumes the App Router for all generated frontend repos and pins the Next.js dependency to the latest 16.x stable at scaffold time.

## Folder structure

The App Router maps the filesystem to URL segments. A file's name encodes intent:

```text
app/
├── layout.tsx              # root layout (required)
├── page.tsx                # /
├── (marketing)/            # route group: not in URL
│   ├── about/page.tsx      # /about
│   └── pricing/page.tsx    # /pricing
├── (dashboard)/            # parallel route group with own layout
│   ├── layout.tsx
│   └── projects/
│       ├── page.tsx                    # /projects
│       ├── [projectId]/                # /projects/abc
│       │   ├── page.tsx
│       │   ├── @modal/                 # parallel slot
│       │   │   └── default.tsx
│       │   └── (.)photo/[photoId]/     # intercepting route
│       │       └── page.tsx
│       └── [[...filters]]/page.tsx     # /projects, /projects/a, /projects/a/b
├── _internal/              # private folder: never routed
│   └── helpers.ts
└── api/
    └── users/route.ts      # GET/POST /api/users
```

- `(group)/` parentheses = route group, organizing files without affecting URL.
- `[dynamic]` = single dynamic segment: `params.dynamic`.
- `[...catchall]` = catch-all (one or more segments): `params.catchall: string[]`.
- `[[...optional]]` = optional catch-all (matches the parent path too).
- `_private` = leading underscore, never registered as a route.
- `@parallel` = parallel slot, rendered alongside `children` of the surrounding layout.
- `(.)`, `(..)`, `(...)` = intercepting routes (current segment, parent, root).

## Files in a route

| File | Purpose |
| --- | --- |
| `page.tsx` | Renders the route's UI. Required for a path to be addressable. |
| `layout.tsx` | Wraps `children` of all nested segments. Does not unmount on navigation. |
| `loading.tsx` | Suspense fallback while the segment streams. |
| `error.tsx` | Error boundary for the segment. Must be a Client Component. |
| `not-found.tsx` | Rendered when `notFound()` is called or no matching route. |
| `template.tsx` | Like `layout.tsx` but re-mounts on every navigation (rare; for analytics). |
| `route.ts` | Route Handler. Exports `GET`/`POST`/etc. Runs on the server only. |
| `default.tsx` | Default content for a parallel slot when no match. |

## Layouts & nesting

The root `app/layout.tsx` is required and must render `<html>` and `<body>`. Nested `layout.tsx` files compose downward: the URL `/dashboard/projects/abc` wraps `app/layout.tsx` → `app/(dashboard)/layout.tsx` → `app/(dashboard)/projects/[projectId]/layout.tsx` (if any) → `page.tsx`. Each layer keeps its state (e.g., a sidebar's scroll position) while the inner content swaps.

Layouts are Server Components by default, which lets them perform server-side data fetches that the children inherit through props or via React `cache()`.

## Route groups

A folder wrapped in parentheses, like `(marketing)`, is a route group. It groups files for organization or layout segmentation without contributing a path segment. Two common uses:

1. Apply a different layout to a subtree without nesting URLs (e.g., a marketing layout for `/about` and `/pricing` separate from the dashboard layout).
2. Co-locate related routes that share concerns (e.g., `(marketing)/about`, `(marketing)/pricing`).

## Dynamic segments

In Next.js 15+, `params` is a Promise. Server Components await it; Client Components unwrap it with React's `use()` hook.

Server Component:

```tsx
// src/app/projects/[projectId]/page.tsx — Server Component (default)
type Params = Promise<{ projectId: string }>;

export default async function Page({ params }: { params: Params }) {
  const { projectId } = await params;
  return <ProjectDetail id={projectId} />;
}
```

Client Component (when the dynamic segment must be read inside a `'use client'` component — e.g., for client-side data fetching with TanStack Query):

```tsx
// src/app/projects/[projectId]/ProjectClient.tsx
'use client';
import { use } from 'react';

type Params = Promise<{ projectId: string }>;

export function ProjectClient({ params }: { params: Params }) {
  const { projectId } = use(params);
  // safe to use projectId in hooks below
  return <InteractiveProjectView id={projectId} />;
}
```

`use(params)` is React 19's mechanism for unwrapping a Promise inside a Client Component; it suspends the component until the value resolves and integrates with the surrounding `<Suspense>` boundary. Server Components keep using `await params` because they execute in async server contexts.

For pre-rendering dynamic routes (SSG), declare the parameter set with `generateStaticParams`:

```tsx
// src/app/projects/[projectId]/page.tsx
export async function generateStaticParams() {
  const projects = await listAllProjectIds();
  return projects.map((p) => ({ projectId: p.id }));
}
```

Catch-all `[...slug]` exposes `params.slug: string[]`. Optional catch-all `[[...slug]]` matches the bare parent path too, with `params.slug` being `undefined` in that case. Use catch-all for documentation trees, content slugs, and category paths.

## Parallel routes

Parallel routes render multiple pages in the same layout simultaneously. Define a slot folder named `@<slot>` next to `children`:

```tsx
// app/dashboard/layout.tsx
export default function Layout({
  children,
  analytics,
  team,
}: {
  children: React.ReactNode;
  analytics: React.ReactNode;
  team: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-2">
      <section>{children}</section>
      <section>{team}</section>
      <section className="col-span-2">{analytics}</section>
    </div>
  );
}
```

Files under `app/dashboard/@analytics/page.tsx` and `app/dashboard/@team/page.tsx` populate the `analytics` and `team` props. Each slot has its own `loading.tsx` and `error.tsx`, allowing independent streaming.

## Intercepting routes

Intercepting routes display a route's content inline within the current view (e.g., a photo modal over a feed) while preserving a separate URL for direct visits. Naming uses dot prefixes: `(.)photo/[id]` intercepts the same level, `(..)photo/[id]` intercepts the parent, `(...)photo/[id]` intercepts from the root.

```text
app/feed/page.tsx
app/feed/(.)photo/[id]/page.tsx     # rendered as modal overlay
app/photo/[id]/page.tsx              # full page on direct navigation
```

Useful for Linear-style modal interactions where deep-linking still works.

## Loading & streaming

`loading.tsx` is wrapped automatically in a `<Suspense>` boundary at that segment. While the segment fetches data, the `loading.tsx` UI streams to the client immediately. Combine with `<Suspense>` inside a page for sub-segment streaming:

```tsx
// app/projects/page.tsx
export default function Page() {
  return (
    <>
      <Suspense fallback={<RecentProjectsSkeleton />}>
        <RecentProjects />
      </Suspense>
      <Suspense fallback={<AllProjectsSkeleton />}>
        <AllProjects />
      </Suspense>
    </>
  );
}
```

## Error boundaries

`error.tsx` must be a Client Component (the boundary needs to attach event handlers). It receives `error` and `reset` props. `global-error.tsx` at the root catches errors that escape the root layout itself.

```tsx
'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div role="alert">
      <h2>Something went wrong</h2>
      <button onClick={reset}>Retry</button>
    </div>
  );
}
```

## Metadata

Static metadata exports a `metadata` object from `layout.tsx` or `page.tsx`:

```tsx
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Projects',
  description: 'Manage your team projects',
  openGraph: { images: ['/og-projects.png'] },
};
```

Dynamic metadata uses `generateMetadata` and may await data:

```tsx
export async function generateMetadata({
  params,
}: {
  params: Promise<{ projectId: string }>;
}): Promise<Metadata> {
  const { projectId } = await params;
  const project = await getProject(projectId);
  return { title: project.name };
}
```

The metadata is composed segment-by-segment; child metadata overrides or merges with parent.

## Route handlers

`route.ts` exports HTTP methods as named functions. Handlers run on the server only, never bundled to the client.

```ts
// app/api/users/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const users = await listUsers();
  return NextResponse.json(users);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const created = await createUser(body);
  return NextResponse.json(created, { status: 201 });
}
```

Use Route Handlers for webhooks, OAuth callbacks, file uploads, or proxying to the backend. For most server mutations triggered by forms, prefer Server Actions instead.

## Linking & navigation

- `<Link href="/projects">` performs client-side navigation with prefetching.
- `useRouter()` (from `next/navigation`) provides imperative navigation in Client Components: `router.push()`, `router.replace()`, `router.refresh()`.
- `redirect('/login')` (from `next/navigation`) inside a Server Component or Server Action throws a redirect.
- `notFound()` triggers the nearest `not-found.tsx`.
- `permanentRedirect()` for 308 status code.

`useRouter()` is Client-only; `redirect()` is Server-only. Mixing these is the most frequent source of "module not found" errors.

## webstack convention

webstack-generated frontend repos follow **FSD-lite** (see `docs/frontend/fsd-architecture.md`): five layers under `src/` — `app`, `widgets`, `features`, `entities`, `shared` — with a one-way import rule. Next.js App Router lives at `src/app/`; this directory simultaneously owns routing (Next.js's responsibility) and the FSD app-layer responsibilities (providers, root layout, global styles).

Implications for App Router files:

- `src/app/<segment>/page.tsx` is a thin orchestrator. It server-fetches data via the generated SDK or via entity queries, then composes `widgets/` and `features/` slices. Business logic does not live in `page.tsx`.
- `src/app/layout.tsx` (root) wraps everything in `src/app/providers/` (Query, Theme, etc.) and applies global styles from `src/app/styles/`.
- Route groups (`(marketing)`, `(dashboard)`, etc.) are still used for layout segmentation. They have no relationship to FSD slices — slices live under `src/features/` and `src/entities/`, not `src/app/`.
- Parallel routes and intercepting routes stay where Next.js expects them under `src/app/`. The components they render are imported from `src/widgets/` or `src/features/`.
- Route Handlers under `src/app/api/` are reserved for FE-only concerns (webhook receivers, BFF proxies, NextAuth callbacks). For domain operations the backend exposes them via OpenAPI; the frontend calls those generated SDKs (see `docs/frontend/tanstack-query.md`) rather than re-defining a Route Handler. Server Actions handle form mutations that don't need a public REST endpoint (see `docs/frontend/server-components.md`).

## Sources

- Next.js App Router docs: https://nextjs.org/docs/app
- Next.js dynamic routes (Server + Client patterns): https://nextjs.org/docs/app/api-reference/file-conventions/dynamic-routes
- Next.js 15 release notes (async params): https://nextjs.org/blog/next-15
- Next.js routing fundamentals: https://nextjs.org/docs/app/building-your-application/routing
- React 19 `use()` API: https://react.dev/reference/react/use

Last verified: 2026-04-26 (Next.js 16.x stable).
