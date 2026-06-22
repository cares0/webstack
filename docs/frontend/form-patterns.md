# Form patterns

> Reference for build-fe SubAgent and frontend-implementer.
> Complex form patterns beyond rhf-zod basics: multi-step, file upload, optimistic UI, Server Action integration.

## What is form complexity in webstack

`docs/frontend/rhf-zod.md` covers the foundation: schema-first Zod, `useForm` + `zodResolver`, ShadCN `FormField`/`FormMessage`, and single-step Server Action submission. Read it first; this document covers what comes next.

Patterns addressed here: multi-step wizards, dynamic field arrays, binary file uploads via presigned URL, TanStack Query optimistic mutations, and bridging RHF with Next.js Server Action `FormData` pipelines. Stack: **Next.js 16**, **React 19**, **RHF 7.X**, **Zod 4.X**, **TanStack Query 5.X**, **Zustand 5.X**, **ShadCN/Radix**.

## Why patterns matter

**UX.** Multi-step forms that lose data on back-navigation or uploads with no progress indicator cause abandonment. Patterns encode the UX contract into implementation constraints.

**Accessibility.** WCAG 2.2 requires errors associated with fields (`aria-describedby`), predictable focus on step transitions, and async state communicated via `aria-live`.

**Data consistency.** Optimistic updates and concurrent submissions can corrupt server state without rollback, idempotency keys, and server-side re-validation.

**Concurrency.** React 19 concurrent rendering and TanStack Query background refetch cause mutations to race. The `onMutate`/`onError`/`onSettled` triple is the coordination boundary.

## Multi-step forms

A multi-step form is a single logical form split across sequential steps.

### Short wizard: single RHF instance

For 2–3 steps with few fields, hold one `useForm` instance and gate transitions with `form.trigger`:

```tsx
'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { WizardSchema, type WizardValues } from '../model/schema'

const STEP_FIELDS: Record<number, (keyof WizardValues)[]> = { 1: ['name', 'plan'], 2: ['seats', 'billingEmail'] }

export function ProjectWizard() {
  const [step, setStep] = useState(1)
  const form = useForm<WizardValues>({
    resolver: zodResolver(WizardSchema),
    defaultValues: { name: '', plan: 'free', seats: 1, billingEmail: '' },
    mode: 'onTouched',
  })
  const goNext = async () => { if (await form.trigger(STEP_FIELDS[step])) setStep((s) => s + 1) }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)}>
      {step === 1 && <StepOne form={form} />}
      {step === 2 && <StepTwo form={form} />}
      {step === 3 && <StepReview form={form} />}
      <nav>
        {step > 1 && <button type="button" onClick={() => setStep((s) => s - 1)}>Back</button>}
        {step < 3 && <button type="button" onClick={goNext}>Next</button>}
        {step === 3 && <button type="submit" disabled={form.formState.isSubmitting}>Submit</button>}
      </nav>
    </form>
  )
}
```

`form.trigger(fields)` validates a named subset and returns `true` only when all pass. The single `useForm` instance accumulates values in RHF's internal refs across all steps. Pass `form` to each step component so `FormField` children share the same `control`.

For accessibility, move focus to the step container (`tabIndex={-1}`, `role="group"`) on transition using a `useEffect` + `useRef`.

### Long wizard: Zustand store

For 4+ steps, field arrays, or resume-after-navigation, move accumulated data into a Zustand feature store. Shape: `step: number` + one data slice per step + patch actions + `reset`. Use `devtools(persist(immer(...)))` so drafts survive page reloads. Seed `defaultValues` from the store at each step; flush the full store to the Server Action on final submission; call `reset()` on success.

See `docs/frontend/client-state.md` for the full store pattern, `persist` stacking rules, and hydration mismatch handling.

### Partial schema per step

Define sub-schemas per step and merge for final submission. Pass each sub-schema to that step's `zodResolver`; the final step validates the merged schema:

```typescript
const StepOneSchema = z.object({ name: z.string().min(1), plan: z.enum(['free', 'pro']) })
const StepTwoSchema = z.object({ seats: z.number().int().min(1), billingEmail: z.email() })
// Zod v4: .merge() is removed — use .extend() (or spread the .shape)
export const WizardSchema = StepOneSchema.extend(StepTwoSchema.shape)
```

