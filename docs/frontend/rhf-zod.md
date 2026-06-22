# React Hook Form + Zod

> Reference for build-fe SubAgent. Covers form patterns using react-hook-form, Zod schema validation, and the ShadCN form integration.

## Why RHF + Zod

`react-hook-form` is uncontrolled-by-default: inputs register themselves and the form state lives in refs, not React state. The result is fewer re-renders (typing in field A does not re-render field B), small bundle (~9 KB), and no controlled-input boilerplate. It pairs well with React 18's concurrent features because it minimizes work during keystrokes.

`zod` provides TypeScript-first schema declaration with both compile-time inference and runtime validation. A Zod schema is the single source of truth: the inferred type drives `useForm<Schema>`, the parser validates user input, the same schema runs server-side, and OpenAPI generators can emit Zod schemas for response/request types.

The bridge is `@hookform/resolvers/zod`, which adapts a Zod schema to RHF's resolver API so RHF's error state mirrors the schema's parse failures with the right field paths.

## Setup

Install the runtime dependencies. Pin Zod to v4 (the current stable major); `@hookform/resolvers/zod` works against both v3 and v4 with the same import.

```bash
pnpm add react-hook-form 'zod@^4' @hookform/resolvers
```

ShadCN's form generator wires the integration:

```bash
npx shadcn@latest add form input label textarea select
```

