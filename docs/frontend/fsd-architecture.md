# FSD Architecture (FSD-lite for Next.js App Router)

> Reference for build-fe SubAgent and frontend-implementer. Defines the layer system webstack uses on the frontend, how it composes with the Next.js App Router, and the rules that the generator + reviewer enforce.

## What is Feature-Sliced Design

Feature-Sliced Design (FSD) is a frontend architecture methodology that organizes a codebase by **business slices** inside a small, fixed set of **layers**. Code is grouped first by what it represents in the product (a "user", a "project", a "comment"), then by what role it plays at runtime (entity, feature, widget, page). Cross-feature coupling becomes visible at the import boundary, and each slice is independently editable, testable, and removable.

For webstack, FSD is the frontend mirror of the backend's DDD/Hexagonal/Modulith discipline: BE has bounded contexts containing layered code; FE has slices containing layered code. The two architectures don't dictate each other but share the same intent — domain-shaped boundaries with explicit dependencies.

webstack adopts a slim **FSD-lite** variant tuned for the Next.js App Router. The trade-off and the exact layer layout are below.

## Why FSD-lite (not vanilla FSD)

Vanilla FSD defines six layers: `app`, `pages`, `widgets`, `features`, `entities`, `shared`. The vanilla `app` layer (providers, layout, global styles) and the vanilla `pages` layer (page components) collide with Next.js App Router's `app/` directory, which owns routing through file-based conventions. The official FSD guide for Next.js works around this by placing the entire FSD tree under `src/` and using the root `app/` directory only for thin re-exports.

webstack chooses a different trade-off. We **drop the vanilla FSD `pages` layer** and let Next.js App Router's `src/app/` absorb its responsibility. The remaining five layers — `app`, `widgets`, `features`, `entities`, `shared` — sit under `src/` alongside `src/app/`. Pages are written directly inside Next.js routes; they assemble widgets and features but contain no business logic of their own.

This costs us:

- The vanilla FSD eslint config (which assumes a `pages` layer) needs minor tweaking — the `boundaries`/`steiger` rules are configured for five layers, not six.
- Some FSD documentation and tutorials reference `pages/` patterns that webstack handles via Next.js routes instead.

In return:

- No Next.js workaround (no thin re-export shells, no dummy `pages/` folder, no `src/`-vs-root duality).
- Page files keep the standard Next.js shape that anyone familiar with App Router can read.
- `middleware.js`, `instrumentation.js`, `not-found.tsx`, `loading.tsx`, `error.tsx`, parallel routes, intercepting routes — all stay where Next.js expects them.

## Layer definitions

### `src/app/`

Next.js App Router routes plus FSD app-layer responsibilities (providers, root layout, global styles, fonts). Each route file (`page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`) lives where the URL says it should. Routes compose widgets and features; they do not own business logic.

Examples of allowed code in `src/app/`:

- `layout.tsx`: imports providers from inside `src/app/providers/`, sets `<html>`/`<body>`, mounts `QueryClientProvider`, theme provider, font CSS variables.
- `page.tsx`: server-fetches data via the generated SDK or directly composes a feature/widget/entity.
- `(group)/`: route groups for shared layouts.
- `api/route.ts`: webhook receivers, OAuth callbacks, file uploads (FE-only concerns; domain operations live in the backend).

Subdirectories of `src/app/` are URL segments. webstack convention: do not put non-route code (e.g., shared helpers, providers) directly in `src/app/<segment>/`; put them in `src/app/providers/` or `src/shared/`.

### `src/widgets/`

Composite UI blocks made by combining features and entities, plus their own presentational chrome. Header, sidebar, filter panel, data table with sorting, project card, dashboard summary card.

