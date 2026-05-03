# Client state with Zustand

> Reference for build-fe SubAgent and frontend-implementer.
> Practical guide to Zustand stores in webstack's RSC + FSD-lite frontend.

## What is client state in webstack

In Next.js 16 App Router, state splits into two distinct categories.

**Server state** originates from the backend — project lists, user profiles, comments. TanStack Query owns it: fetching, caching, refetching on staleness, invalidating after mutations, optionally seeding from the server via `HydrationBoundary`. Putting server state in Zustand is an anti-pattern (see `## Anti-patterns`).

**Client state** is browser-session-only UI data with no server representation: sidebar collapsed/open, active modal, unsaved comment draft, wizard current step. It never needs to be cached, invalidated, or refetched. Zustand owns it.

The two libraries coexist without overlap — see `docs/frontend/tanstack-query.md` for the TanStack side.

**RSC boundary.** Server Components render on the server and cannot call hooks or read Zustand stores. Any component that accesses a Zustand store must carry `'use client'`. The `create(...)` call is browser-side; its file must never be imported from a Server Component.

## Why Zustand

Zustand is the de-facto client state library for Next.js App Router. Vercel's examples, Linear, OpenAI's ChatGPT web frontend, and Cal.com all use it.

**vs Redux / Redux Toolkit.** Redux requires `Provider`, `configureStore`, `createSlice`, `useSelector`, and `useDispatch`. Zustand requires none of that — a store is a hook, no provider needed. Immer integration and DevTools are each a one-line middleware. The result is 3–4× less boilerplate for the same capabilities.

**vs Jotai.** Jotai is atom-based (fine-grained, bottom-up). Zustand is store-based (coarser, simpler). For webstack's typical needs — a few global UI toggles plus feature-local stores — Zustand's slice pattern is more readable than a proliferation of atoms.

**Official `llms.txt`.** Zustand ships a machine-readable API index at `https://zustand.docs.pmnd.rs/llms.txt`. SubAgents should fetch it for the current API surface before writing or reviewing store code.

## webstack convention

### Store locations

| Scope | Path | Use for |
|-------|------|---------|
| Global UI | `src/shared/store/<slice>.ts` | State shared across features: sidebar, active theme, toast queue |
| Feature-local | `src/features/<feature>/model/store.ts` | State confined to one feature: draft form data, wizard step, panel selection |

Each slice file exports one `create(...)` call. Global slices can be composed via the slice pattern (see below), but keep files separate — no monolithic `store/index.ts`.

### Slice pattern

For global UI state, define typed slices and compose them into `useUiStore` — the canonical webstack global UI store:

```typescript
// src/shared/store/sidebarSlice.ts
import { StateCreator } from 'zustand'
export type SidebarSlice = { sidebarOpen: boolean; toggleSidebar: () => void }
export const createSidebarSlice: StateCreator<
  SidebarSlice & ModalSlice, [['zustand/immer', never], ['zustand/devtools', never]], [], SidebarSlice
> = (set) => ({
  sidebarOpen: false,
  toggleSidebar: () => set((s) => { s.sidebarOpen = !s.sidebarOpen }, undefined, 'ui/toggleSidebar'),
})

// src/shared/store/modalSlice.ts
export type ModalSlice = { activeModal: string | null; openModal: (id: string) => void; closeModal: () => void }
export const createModalSlice: StateCreator<
  SidebarSlice & ModalSlice, [['zustand/immer', never], ['zustand/devtools', never]], [], ModalSlice
> = (set) => ({
  activeModal: null,
  openModal: (id) => set((s) => { s.activeModal = id }, undefined, 'ui/openModal'),
  closeModal: () => set((s) => { s.activeModal = null }, undefined, 'ui/closeModal'),
})

// src/shared/store/ui.ts
import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

export const useUiStore = create<SidebarSlice & ModalSlice>()(
  devtools(
    immer((...args) => ({ ...createSidebarSlice(...args), ...createModalSlice(...args) })),
    { name: 'UiStore' },
  ),
)
```