## Dynamic field arrays

`useFieldArray` manages repeating field groups — members, line items, tags — that the user adds and removes at runtime.

```tsx
'use client'

import { useForm, useFieldArray } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Form, FormField, FormItem, FormControl, FormMessage } from '@/shared/ui/form'
import { Input } from '@/shared/ui/input'
import { Button } from '@/shared/ui/button'

const Schema = z.object({ members: z.array(z.object({ email: z.email() })).min(1) })

export function InviteForm() {
  const form = useForm({ resolver: zodResolver(Schema), defaultValues: { members: [{ email: '' }] } })
  const { fields, append, remove } = useFieldArray({ control: form.control, name: 'members' })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {fields.map((field, index) => (
          <div key={field.id} className="flex gap-2">    {/* key=field.id, never index */}
            <FormField control={form.control} name={`members.${index}.email`}
              render={({ field: f }) => (
                <FormItem className="flex-1">
                  <FormControl><Input {...f} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />
            <Button type="button" onClick={() => remove(index)} aria-label={`Remove ${index + 1}`}>×</Button>
          </div>
        ))}
        <Button type="button" onClick={() => append({ email: '' })}>Add</Button>
        <Button type="submit" disabled={form.formState.isSubmitting}>Send</Button>
      </form>
    </Form>
  )
}
```

**Key stability.** Always use `field.id` as the React `key` — never the array index. Index keys cause React to reuse wrong DOM nodes when rows are removed mid-list, breaking focus and error state.

**Available mutations.** `append`, `prepend`, `insert`, `remove`, `swap`, `move`, `replace`. Use `replace` to overwrite all rows atomically from a server-returned array.

**Performance.** For lists over ~50 rows set `mode: 'onBlur'` to avoid synchronous Zod parsing on every keystroke. For hundreds of rows consider `@tanstack/react-virtual` with individually registered fields.

## File uploads

`FileList` is not JSON-serializable; binary data must not travel through a Server Action (payload size limits, unnecessary server egress). Use the presigned URL pattern.

### Three-step flow

1. **Request a presigned URL** — the backend issues a short-lived signed PUT URL for OCI Object Storage / S3-compat, scoped to `contentType` and `sizeBytes`.
2. **PUT the file directly** from the browser. Next.js is not in the data path.
3. **Submit the `objectKey`** (not the binary) via the form. The backend stores the key and validates server-side.

```tsx
// AvatarUploadField.tsx  ('use client')
export function AvatarUploadField({ onUploadComplete }: { onUploadComplete: (key: string) => void }) {
  const [progress, setProgress] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { mutate: upload, isPending } = useMutation({
    mutationFn: async (file: File) => {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
        throw new Error('Only JPEG, PNG, WebP allowed.')
      if (file.size > 5_000_000) throw new Error('Exceeds 5 MB.')
      const { presignedUrl, objectKey } = await profileApi.getAvatarUploadUrl({
        body: { contentType: file.type, sizeBytes: file.size },
      })
      // fetch() has no upload progress event — use XHR
      await new Promise<void>((res, rej) => {
        const xhr = new XMLHttpRequest()
        xhr.upload.onprogress = (e) => e.lengthComputable &&
          setProgress(Math.round(e.loaded / e.total * 100))
        xhr.onload = () => (xhr.status < 300 ? res() : rej(new Error('Upload failed')))
        xhr.onerror = () => rej(new Error('Network error'))
        xhr.open('PUT', presignedUrl); xhr.setRequestHeader('Content-Type', file.type); xhr.send(file)

      })
      return objectKey
    },
    onSuccess: (key) => { setProgress(null); onUploadComplete(key) },
    onError: (e: Error) => { setProgress(null); setErr(e.message) },
  })

  return (
    <div className="space-y-2">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
        onChange={(e) => { setErr(null); const f = e.target.files?.[0]; if (f) upload(f) }} />
      <button type="button" onClick={() => inputRef.current?.click()} disabled={isPending}>
        {isPending ? `Uploading… ${progress ?? 0}%` : 'Choose file'}
      </button>
      {progress !== null && <progress value={progress} max={100} aria-label="Upload progress" className="w-full" />}
      {err && <p role="alert" className="text-destructive text-sm">{err}</p>}
    </div>
  )
}
```