This drops `src/shared/ui/form.tsx` (a thin RHF + Radix Label wrapper — the path comes from webstack's `components.json` aliases override) and the related primitives into your repo.

## Schema-first pattern

Define the schema first, then derive the type from it. Never declare a separate TypeScript interface — they will drift.

```ts
// src/features/create-project/model/schema.ts
import { z } from 'zod';

export const ProjectFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(80),
  slug: z.string().regex(/^[a-z0-9-]+$/, 'Lowercase, numbers, dashes only'),
  description: z.string().max(500).optional(),
  visibility: z.enum(['public', 'private']),
  tagIds: z.array(z.uuid()).default([]),   // Zod v4 top-level; z.string().uuid() is deprecated
});

export type ProjectFormValues = z.infer<typeof ProjectFormSchema>;
```

`z.infer<typeof Schema>` produces a TypeScript type that exactly matches what `parse()` returns at runtime. Optional fields become `string | undefined`; defaults become required (after parse, `tagIds` is guaranteed `string[]`).

## Form structure

ShadCN's form components compose with RHF's `useForm` and `Controller` to produce accessible markup with labels, descriptions, and error messages auto-wired. A typical form:

```tsx
'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/shared/ui/form';
import { Input } from '@/shared/ui/input';
import { Textarea } from '@/shared/ui/textarea';
import { Button } from '@/shared/ui/button';
import { ProjectFormSchema, type ProjectFormValues } from '../model/schema';

export function ProjectForm({ onSubmit }: { onSubmit: (values: ProjectFormValues) => Promise<void> }) {
  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(ProjectFormSchema),
    defaultValues: { name: '', slug: '', description: '', visibility: 'private', tagIds: [] },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input placeholder="Acme launch" {...field} />
              </FormControl>
              <FormDescription>Visible to all team members.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea rows={4} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? 'Saving…' : 'Save'}
        </Button>
      </form>
    </Form>
  );
}
```

`FormField` is a typed wrapper over RHF's `Controller`. `FormMessage` reads from the resolver's error path and renders nothing when the field is valid. `FormLabel` automatically associates with the input via `htmlFor` / `aria-describedby`.

## Server-side validation consistency

Client-side Zod is **advisory** — anyone can call the endpoint with crafted payloads, so validation must also run authoritatively on the server. In webstack the server is the separate Spring backend: the form's `onSubmit` calls the generated SDK (FE → SDK → Spring) via a TanStack `useMutation`, and Spring re-validates against the OpenAPI contract. Backend mutations do **not** go through a Next.js Server Action.

```tsx
// src/features/create-project/api/mutations.ts
'use client';

import { useMutation } from '@tanstack/react-query';
import { ProjectsService } from '@/shared/api/generated';
import { ProjectFormSchema, type ProjectFormValues } from '../model/schema';

export function useCreateProject() {
  return useMutation({
    // client-side parse for instant feedback; Spring is the authoritative validator
    mutationFn: (values: ProjectFormValues) =>
      ProjectsService.createProject({ body: ProjectFormSchema.parse(values) }),
  });
}
```

The frontend's Zod schema mirrors the OpenAPI contract that the backend enforces (the `code-reviewer` SubAgent verifies request bodies match). If the OpenAPI emits matching Zod via `@hey-api/openapi-ts`, prefer the generated schema and only hand-author when generation is insufficient.

## Async submit + SDK mutation

`form.handleSubmit` accepts an async function. RHF tracks `formState.isSubmitting` automatically. Call the mutation's `mutateAsync` (from the `useCreateProject` hook above) so a rejected SDK call maps to RHF error state:

```tsx
const { mutateAsync: createProject } = useCreateProject();

const onSubmit = async (values: ProjectFormValues) => {
  try {
    await createProject(values);
    form.reset();
  } catch (e) {
    if (e instanceof ServerError) {
      form.setError('root.serverError', { message: e.message });
    }
  }
};
```

Use `form.setError('<fieldName>')` to surface server-returned validation errors against specific fields. Use `form.setError('root.<key>')` for cross-cutting errors (network, auth) that don't map to a single field.

## Common patterns

**Required vs optional**: a Zod field is required by default. `.optional()` allows `undefined`; `.nullable()` allows `null`; `.optional().default('foo')` makes it optional in input and guaranteed in output.

**Conditional fields (refinement)**: when one field's validity depends on another:

```ts
const Schema = z
  .object({
    plan: z.enum(['free', 'pro']),
    seats: z.number().int().min(1),
  })
  .superRefine((data, ctx) => {
    if (data.plan === 'free' && data.seats > 5) {
      // verify the addIssue shape against pinned Zod v4 — v4 also offers `.check()` as the newer form
      ctx.addIssue({ code: 'custom', path: ['seats'], message: 'Free plan allows up to 5 seats' });
    }
  });
```

**Array fields (FieldArray)**: use RHF's `useFieldArray` for dynamic lists.

```tsx
const { fields, append, remove } = useFieldArray({ control: form.control, name: 'members' });
fields.map((field, index) => (
  <FormField key={field.id} name={`members.${index}.email`} ... />
));
```

**File upload**: `<Input type="file" />` exposes a `FileList`. Zod can validate via `z.instanceof(FileList).refine(files => files[0]?.size < 5_000_000)`. Hold the `FileList` as form state and serialize on submit (FormData or upload URL).

## Errors

Zod errors → resolver maps them to RHF's `errors` object → `FormMessage` reads `formState.errors[fieldName]` and renders `error.message`. The mapping is path-based: a Zod error at path `['address', 'city']` lands as `errors.address?.city`.

For a global error block (not tied to one field):

```tsx
{form.formState.errors.root?.serverError && (
  <p className="text-destructive">{form.formState.errors.root.serverError.message}</p>
)}
```

Customize default Zod messages on the schema itself rather than rewriting them in `FormMessage` — the schema is the source of truth for validation copy, including for backend reuse.

## webstack convention

webstack uses FSD-lite (see `docs/frontend/fsd-architecture.md`); RHF + Zod placement maps to layers:

- **One schema per feature slice**: `src/features/<feature>/model/schema.ts` exports the Zod schemas and inferred types. Both the form component (`src/features/<feature>/ui/<Form>.tsx`) and the TanStack mutation (`src/features/<feature>/api/mutations.ts`) import from it — as does any FE-only Server Action, on the rare paths that use one.
- **ShadCN form primitives** are imported from `@/shared/ui/form`, `@/shared/ui/input`, etc.
- **Generated SDK schemas first**: if `@hey-api/openapi-ts` emits a Zod schema for the request body, import it from `@/shared/api/generated` and use it as the form's resolver schema. Hand-author only when the form needs additional client-only fields (e.g., a confirmation toggle) — extend with `Schema.extend({ confirm: z.literal(true) })`.
- **Server Action vs SDK call**: form submissions targeting backend domain operations call the generated SDK from inside `onSubmit` (with TanStack Query mutations under `src/features/<feature>/api/mutations.ts` — see `docs/frontend/tanstack-query.md`). Use Server Actions (`src/features/<feature>/api/actions.ts`) for forms whose persistence is FE-only (e.g., NextAuth profile edits).
- **No two error message strings**: error copy lives in the Zod schema. The form components never hardcode validation messages.

## Sources

For complex form patterns (multi-step, file upload, optimistic UI, Server Action ↔ RHF), see `docs/frontend/form-patterns.md`.

- React Hook Form: https://react-hook-form.com/docs
- Zod: https://zod.dev
- Zod v4 release notes: https://zod.dev/v4
- @hookform/resolvers: https://react-hook-form.com/get-started#SchemaValidation
- ShadCN form component: https://ui.shadcn.com/docs/components/form

Last verified: 2026-06-22 (Zod v4 stable; v3 still receives security fixes — webstack defaults to v4).
