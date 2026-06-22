# Server vs Client Components

> Reference for build-fe SubAgent. Defines when to keep code on the server, when to ship JS to the client, and how to compose across the boundary safely.

## What runs where

In the Next.js App Router, components under `app/` default to **Server Components**. They render to HTML on the server, do not ship JavaScript to the client, and may directly read environment variables, call databases, or import server-only libraries (e.g., `fs`, `pg`, ORM clients). Their output is streamed as RSC payload (a serialized React tree) and reconciled on the client from that serialized payload — Server Components never hydrate; only Client Components do.

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

## Server Actions (FE-only form mutations)

A Server Action is a server-side function callable from a Client Component, typically as a `<form action={...}>` handler or a `useTransition` callback. Mark it with `'use server'`.

**webstack scope (canon).** Server Actions are **not** webstack's path for backend mutations. Operations against the backend domain go FE → generated SDK → Spring via TanStack `useMutation` (see [`docs/frontend/tanstack-query.md`](tanstack-query.md)); there is no `actions.ts` calling a Spring/backend service. Reserve Server Actions for **FE-only** persistence that never leaves the Next.js process — e.g., saving a UI preference or a NextAuth profile blurb:

```ts
// src/features/profile/api/save-blurb-action.ts
'use server';

import { z } from 'zod';
import { revalidatePath } from 'next/cache';

const Blurb = z.object({ blurb: z.string().max(280) });

export async function saveProfileBlurb(formData: FormData) {
  const parsed = Blurb.parse({ blurb: formData.get('blurb') });
  await savePreference('profile.blurb', parsed.blurb);  // FE-only store, not the Spring backend
  revalidatePath('/settings/profile');
}
```

Server Actions can be inline (defined in a Server Component file) or extracted to a dedicated file. They serialize their arguments, run on the server, and return a serializable result. The Next.js runtime wires them to a unique endpoint. Always validate inputs (Zod) — a Server Action's URL is callable by anyone who inspects the page.

For these FE-only form mutations, Server Actions beat Route Handlers: they get progressive enhancement (work without JS), automatic revalidation hooks, and direct access to the request context.

## React 19 form hooks (`useActionState`, `useFormStatus`, `useOptimistic`)

React 19 (stable since 2025) ships three hooks that pair naturally with Server Actions and remove most of the bespoke wiring webstack used to hand-write inside RHF + Zod forms:

- **`useActionState(action, initialState)`** — wraps a Server Action and exposes `[state, formAction, isPending]`. The Server Action itself receives `(prevState, formData)` and returns the next state. This is the canonical pattern for "submit a form, render the server's response inline" without Client-side state plumbing.
- **`useFormStatus()`** — returns `{ pending, data, method, action }` for the **enclosing** form. It must be called from a child of `<form>`, never the form itself. Useful in submit buttons that need to disable themselves and show a spinner.
- **`useOptimistic(state, updateFn)`** — returns `[optimisticState, addOptimistic]` that lets the UI render an instant guess while the Server Action is in flight. The optimistic state is automatically reconciled with the real state once the action returns.

Minimal example combining all three:

```tsx
'use client';

import { useActionState, useOptimistic } from 'react';
import { useFormStatus } from 'react-dom';
import { createComment } from './actions';

type State = { error?: string };

function SubmitButton() {
  const { pending } = useFormStatus();
  return <button disabled={pending}>{pending ? 'Saving…' : 'Add comment'}</button>;
}

export function CommentForm({ initial }: { initial: Comment[] }) {
  const [state, formAction] = useActionState<State, FormData>(
    async (_prev, formData) => createComment(formData),
    {},
  );
  const [optimistic, addOptimistic] = useOptimistic(initial, (curr, next: Comment) => [
    ...curr,
    next,
  ]);

  return (
    <form
      action={(fd) => {
        addOptimistic({ id: crypto.randomUUID(), text: fd.get('text') as string });
        formAction(fd);
      }}
    >
      <textarea name="text" required />
      <SubmitButton />
      {state.error && <p role="alert">{state.error}</p>}
      <ul>
        {optimistic.map((c) => (
          <li key={c.id}>{c.text}</li>
        ))}
      </ul>
    </form>
  );
}
```