Wire: `form.setValue('avatarObjectKey', objectKey)` in the parent RHF form.

**Retry.** Do not set `retry: true` — a failed presigned PUT may have consumed the URL. Show a manual retry button; obtain a fresh presigned URL on each attempt.

**Server-side enforcement.** `file.type` is advisory and can be spoofed. The backend must re-verify content type from object storage metadata, enforce size at the storage policy level, and run virus scanning where the risk profile requires it.

## Optimistic UI

Optimistic updates apply a mutation to local UI immediately; on error the change rolls back.

### TanStack Query cache pattern

```tsx
export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { title: string; projectId: string }) => tasksApi.createTask({ body: data }),
    onMutate: async (t) => {
      await qc.cancelQueries({ queryKey: ['tasks', t.projectId] })
      const previous = qc.getQueryData<Task[]>(['tasks', t.projectId])
      qc.setQueryData<Task[]>(['tasks', t.projectId], (old = []) => [
        ...old, { id: `opt-${Date.now()}`, ...t, status: 'todo', _optimistic: true } as Task,
      ])
      return { previous, projectId: t.projectId }
    },
    onError: (_e, _t, ctx) => { if (ctx?.previous) qc.setQueryData(['tasks', ctx.projectId], ctx.previous) },
    onSettled: (_d, _e, vars) => qc.invalidateQueries({ queryKey: ['tasks', vars.projectId] }),
  })
}
```

The three-hook triple is required: `onMutate` snapshots and patches; `onError` rolls back; `onSettled` invalidates to converge with server truth. Mark optimistic entries with `_optimistic: true` so the UI can dim unconfirmed items.

**Idempotency keys.** For mutations that must not apply twice (charges, emails, state transitions), include `idempotencyKey: crypto.randomUUID()` in the request body. The backend deduplicates on the key. Reference: backend idempotency patterns (covered in `docs/backend/api-versioning.md` and `docs/cross-cutting/rest-api-design.md`).

**Simple case.** When only one component needs the optimistic value, skip cache manipulation and read from `variables` on the pending mutation: `const display = isPending ? [...items, { ...variables, _optimistic: true }] : items`.

## Server Action ↔ RHF

> **Scope (canon).** webstack routes **backend** mutations through the generated SDK + TanStack `useMutation` (FE → SDK → Spring), not Server Actions — see [`docs/frontend/tanstack-query.md`](tanstack-query.md). The `useActionState` and `startTransition` patterns below are for **FE-only** form persistence (e.g., NextAuth profile edits); `userService`/`createProject` here stand in for that FE-only path, not a Spring domain call.

### useActionState (React 19)

`useActionState` from `'react'` replaces React 18's `useFormState` from `'react-dom'`. Do not use `useFormState` in new code. Return signature: `[state, formAction, isPending]`.

```tsx
// SignupForm.tsx  'use client'
import { useActionState } from 'react'   // React 19: import from 'react', NOT 'react-dom'

export function SignupForm() {
  const [state, formAction, isPending] = useActionState(createUser, { errors: {}, message: null })
  return (
    <form action={formAction}>
      <input type="email" id="email" name="email" required />
      {state.errors?.email && <p role="alert" aria-live="polite">{state.errors.email[0]}</p>}
      {state.message && <p role="alert">{state.message}</p>}
      <button type="submit" disabled={isPending}>{isPending ? 'Creating…' : 'Sign up'}</button>
    </form>
  )
}

// actions.ts  'use server'
type State = { errors: Record<string, string[]>; message: string | null }

export async function createUser(prevState: State, formData: FormData): Promise<State> {
  const result = SignupSchema.safeParse(Object.fromEntries(formData))
  if (!result.success) return { errors: result.error.flatten().fieldErrors, message: null }
  try { await userService.create(result.data); return { errors: {}, message: 'Account created.' } }
  catch { return { errors: {}, message: 'Something went wrong.' } }
}
```

Rules: `safeParse` (not `parse`) to return typed error state. `formData.getAll('field')` for multi-value fields. Always re-validate server-side — the action is a public endpoint.

### RHF + Server Action hybrid

When a form needs RHF's controlled validation alongside a Server Action, bridge via `startTransition`. Call the action from `form.handleSubmit` and map returned server errors back into RHF's field state with `form.setError`:

