# TypeScript best practices

> Reference for build-fe SubAgent and frontend-implementer.
> Strict-mode TypeScript patterns for webstack's Next.js 16 + RSC + FSD-lite + generated SDK stack.

## What is type safety in webstack

webstack frontends operate under the strictest TypeScript configuration the compiler supports. The goal is that every value flowing through the codebase — from a raw HTTP response parsed by the generated SDK, through a Zod-validated form submission, to a Server Component prop — carries a type that the compiler has verified. No gaps at module boundaries, no silent `any` widening, no runtime surprises from optional properties.

Two artefacts form the foundation:

**1. The `tsconfig.json` strict baseline.** webstack projects ship with `strict: true` and four additional flags that `strict` does not enable. These flags are discussed in detail in `## webstack convention`.

**2. The generated SDK in `src/shared/api/generated/`.** `@hey-api/openapi-ts` reads the OpenAPI contract and emits fully-typed request/response types, service functions, and (when configured) Zod schemas. These generated types are the canonical representation of every HTTP boundary. Application code composes *from* them using `Pick`, `Omit`, and intersection types rather than redefining parallel shapes.

Together, the strict baseline and the generated SDK mean TypeScript can catch entire classes of error — missing required fields in API payloads, stale field names after a contract update, nullable values passed as non-nullable — before the code runs.

## Why this approach

**Code stability.** The strict flags expose latent bugs that permissive settings hide. `noUncheckedIndexedAccess` forces handling of the case where an array or record lookup returns nothing. `exactOptionalPropertyTypes` prevents silently assigning `undefined` to a field that should simply be absent. Catching these at compile time prevents production bugs that only surface on edge-case data.

**AI codegen safety net.** SubAgents generating feature code in this stack produce typed function signatures and typed component props. If a generated snippet omits a required field or misuses a nullable value, the compiler rejects it immediately. The strict baseline acts as a mechanical reviewer that operates at every save, before any human review step.

**IDE feedback loop.** `noImplicitOverride`, `noFallthroughCasesInSwitch`, and the full `strict` family all feed TypeScript's language server. Editors surface errors inline while the agent is typing, narrowing the distance between making an error and being told about it from minutes (CI) to seconds.

**Serializable RSC boundary.** Server Components pass props to Client Components across the RSC boundary. That boundary only allows serializable values — no functions, no class instances, no React elements. TypeScript alone cannot enforce serializability, but combined with the FSD import rule (Server Components pass plain data; Client Components hold event handlers and state), strong typing makes the boundary violations visible: a prop typed `() => void` in a Server Component is an immediate red flag.

## webstack convention

### `tsconfig.json` settings

```jsonc
// tsconfig.json — webstack strict baseline (add to Next.js defaults)
{
  "compilerOptions": {
    "moduleResolution": "bundler",   // Next.js 16 required
    "strict": true,                  // strictNullChecks + noImplicitAny + more
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true
  }
}
```

**What each flag does:**

| Flag | What it adds beyond `strict` |
|------|------------------------------|
| `strict` | Enables `strictNullChecks`, `noImplicitAny`, `strictFunctionTypes`, `strictPropertyInitialization`, `strictBindCallApply`, and `useUnknownInCatchVariables`. |
| `noUncheckedIndexedAccess` | Adds `\| undefined` to every index-signature access (`obj[key]`, `arr[i]`). Forces a guard before use. |
| `exactOptionalPropertyTypes` | `{ a?: string }` means `a` may be absent but not `undefined`. Prevents `obj.a = undefined` unless the type explicitly includes `\| undefined`. |
| `noImplicitOverride` | Subclass methods that override a base class method must carry the `override` keyword. Prevents silent divergence when a base method is renamed. |
| `noFallthroughCasesInSwitch` | Non-empty `case` blocks must terminate with `break`, `return`, or `throw`. Prevents unintentional fall-through bugs. |

### `satisfies` for object literals

Use `satisfies` when you want the compiler to validate an object literal against a type *without* widening the inferred type. This is the right tool for route config maps, event-handler maps, and any literal that must conform to a wider type while keeping its narrow inference downstream.

```ts
// src/shared/config/routes.ts
type RouteConfig = { label: string; href: string; icon?: React.ReactNode }
type NavRoutes = Record<string, RouteConfig>

export const navRoutes = {
  dashboard: { label: 'Dashboard', href: '/dashboard' },
  projects:  { label: 'Projects',  href: '/projects'  },
  settings:  { label: 'Settings',  href: '/settings'  },
} satisfies NavRoutes
// typeof navRoutes.dashboard is { label: string; href: string }
// not RouteConfig — specificity is preserved
```

Do not use `as NavRoutes` here — a type assertion bypasses the compiler check and will silently accept a wrong shape. `satisfies` validates *and* preserves.

### Brand types

Primitive types like `string` and `number` are structurally identical — the compiler cannot distinguish a `UserId` from a `ProjectId` without help. Brand types create nominal distinctions:

