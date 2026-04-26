# Server vs Client Components

> Reference for build-fe SubAgent. Defines when to keep code on the server, when to ship JS to the client, and how to compose across the boundary safely.

## What runs where

In the Next.js App Router, components under `app/` default to **Server Components**. They render to HTML on the server, do not ship JavaScript to the client, and may directly read environment variables, call databases, or import server-only libraries (e.g., `fs`, `pg`, ORM clients). Their output is streamed as RSC payload (a serialized React tree) and rehydrated by the client runtime — only as static markup, never with hydration of those components themselves.

A **Client Component** is opted in by placing the directive `'use client'` at the very top of the file. The file and every module it imports are bundled to JavaScript that ships to the browser. Client Components hydrate on load and may use `useState`, `useEffect`, `useRef`, browser APIs, event handlers, and third-party libraries that depend on the DOM.

The directive is a boundary marker, not a per-component switch: anything imported from a `'use client'` file becomes part of the client bundle. A single component can be rendered as a server child of a parent client component (via the `children` pattern below), but if it imports a Client Component, that component's JS ships.

## When to use Client Component

Add `'use client'` when the component needs any of:

- Event handlers: `onClick`, `onChange`, `onSubmit`, etc.
- React state or effects: `useState`, `useReducer`, `useEffect`, `useLayoutEffect`.
- Refs and imperative DOM APIs: `useRef`, `forwardRef`, `useImperativeHandle`.
- Browser-only APIs: `window`, `document`, `localStorage`, `IntersectionObserver`, `matchMedia`, `navigator.clipboard`.
- Third-party libraries that require a browser context: `react-hook-form`, `framer-motion`, `embla-carousel-react`, most charting libraries.
- React Context providers that wrap interactive children: `<ThemeProvider>`, `<QueryClientProvider>`.

The directive should appear on the smallest leaf that needs it. Putting `'use client'` at the top of a layout or page forces the entire subtree into the client bundle and forfeits the RSC benefits.

## When to keep Server Component

Default to Server Component unless the rule above forces otherwise. Server Components are right for:

- **Data fetching**: `await db.query(...)` directly inside the component. No useEffect, no waterfalls.
- **Static rendering**: marketing pages, documentation, blog posts.
- **SEO content**: visible text, metadata, structured data — all rendered server-side.
- **Secret-bearing logic**: API keys, service-role tokens, database credentials. Never exposed to the bundle.
- **Heavy dependencies**: markdown parsers, syntax highlighters, image processors. They stay on the server.

Server Components return JSX but cannot accept event handlers as props (those would not survive serialization). They can still render Client Components and pass serializable props.

## Composition pattern

The serialization boundary is one-way: Server Components may import and render Client Components, but Client Components cannot import Server Components. To "embed" server-rendered content inside a client tree, pass the Server Component as `children` (or any prop) from a parent Server Component:

```tsx
// app/page.tsx (Server Component)
import { ClientShell } from './ClientShell';
import { ServerOnlyContent } from './ServerOnlyContent';

export default function Page() {
  return (
    <ClientShell>
      <ServerOnlyContent />
    </ClientShell>
  );
}
```

```tsx
// ClientShell.tsx
'use client';

import { useState } from 'react';

export function ClientShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section onClick={() => setOpen(!open)}>
      {open && children}
    </section>
  );
}
```

The page renders `<ServerOnlyContent />` as RSC output, then passes that already-rendered tree as the `children` prop into the Client Component. The Server Component never gets imported by the Client file, so its dependencies stay off the client bundle.

## Anti-patterns

- **`'use client'` at the top of every file.** Defeats RSC entirely. Move the directive down to the actual interactive leaf.
- **Fetching data in a Client Component when SSR was sufficient.** A `useEffect` + `fetch` waterfall replaces what should have been a server-side `await`. Convert to Server Component or pass server-fetched data as a prop.
- **Passing huge serialized data to client.** Every prop crossing the server→client boundary is JSON-stringified and embedded in the RSC payload. A 5MB array makes initial HTML 5MB. Filter on the server.
- **Mixing imports.** Importing a Client Component from a server file is fine; importing a server-only module (e.g., `import 'fs'`) from a Client Component crashes the build.
- **Using context to share data the server already had.** Pass it as a prop instead.

## Server Actions (form mutations)

A Server Action is a server-side function callable from a Client Component, typically as a `<form action={...}>` handler or a `useTransition` callback. Mark it with `'use server'`:

```ts
// app/projects/actions.ts
'use server';

import { z } from 'zod';
import { revalidatePath } from 'next/cache';

const CreateProject = z.object({ name: z.string().min(1) });

export async function createProject(formData: FormData) {
  const parsed = CreateProject.parse({ name: formData.get('name') });
  await db.project.insert(parsed);
  revalidatePath('/projects');
}
```

Server Actions can be inline (defined in a Server Component file) or extracted to a dedicated `actions.ts`. They serialize their arguments, run on the server, and return a serializable result. The Next.js runtime wires them to a unique endpoint. Always validate inputs (Zod) — a Server Action's URL is callable by anyone who inspects the page.

For form-driven mutations, Server Actions are preferred over Route Handlers: they get progressive enhancement (work without JS), automatic revalidation hooks, and direct access to the request context.

## Type safety across boundary

Props passed from a Server Component to a Client Component are serialized with `React.RSC`'s superset of JSON. **Allowed:**

- Primitives: string, number, boolean, null, undefined, BigInt.
- Plain objects and arrays composed of allowed types.
- Symbols registered via `Symbol.for`.
- Promises (RSC-aware: the client awaits them).
- Server Action references (treated as opaque function tokens).
- React elements (already-rendered RSC trees).

**Disallowed:**

- Class instances (Date, Map, Set, custom classes). Convert Date to ISO string; Map/Set to plain objects/arrays.
- Functions other than Server Actions (event handlers, callbacks).
- DOM nodes, file handles, streams.

In practice: if your prop wouldn't survive `JSON.stringify` plus the Promise/element exception, it cannot cross the boundary. The error message at build time is `Only plain objects can be passed...`.

## webstack convention

webstack-generated frontends fetch data from the backend via the OpenAPI-generated SDK. Default to Server Components calling the SDK and passing the result as props. Promote a subtree to Client Component only when:

1. The data is interaction-driven (mutations, optimistic updates, search-as-you-type) — use TanStack Query in a Client Component (see `docs/frontend/tanstack-query.md`).
2. The component needs browser APIs (modals, toasts, tooltips, drag-and-drop).
3. The data must update without a full route refresh (live dashboards, polling).

Form submissions inside the frontend repo's own surface (e.g., contact forms, profile updates persisted in Supabase via NextAuth) use Server Actions with Zod validation. Form submissions targeting the backend's domain operations call the generated SDK from a Client Component using TanStack Query mutations, never duplicating the validation in a Server Action.

## Sources

- Server Components: https://nextjs.org/docs/app/building-your-application/rendering/server-components
- Client Components: https://nextjs.org/docs/app/building-your-application/rendering/client-components
- Composition patterns: https://nextjs.org/docs/app/building-your-application/rendering/composition-patterns
- Server Actions: https://nextjs.org/docs/app/building-your-application/data-fetching/server-actions-and-mutations