**When to use these vs RHF + Zod**:

- **Single-field or simple forms** (subscribe, like, comment, follow): React 19 hooks are enough and ship less JS.
- **Complex forms** (multi-step, async cross-field validation, dynamic field arrays, rich client-side error UX): RHF + Zod still wins. RHF's uncontrolled-by-default model + Zod schema reuse outclass React 19's primitives at scale.
- **Hybrid**: webstack convention is to keep RHF + Zod as the default for backend-targeted form mutations (so client and server share one Zod schema — see `docs/frontend/rhf-zod.md`). Use React 19 hooks selectively for FE-only, single-action forms (e.g., a NextAuth profile blurb update Server Action).

## Type safety across boundary

Props passed from a Server Component to a Client Component are serialized with the RSC serialization format (a superset of JSON). **Allowed:**

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

webstack-generated frontends follow FSD-lite (see `docs/frontend/fsd-architecture.md`). The Server/Client split maps onto FSD layers as follows:

- **`src/app/<route>/page.tsx`**: Server Component by default. Calls the generated SDK or entity-level queries (`src/entities/<x>/api/queries.ts`) directly with `await`, then renders widgets/features.
- **`src/widgets/<widget>/`**: usually Server Components. A widget that needs interactivity (a sticky header that listens to scroll) marks just its interactive leaf with `'use client'`.
- **`src/features/<feature>/ui/<Component>.tsx`**: typically `'use client'`. Features are user-facing interactions (forms, mutations, optimistic updates), so Client by default makes sense — but the directive still goes only on the leaf, not the whole feature directory.
- **`src/entities/<entity>/ui/<Display>.tsx`**: Server Components when they only render data; mark `'use client'` only if they wrap an interactive primitive (e.g., a clickable card that opens a modal).
- **`src/shared/ui/*` (ShadCN primitives)**: ShadCN components ship with `'use client'` where they wrap Radix primitives that need browser context — leave that as is. Pure presentational primitives (`Card`, `Badge`) stay server-friendly.

Default to Server Components calling the SDK and passing the result as props. Promote a subtree to Client Component only when:

1. The data is interaction-driven (mutations, optimistic updates, search-as-you-type) — use TanStack Query in a Client Component (see `docs/frontend/tanstack-query.md`). The query/mutation lives at `src/features/<feature>/api/` (mutation) or `src/entities/<entity>/api/` (query).
2. The component needs browser APIs (modals, toasts, tooltips, drag-and-drop).
3. The data must update without a full route refresh (live dashboards, polling).

Form submissions inside the frontend repo's own surface (e.g., contact forms, FE-only profile/preference updates via NextAuth) use Server Actions with Zod validation; the Server Action and the form share the same Zod schema from `src/features/<feature>/model/schema.ts`. Form submissions targeting the backend's domain operations call the generated SDK from a Client Component using TanStack Query mutations under `src/features/<feature>/api/mutations.ts` — never a Server Action that proxies the backend.

## Sources

- Server Components: https://nextjs.org/docs/app/building-your-application/rendering/server-components
- Client Components: https://nextjs.org/docs/app/building-your-application/rendering/client-components
- Composition patterns: https://nextjs.org/docs/app/building-your-application/rendering/composition-patterns
- Server Actions: https://nextjs.org/docs/app/building-your-application/data-fetching/server-actions-and-mutations
- React 19 release: https://react.dev/blog/2024/12/05/react-19
- `useActionState`: https://react.dev/reference/react/useActionState
- `useFormStatus`: https://react.dev/reference/react-dom/hooks/useFormStatus
- `useOptimistic`: https://react.dev/reference/react/useOptimistic

Last verified: 2026-06-22 (React 19.x stable).