```ts
// src/shared/types/brands.ts
type Branded<T, Brand extends string> = T & { readonly __brand: Brand }

export type UserId      = Branded<string, 'UserId'>
export type ProjectId   = Branded<string, 'ProjectId'>
export type WorkspaceId = Branded<string, 'WorkspaceId'>

// Constructor — the only place that calls `as`. Everywhere else the type flows structurally.
export function asUserId(raw: string): UserId { return raw as UserId }
```

Brand type definitions belong in `src/shared/types/`. Entity-layer code that maps API responses to domain types calls the constructors:

```ts
// src/entities/user/model/user.ts
import type { UserId } from '@/shared/types/brands'

export type User = { id: UserId; email: string; displayName: string }
```

### Exhaustive `never` checks with `assertNever`

When a `switch` handles a discriminated union, `assertNever` in the default branch converts an unhandled case into a compile-time error:

```ts
// src/shared/lib/assert-never.ts
export function assertNever(value: never, message?: string): never {
  throw new Error(message ?? `Unhandled case: ${JSON.stringify(value)}`)
}

// Usage
type ProjectStatus = 'active' | 'archived' | 'draft'

function statusLabel(status: ProjectStatus): string {
  switch (status) {
    case 'active':   return 'Active'
    case 'archived': return 'Archived'
    case 'draft':    return 'Draft'
    default:         return assertNever(status)
    // Adding a new union member without updating this switch → compile error here.
  }
}
```

The `never` parameter is what triggers the check. A plain `throw new Error(...)` in the default branch does not — `never` is required.

## Zod ↔ TypeScript inference

This section covers *type inference patterns* only. For form integration (React Hook Form + Zod), see `docs/frontend/rhf-zod.md`.

### `z.infer` — the primary inference utility

```ts
import { z } from 'zod'

const createProjectSchema = z.object({
  name:        z.string().min(1).max(100),
  description: z.string().max(500).optional(),
  workspaceId: z.string(),
})

// The TypeScript type is inferred from the schema — no duplication
type CreateProjectInput = z.infer<typeof createProjectSchema>
// { name: string; description?: string | undefined; workspaceId: string }
```

Always derive the type with `z.infer<typeof schema>` rather than writing a parallel interface. The schema *is* the source of truth; the interface is a consequence.

### `z.input<>` vs `z.output<>` — when they diverge

For schemas without `.transform()` or `.default()`, `z.input` and `z.output` are identical to `z.infer`. They diverge when the schema transforms its value:

```ts
const dateSchema = z.string().datetime().transform((s) => new Date(s))

type DateIn  = z.input<typeof dateSchema>   // string
type DateOut = z.output<typeof dateSchema>  // Date

// z.infer<> returns the OUTPUT type (post-transform)
type DateInferred = z.infer<typeof dateSchema>  // Date
```

A `.default()` also introduces divergence — the input type allows `undefined`, the output type does not:

```ts
const withDefault = z.object({
  pageSize: z.number().default(20),
})

type In  = z.input<typeof withDefault>   // { pageSize?: number | undefined }
type Out = z.output<typeof withDefault>  // { pageSize: number }
```

**Rule:** Use `z.input<>` for the type you accept at a function boundary (e.g., form data, raw API query params). Use `z.output<>` (or `z.infer<>`) for the type you work with after calling `schema.parse(...)`.

### Combining Zod with generated SDK types

`@hey-api/openapi-ts` generates TypeScript types in `src/shared/api/generated/`. These represent the contract. Zod schemas live in `src/features/<feature>/model/schema.ts` and represent the *form input*. They overlap but are not identical — a form may collect a subset of a request body and add client-side-only fields.

The pattern is to derive the Zod schema from the generated type where possible:

```ts
// src/shared/api/generated/types.gen.ts (read-only, generated)
// export type CreateProjectBody = { name: string; description?: string; workspaceId: string }

// src/features/project/model/schema.ts
import type { CreateProjectBody } from '@/shared/api/generated'
import { z } from 'zod'

// Zod schema matches the generated type — DRY because we derive it from the type shape
export const createProjectSchema = z.object({
  name:        z.string().min(1, 'Name is required').max(100),
  description: z.string().max(500).optional(),
  workspaceId: z.string().min(1),
}) satisfies z.ZodType<CreateProjectBody>
// satisfies here proves the schema output is assignable to CreateProjectBody
// TypeScript errors if the schema produces a shape incompatible with the generated type
```

The `satisfies z.ZodType<GeneratedType>` pattern is the bridge: the schema is still Zod (with validations), but the compiler confirms it aligns with the contract type.

## Composing generated SDK types

### Rules

1. **Never modify files in `src/shared/api/generated/`.** They are regenerated by `pnpm gen:api` and any edits are overwritten.
2. **Compose, don't copy.** Use TypeScript utility types on the generated types rather than writing parallel interfaces.
3. **Wrap in a domain type when the shape should diverge.** If the application's mental model of an entity differs from the API's (e.g., the API returns flat data the app groups), create a domain type in `src/entities/<entity>/model/`.