**Middleware stacking rule (Zustand 5):** `devtools` outermost, `immer` innermost. DevTools then observes every Immer draft mutation. Apply middleware only in the composed `create(...)` call — wrapping individual slice creators causes type mismatches and double-mutation bugs.

### Feature-local store

For state confined to one feature (e.g., a multi-step wizard), place the store at `src/features/<feature>/model/store.ts`:

```typescript
// src/features/onboarding/model/store.ts
'use client'

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

type Step = 'profile' | 'workspace' | 'invite' | 'done'
type Profile = { displayName: string; avatarUrl: string | null }
type OnboardingStore = {
  step: Step; profile: Profile
  setStep: (s: Step) => void; setProfile: (p: Partial<Profile>) => void
}

export const useOnboardingStore = create<OnboardingStore>()(
  devtools(
    immer((set) => ({
      step: 'profile', profile: { displayName: '', avatarUrl: null },
      setStep: (step) => set((s) => { s.step = step }, undefined, 'onboarding/setStep'),
      setProfile: (patch) => set((s) => { Object.assign(s.profile, patch) }, undefined, 'onboarding/setProfile'),
    })),
    { name: 'OnboardingStore' },
  ),
)
```

The `'use client'` directive is required — the store creates browser-side state and must be excluded from the server bundle.

### `persist` middleware

Use `persist` when state should survive a full page reload (e.g., sidebar collapsed preference). In Zustand 5, `persist` no longer auto-stores initial state at store creation — call `setState` explicitly if you need the initial value to be written immediately.

```typescript
// src/shared/store/preferencesSlice.ts
'use client'
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'

type PreferencesStore = { sidebarCollapsed: boolean; setSidebarCollapsed: (v: boolean) => void }

export const usePreferencesStore = create<PreferencesStore>()(
  devtools(
    persist(
      immer((set) => ({
        sidebarCollapsed: false,
        setSidebarCollapsed: (v) => set((s) => { s.sidebarCollapsed = v }, undefined, 'preferences/setSidebarCollapsed'),
      })),
      { name: 'webstack-preferences' },
    ),
    { name: 'PreferencesStore' },
  ),
)
```

Only persist true user preferences — ephemeral UI state (open modal, hover) will be stale on the next visit.

## RSC boundary

Server Components cannot read Zustand state. The constraint is fundamental: the store is a React hook, and hooks only run during client rendering.

**Rule:** A store file must never be imported from a Server Component — doing so pulls browser-only hook code into the server bundle and crashes the build.

**Pattern:** keep the Server Component store-free; push the store import into the `'use client'` leaf.

```tsx
// src/widgets/app-shell/AppShell.tsx  (Server Component — no store import)
import { Sidebar } from './Sidebar'

export async function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1">{children}</main>
    </div>
  )
}
```

```tsx
// src/widgets/app-shell/Sidebar.tsx  ('use client' leaf — reads store)
'use client'

import { useUiStore } from '@/shared/store/ui'

export function Sidebar() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggle = useUiStore((s) => s.toggleSidebar)
  return (
    <aside className={`transition-all ${sidebarOpen ? 'w-64' : 'w-16'}`}>
      <button onClick={toggle} aria-label="Toggle sidebar">
        {sidebarOpen ? '←' : '→'}
      </button>
    </aside>
  )
}
```

**Hydration mismatch prevention.** When `persist` reads `localStorage` on first client render, the rehydrated value may differ from the server-rendered initial value — Next.js throws a hydration warning. Fix this by deferring the rendered value to after mount:

```typescript
// src/shared/store/useHydratedStore.ts
'use client'

import { useState, useEffect } from 'react'

export function useHydratedStore<T, S>(
  store: (selector: (state: T) => S) => S,
  selector: (state: T) => S,
): S | undefined {
  const result = store(selector)
  const [data, setData] = useState<S>()
  useEffect(() => { setData(result) }, [result])
  return data  // undefined on server + first paint, hydrated value after
}
```