A widget can import from `features/`, `entities/`, `shared/`. A widget cannot import another widget (sibling imports across the same layer are forbidden — composing widgets is the page's job).

### `src/features/`

Slices that represent **user-meaningful interactions**: "create project", "filter projects", "edit comment", "log in". A feature owns its UI (form, modal, button group), its validation schema, its API mutation/query, and any client-side state.

Each feature is a directory under `src/features/`:

```
src/features/create-project/
├── ui/
│   └── CreateProjectForm.tsx
├── model/
│   └── schema.ts                 # Zod schema (server-shared via re-export from RHF setup)
├── api/
│   └── mutations.ts              # TanStack Query mutation built on generated SDK
└── index.ts                      # public barrel
```

A feature can import from `entities/`, `shared/`. It cannot import from `widgets/`, `app/`, or another `features/<other>` slice — features are independent. If two features need to share something, the shared piece moves to `entities/` (if it's domain-shaped) or `shared/` (if it's generic).

### `src/entities/`

Business entities — `User`, `Project`, `Comment`, `Invoice`, etc. An entity slice owns the entity's display components (e.g., `<UserAvatar>`, `<ProjectName>`), its read-side queries (`useGetProject`), and any TypeScript types specific to it. Entities don't own mutations — those live in features.

```
src/entities/project/
├── ui/
│   ├── ProjectName.tsx
│   └── ProjectStatusBadge.tsx
├── api/
│   └── queries.ts                # TanStack Query queries via generated SDK
├── model/
│   └── types.ts                  # entity-specific TS types if not from generated SDK
└── index.ts
```

An entity can import from `shared/` only.

### `src/shared/`

Reusable building blocks with no business meaning. Every layer above can import from `shared/`; `shared/` cannot import from any other layer.

```
src/shared/
├── ui/                           # ShadCN primitives + cva-extended variants
│   ├── button.tsx
│   ├── card.tsx
│   ├── form.tsx
│   └── ... (everything `npx shadcn add` produces)
├── api/
│   └── generated/                # @hey-api/openapi-ts output (read-only)
│       ├── types.ts
│       ├── sdk.ts
│       └── queries.ts
├── lib/                          # cn(), clsx wrappers, date formatters
│   └── utils.ts
├── config/                       # constants, env reads, feature flags
└── hooks/                        # generic hooks (useDebounce, useMediaQuery)
```

ShadCN primitives are placed under `src/shared/ui/` because they are infrastructure for higher layers to compose. The ShadCN `components.json` is configured with `"aliases.ui": "@/shared/ui"` so `npx shadcn add` writes to the right path. The generated OpenAPI SDK lives at `src/shared/api/generated/` — committed, read-only, and regenerated via `pnpm gen:api` — and `entities/<x>/api/` and `features/<x>/api/` import from it.

## Import rules (the layer dependency graph)

```
app  →  widgets  →  features  →  entities  →  shared
```

A higher layer imports from any lower layer. A layer never imports sideways (no widget→widget, feature→feature, entity→entity). A layer never imports upward.

Concrete rules:

- `src/app/**` may import from `src/widgets/**`, `src/features/**`, `src/entities/**`, `src/shared/**`.
- `src/widgets/**` may import from `src/features/**`, `src/entities/**`, `src/shared/**`.
- `src/features/<a>/**` may import from `src/entities/**`, `src/shared/**`. **Not** from `src/features/<b>/**`.
- `src/entities/<a>/**` may import from `src/shared/**`. **Not** from `src/entities/<b>/**`.
- `src/shared/**` may import only from `src/shared/**`.

Each slice's public surface is its `index.ts` barrel; deeper imports (`@/features/create-project/ui/CreateProjectForm`) are discouraged. The barrel makes refactors local — moving `CreateProjectForm.tsx` doesn't ripple.

webstack enforces these rules via `eslint-plugin-boundaries` (lint-time) and via `code-reviewer` SubAgent (review-time). The init skill writes both configs.

## Mapping to webstack tooling

- **ShadCN primitives** → `src/shared/ui/`. `components.json` sets `"aliases.ui": "@/shared/ui"`.
- **Generated SDK** (`@hey-api/openapi-ts`) → `src/shared/api/generated/`. The `openapi-ts.config.ts` `output` field points here.
- **Zod schemas for forms** → `src/features/<feature>/model/schema.ts`. Re-imported by Server Actions when the form posts to a same-repo endpoint.
- **TanStack Query mutations** → `src/features/<feature>/api/mutations.ts`. Wraps the generated mutation hook from `src/shared/api/generated/`.
- **TanStack Query queries** → `src/entities/<entity>/api/queries.ts`. Wraps the generated query hook.
- **Page-level data fetch** (Server Component) → directly inside `src/app/<route>/page.tsx`, calling the generated SDK or composing entity queries.

## Comparison with vanilla FSD

| Aspect | Vanilla FSD | webstack FSD-lite |
|---|---|---|
| Layers | 6 (app, pages, widgets, features, entities, shared) | 5 (app, widgets, features, entities, shared) |
| Page components | `src/pages/<name>/` | `src/app/<route>/page.tsx` (Next.js App Router) |
| Route declarations | Re-export shell at root `app/<segment>/page.tsx` | `src/app/<segment>/page.tsx` directly, no re-export |
| Dummy `pages/` folder at root | Required (Next.js Pages Router suppression) | Not needed |
| FSD app layer | `src/app/providers/`, `src/app/styles/` | Same — but coexists with Next.js routing in the same `src/app/` |
| `middleware.js` location | Project root | Project root (unchanged) |
| eslint-plugin-boundaries config | 6 elements | 5 elements |
| Compatible with steiger linter (FSD-specific) | Yes | Partial — `pages/` rules don't apply |

If a project later wants the vanilla split (a separate `pages/` layer for explicit testability of page composition), the migration is local: move `src/app/<route>/page.tsx` bodies into `src/pages/<route>/index.tsx` and replace the originals with re-exports. webstack's FSD-lite keeps that escape hatch open.

## Anti-patterns

- **Cross-feature import** (`features/a/ui/Foo` imports from `features/b/ui/Bar`) — should not happen. Promote the shared bit to `entities/` or `shared/`.
- **Importing through deep paths** instead of the slice's `index.ts` barrel — couples consumers to internal structure. Use `import { CreateProjectForm } from '@/features/create-project'`.
- **Putting page-shape components in `widgets/`** — widgets are reusable across pages; page assembly belongs in `src/app/<route>/page.tsx`.
- **Putting business logic in `src/app/<route>/page.tsx`** — pages should be thin orchestrators. Move feature-shaped logic into a feature slice.
- **Multiple feature slices for one user-facing action** — if you find `features/create-project-step-1`, `features/create-project-step-2`, fold them into one slice with multi-step UI internal to it.

## Sources

- Feature-Sliced Design official: https://feature-sliced.design/
- FSD with Next.js (official guidance): https://feature-sliced.design/docs/guides/tech/with-nextjs
- eslint-plugin-boundaries: https://github.com/javierbrea/eslint-plugin-boundaries
- steiger (FSD-specific linter): https://github.com/feature-sliced/steiger

Last verified: 2026-06-22.