### Utility type composition

```ts
// src/entities/project/model/project.ts
import type { Project as ApiProject } from '@/shared/api/generated'

// Card view — subset via Pick
export type ProjectCard = Pick<ApiProject, 'id' | 'name' | 'description' | 'memberCount'>

// Update payload — strip server-managed fields via Omit
export type ProjectUpdatePayload = Omit<ApiProject, 'id' | 'createdAt' | 'updatedAt' | 'archivedAt'>

// Client-enriched type — add a UI-only field without touching the generated type
export type ProjectWithStatus = ApiProject & { uiStatus: 'loading' | 'idle' | 'error' }
```

### When to wrap in a domain type vs use directly

**Use the generated type directly** in:

- `src/entities/<entity>/api/` — query functions return the generated type
- `src/shared/ui/` components that are purely presentational and own no business logic

**Wrap in a domain type** when:

- The application needs computed or derived fields not present in the API response
- The entity layer normalises data (e.g., parses ISO strings to `Date` objects via a Zod transform)
- Multiple API resources are combined into one application concept

```ts
// domain type with parsed dates — the only place that transforms createdAt
// src/entities/project/model/project.ts
import type { Project as ApiProject } from '@/shared/api/generated'
export type Project = Omit<ApiProject, 'createdAt' | 'updatedAt'> & {
  createdAt: Date
  updatedAt: Date
}
```

### RSC serialization constraint

Server Components serialize props to pass them to Client Components — the boundary accepts only JSON-compatible values. Generated SDK types use `string` for dates and plain primitives, which are safe. Two common pitfalls:

- `Date` objects are not JSON-serializable. Pass the ISO `string` from the API response and parse in the Client Component.
- `exactOptionalPropertyTypes` means `{ label?: string }` allows the key to be absent but not explicitly `undefined`. JSON serialization drops `undefined` values anyway, so the two align correctly.

## Anti-patterns

**`any` and `as any`.** Assigning `any` or casting through `any` disables the type system for that value and everything that depends on it. The only tolerable use is a transitional `// TODO: remove any` comment with a linked ticket. Never in reviewed code.

**`@ts-ignore` without explanation.** `@ts-ignore` silently suppresses all errors on the next line and is invisible in diff review. Use `@ts-expect-error` instead — it requires a comment explaining the reason, and it errors when the suppression is no longer needed:

```ts
// @ts-expect-error: SomeLib types incorrectly narrow T to never — https://github.com/somelib/issue/1234
someLibFunction(value)
```

**Type assertions to bypass real validation.** `value as SpecificType` tells the compiler to trust you. It does not validate the value at runtime. A common incorrect pattern:

```ts
// Bad — no validation, runtime crash if shape is wrong
const project = (await response.json()) as Project

// Good — validates and provides a useful error message
const project = projectSchema.parse(await response.json())
```

Parse API responses with Zod. Use the generated SDK's typed service functions (which the SDK validates internally) rather than raw `fetch` + type assertion.

**The `Function` type.** `Function` is `any` for callables — accepts any signature, returns `any`. Use a concrete function type:

```ts
// Bad:  function invoke(fn: Function) { fn() }
// Good: function invoke(fn: () => void) { fn() }
```

**Non-null assertion `!` instead of narrowing.** `value!` suppresses `null | undefined` from the type with no runtime guard. If the assumption is wrong the code crashes. Use a guard or the nullish coalescing/optional chaining operators:

```ts
// Bad
const name = user!.displayName

// Good — guard
if (!user) throw new Error('user required')
const name = user.displayName

// Good — fallback
const name = user?.displayName ?? 'Anonymous'
```

Exception: test setup code (`beforeEach` declarations) where the assignment is structurally guaranteed. Keep `!` isolated to test files; do not let it appear in application code.

**Parallel interface duplication of generated types.** Writing a second `interface Project { ... }` that mirrors `src/shared/api/generated/types.gen.ts` creates two sources of truth that drift apart on every contract update. Compose from the generated type instead.

## Sources

- **TypeScript Handbook — Everyday Types:** https://www.typescriptlang.org/docs/handbook/2/everyday-types.html — *authoritative*
- **TypeScript TSConfig reference:** https://www.typescriptlang.org/tsconfig/ — *authoritative*
- **TypeScript 4.9 release notes (`satisfies` operator):** https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html — *authoritative*
- **TypeScript 5.0 release notes (const type parameters, decorator improvements):** https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-0.html — *authoritative*
- **Zod docs — Basics (type inference, `z.infer`, `z.input`, `z.output`):** https://zod.dev/basics — *authoritative*
- **@hey-api/openapi-ts — client docs:** https://heyapi.dev/openapi-ts/clients — *authoritative*
- **Total TypeScript — Matt Pocock's free tutorials on branded types and satisfies:** https://www.totaltypescript.com/tutorials — *community: Matt Pocock*

---

Last verified: 2026-05-04 (TypeScript 5.X / React 19 / Next.js 16.X).
