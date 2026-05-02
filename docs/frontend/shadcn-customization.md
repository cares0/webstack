# ShadCN Customization

> Reference for design-system-architect SubAgent and build-fe. Covers ShadCN UI install, theme.css mapping, components.json schema, cva variants, and Radix composition.

## What ShadCN is (and isn't)

ShadCN UI is **not** a component library you install from npm. It is a CLI that copies pre-built React component source code (built on Radix primitives + Tailwind utility classes) into your repo. After install, the components live under whatever path the `components.json` `aliases.ui` field points to — webstack's convention is `src/shared/ui/` (the FSD-lite `shared` layer; the ShadCN default `src/components/ui/` is overridden in init). You own the files: edit, delete, restyle freely. There is no version lockstep with an upstream package; the "library" is whatever you copied at the time you ran the CLI.

This trade-off matters for webstack:

- **Pro**: every visual decision (radius, color, spacing, typography) is editable. The design-system-architect SubAgent can rewrite `theme.css` and `components/ui/*.tsx` to match the brand identity without monkey-patching a vendor package.
- **Pro**: zero runtime overhead from a wrapper layer; the components compile down to plain JSX + Tailwind classes.
- **Con**: no automatic updates. When ShadCN ships a fix, you re-run `npx shadcn add <component>` and reconcile manually.

ShadCN supplies the structural skeleton; brand identity is layered via `theme.css` (CSS variables) and per-component `cva` variants.

## Initial setup

In a fresh Next.js + Tailwind v4 repo:

```bash
npx shadcn@latest init
```

The CLI prompts for style, base color, CSS variables vs Tailwind classes, and component path aliases, then creates:

- `components.json` — the schema-driven config (see below).
- `src/lib/utils.ts` — exports `cn()` (a `clsx` + `tailwind-merge` wrapper).
- `src/app/globals.css` (or your designated CSS entry) — adds `:root` and `.dark` CSS variable blocks.
- Updates `tsconfig.json` aliases.

In webstack-generated repos, the `/webstack:init` P4 step runs `init` non-interactively and then writes the project-specific `theme.css` from the design-system output, replacing the default tokens.

## components.json

This file is read every time the CLI generates a component. Fields:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/app/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/shared/ui",
    "utils": "@/shared/lib/utils",
    "ui": "@/shared/ui",
    "lib": "@/shared/lib",
    "hooks": "@/shared/hooks"
  }
}
```

**webstack note**: the aliases above point at `src/shared/...` because webstack's FSD-lite layer system places ShadCN primitives in the FSD `shared` layer (see `docs/frontend/fsd-architecture.md`). If you generate this `components.json` via `npx shadcn init`, override the prompts to use these aliases (or edit the file after init). The `components` alias and `ui` alias both target `@/shared/ui` — `npx shadcn add` writes new primitives to `src/shared/ui/`.

- `style`: `new-york` is the modern default (sharper edges, denser); `default` is the legacy v1 style and rarely picked for new projects. Pick one and lock it.
- `rsc: true`: emits Server-Component-aware files (no top-of-file `'use client'` unless required).
- `tailwind.css`: path to the global CSS file where variables are written.
- `tailwind.cssVariables: true`: variants reference `bg-primary`, `text-foreground` (mapped to CSS vars). Setting `false` would inline color values into Tailwind classes — webstack uses `true` so the design-system can swap themes.
- `tailwind.config: ""`: empty for Tailwind v4 (CSS-first config; see `docs/frontend/tailwind-v4.md`).
- `aliases`: must match `tsconfig.json` `paths`.

## CSS variables theming

ShadCN components reference Tailwind utility classes that resolve through CSS custom properties. Tailwind v4's `@theme` directive (in `globals.css`) wires variable names to Tailwind tokens:

```css
@import "tailwindcss";

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --radius: var(--radius);
}

:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --radius: 0.625rem;
}

.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --primary: oklch(0.985 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
}
```

ShadCN's recent generator emits `oklch()` values; older repos may have HSL. The format is interchangeable as long as the same color space is used consistently. Per-mode toggles are a `class="dark"` on `<html>` or `<body>` driven by `next-themes`.

In webstack: the design-system-architect produces `design-system/theme.css` with brand-specific values. `/webstack:init` P4 copies that file content into the frontend repo's `globals.css` `:root` and `.dark` blocks.

## Variants via cva

`class-variance-authority` (cva) is the convention for typed, multi-variant component classes. A typical Button:

```tsx
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3',
        lg: 'h-10 rounded-md px-8',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