Guard on `undefined` to keep server and first-paint renders identical. The alternative is `persist`'s `skipHydration: true` option with a manual `store.persist.rehydrate()` call inside `useEffect`.

## Decision tree: TanStack Query vs Zustand

```
Does the data originate from the server?
├── Yes, needs caching / refetch / invalidation → TanStack Query
├── Yes, but only read once and static → pass as prop from Server Component
└── No, browser-session UI state
    ├── Scoped to one component → useState / useReducer
    └── Shared across components → Zustand
```

| State | Where |
|-------|-------|
| Project list from `/api/projects` | TanStack Query |
| User profile `/api/me` | TanStack Query |
| Pagination cursor | TanStack Query (`keepPreviousData`) |
| Selected project ID (filter) | Zustand or `useState` |
| Modal open/close (cross-feature) | Zustand (`useUiStore`) |
| Draft text in comment box | Zustand (`features/comment/model/store.ts`) |
| Sidebar collapsed preference | Zustand + `persist` |
| Wizard current step | Zustand (feature store) |

**Optimistic update interplay.** Optimistic data for a TanStack Query mutation lives in the TQ cache — managed via `onMutate`/`onError`/`onSettled` callbacks (see `docs/frontend/tanstack-query.md`). Zustand is not involved in the optimistic flow itself. The only intersection: close a modal after mutation success by calling `useUiStore.getState().closeModal()` inside `onSuccess`.

## Anti-patterns

**Storing server data in Zustand.** A store that manually fetches and holds `/api/projects` is a hand-rolled, inferior TanStack Query. You lose background refetch, stale-while-revalidate, cache deduplication, and error states. Use TanStack Query for anything with a server origin.

**Subscribing to the entire store.** `const store = useUiStore()` re-renders on every state change anywhere in the store. Always use a selector:

```typescript
// Bad:  const store = useUiStore()
// Good: const open = useUiStore((s) => s.sidebarOpen)
```

**Non-serializable values in state.** Class instances, DOM refs, `Promise` objects, and React components break `persist` serialization and DevTools snapshots. Action functions (`toggleSidebar`, `setStep`) are fine — they are not state. Data values must be serializable primitives, plain objects, or arrays.

**Direct store import in a Server Component.** Even without calling the hook, importing a Zustand store from a Server Component pulls browser-only code into the server bundle. Store files belong in `src/shared/store/` or `src/features/<feature>/model/store.ts` and are imported only from `'use client'` components.

**Middleware inside slice creators.** Middleware (`immer`, `devtools`, `persist`) belongs only in the top-level `create(...)` call. Wrapping individual slices with `immer(...)` produces wrong TypeScript types and potential double-mutation bugs.

**Routing form field values through Zustand.** Forms that submit to the server should use React Hook Form + Zod (see `docs/frontend/rhf-zod.md`). Zustand belongs in pre-form UI state (current wizard step, selected tab) — not field values.

## Sources

- **Zustand GitHub — pmndrs/zustand:** https://github.com/pmndrs/zustand — _authoritative_
- **Zustand docs — llms.txt (machine-readable API index):** https://zustand.docs.pmnd.rs/llms.txt — _authoritative_
- **Zustand docs — Persisting store data (Next.js hydration section):** https://zustand.docs.pmnd.rs/integrations/persisting-store-data — _authoritative_
- **Zustand docs — Migrating to v5:** https://github.com/pmndrs/zustand/blob/main/docs/reference/migrations/migrating-to-v5.md — _authoritative_
- **Zustand docs — Slices pattern:** https://github.com/pmndrs/zustand/blob/main/docs/guides/slices-pattern.md — _authoritative_
- **Zustand docs — Comparison with other solutions:** https://github.com/pmndrs/zustand/blob/main/docs/learn/getting-started/comparison.md — _authoritative_
- **Context7 — pmndrs/zustand (middleware + Next.js snippets):** https://context7.com/pmndrs/zustand/llms.txt — _community: Context7 aggregation of pmndrs/zustand source_

---

Last verified: 2026-05-04 (Zustand 5.x / React 19 / Next.js 16.x).