```tsx
const [isPending, startTransition] = useTransition()
const onSubmit = (values: ProjectValues) => {
  startTransition(async () => {
    const result = await createProject(values)   // typed values — no FormData needed
    if (result.errors)
      Object.entries(result.errors).forEach(([f, msgs]) =>
        form.setError(f as keyof ProjectValues, { message: msgs[0] }))
  })
}
```

## ShadCN MCP integration

The ShadCN MCP server bridges the AI agent, the ShadCN registry, and the `shadcn` CLI. Use it for `Form`, `Dialog`, `Sheet`, `Combobox`, and `DatePicker` rather than running CLI commands manually.

**Setup** (once per project): `pnpm dlx shadcn@latest mcp init --client claude`. This writes `.mcp.json` pointing to `npx shadcn@latest mcp`.

**Agent invocation (G1).** Instruct conversationally: "Add the form, dialog, and sheet components from the ShadCN registry." The agent runs the equivalent of `npx shadcn@latest add form dialog sheet`. Components land in `src/shared/ui/` per webstack's `components.json` aliases.

**Custom registries.** Declare under `registries` in `components.json` (e.g. `"@acme": "https://registry.acme.com/{name}.json"`), then: "Add the @acme/data-table component."

## Draft / partial save

Long forms need anti-loss UX. Create a draft store at `src/features/<feature>/model/draft-store.ts` with `draft: T | null`, `saveDraft(d)`, and `clearDraft()` using `devtools(persist(immer(...)))`.

Seed RHF `defaultValues` from `draft` on mount. Subscribe via `form.watch((v) => saveDraft(v))` for auto-save (debounce in production). Call `clearDraft()` on successful submit.

On return, show a recovery banner (`role="status"`, Restore / Discard) rather than silently restoring. Only persist JSON-safe values — no tokens, binary data, or `FileList` objects.

## Anti-patterns

**Client-only validation.** Trusting client Zod in the Server Action is a security defect — any caller bypasses the browser. Always `safeParse` in the action.

**`useFieldArray` with index keys.** Index keys break focus and error state on mid-list removal. Always use `field.id`.

**Optimistic update without rollback.** `onMutate` without `onError` rollback leaves the UI inconsistent on rejection. The `onMutate`/`onError`/`onSettled` triple is required.

**Binary upload through a Server Action body.** Hits payload size limits and routes bytes through the Next.js server. Use the presigned URL pattern.

**File upload without server-side validation.** `file.type` is advisory and spoofable. The backend must validate actual file content.

**`FileList` or `File` in Zustand across navigations.** `FileList` does not survive `localStorage` serialisation. Hold it in `useRef`/`useState` only for the upload duration.

**Missing step gating.** Advancing without `form.trigger(STEP_FIELDS[step])` silently accumulates invalid data. Gate every step transition.

**`useFormState` from `'react-dom'` (React 18).** Deprecated in React 19. Use `useActionState` from `'react'`. Return adds `isPending` as third element: `[state, action, isPending]`.

## Sources

- **React Hook Form — useFieldArray:** https://react-hook-form.com/docs/usefieldarray — _authoritative_
- **React Hook Form — formState:** https://react-hook-form.com/docs/useform/formstate — _authoritative_
- **TanStack Query v5 — Optimistic Updates:** https://tanstack.com/query/v5/docs/framework/react/guides/optimistic-updates — _authoritative_
- **Next.js 16 — Forms guide (useActionState + Server Actions):** https://nextjs.org/docs/app/guides/forms — _authoritative_
- **ShadCN MCP server:** https://ui.shadcn.com/docs/mcp — _authoritative_
- **ShadCN Form component:** https://ui.shadcn.com/docs/components/form — _authoritative_
- **React 19 — useActionState:** https://react.dev/reference/react/useActionState — _authoritative_
- **TkDodo — Practical React Query (optimistic updates patterns):** https://tkdodo.eu/blog/practical-react-query — _community: TanStack Query maintainer_
- **react-hook-form/examples (multi-step + dynamic arrays):** https://github.com/react-hook-form/react-hook-form/tree/master/examples — _community: RHF maintainers (open examples)_

Last verified: 2026-06-22 (RHF 7.X / TanStack Query 5.X / Next.js 16.X / React 19 / Zod 4.X).