```

`VariantProps` derives the prop types from the cva config — adding a new variant key updates the type automatically. Always end with `cn(... className)` so consumers can override.

## Adding new components

```bash
npx shadcn@latest add button card dialog input form
```

Each component lands under the path declared in `components.json` `aliases.ui` — webstack's `src/shared/ui/`. The CLI also installs any required deps (e.g., `@radix-ui/react-dialog`, `@hookform/resolvers`). Once the file is in your repo, treat it as your code: edit the `cva` config, swap Radix primitives, restyle freely. Re-running `add` for the same component will prompt to overwrite, so back up local edits first.

## Custom variants per webstack identity

The design-system-architect SubAgent emits `design-system/component-variants.md` (and a JSON sibling) describing brand-specific variants beyond ShadCN defaults — e.g., a `tonal` button, a `compact` card, a destructive-but-quiet alert. The build-fe SubAgent extends the corresponding `cva` block in `src/shared/ui/<component>.tsx`:

```tsx
const buttonVariants = cva('...', {
  variants: {
    variant: {
      default: '...',
      // existing ShadCN variants...
      tonal: 'bg-primary/10 text-primary hover:bg-primary/15', // webstack-added
    },
  },
});
```

Brand variants live alongside defaults; never fork the file or wrap it. The single `cva` config is the source of truth.

## Composition with Radix

ShadCN's interactive components (Dialog, DropdownMenu, Tooltip, Popover, Select, Combobox, ContextMenu, etc.) wrap Radix primitives. A `<Dialog>` is `Dialog.Root` + `Dialog.Trigger` + `Dialog.Content` re-exported with default styling. To extend:

```tsx
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Dialog, DialogContent, DialogTrigger } from '@/shared/ui/dialog';

// Add a left-anchored variant by overriding DialogContent's positioning
export function DialogSheetContent({ children, ...props }: DialogPrimitive.DialogContentProps) {
  return (
    <DialogContent className="left-0 top-0 h-screen w-96 translate-x-0 translate-y-0 rounded-none" {...props}>
      {children}
    </DialogContent>
  );
}
```

When ShadCN doesn't ship a primitive you need (e.g., `@radix-ui/react-toggle-group`), install it directly and wrap with the same `cva` + `cn` pattern. Stay inside the Radix ecosystem for accessibility and keyboard semantics; rebuilding focus-trap / Esc-to-close from scratch leads to subtle a11y bugs.

## webstack convention

webstack frontends use FSD-lite (see `docs/frontend/fsd-architecture.md`); ShadCN integration follows the layer placement:

- All ShadCN-generated UI primitives live at `src/shared/ui/`. (`components.json` aliases `ui` and `components` both point to `@/shared/ui`.)
- Composite UI for a domain entity (e.g., `<ProjectCard>`) lives at `src/entities/<entity>/ui/` and imports primitives from `@/shared/ui`.
- Composite UI for a user action / feature (e.g., `<CreateProjectForm>`) lives at `src/features/<feature>/ui/` and imports both primitives from `@/shared/ui` and entity components from `@/entities/<entity>` as needed.
- Page-level chrome (header, sidebar, dashboard layout) lives at `src/widgets/<widget>/`.
- The OpenAPI-generated TypeScript SDK lives at `src/shared/api/generated/` and is gitignored or marked generated; design-system-architect and code-reviewer skip it.
- `theme.css` and any custom `cva` extensions are tracked under `src/app/globals.css` and `src/shared/ui/<component>.tsx` respectively; never duplicated.
- When ShadCN ships an upstream improvement to a component already vendored, the build-fe SubAgent regenerates the file at `src/shared/ui/<component>.tsx`, then re-applies webstack-specific cva variants from `design-system/component-variants.md`.

## Sources

- ShadCN UI docs: https://ui.shadcn.com/docs
- ShadCN theming: https://ui.shadcn.com/docs/theming
- class-variance-authority: https://cva.style/docs
- Radix UI primitives: https://www.radix-ui.com/primitives

Last verified: 2026-04-26 (ShadCN CLI 2.x stable, "new-york" default style, OKLCH color tokens).
