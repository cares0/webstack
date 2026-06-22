# Tailwind CSS v4

> Reference for build-fe SubAgent. Covers the CSS-first config introduced in Tailwind v4 (released January 2025) and how it differs from v3.

## What's new in v4

Tailwind v4 is a near-complete rewrite focused on simplification and speed:

- **CSS-first configuration.** Theme tokens, custom utilities, plugins, and content sources are declared in CSS via the `@theme`, `@utility`, `@plugin`, and `@source` directives. The previous `tailwind.config.js` is optional and most projects do not need one.
- **Lightning CSS engine.** Built on the Rust `lightningcss` parser (the same engine Vercel and Bun use). Cold builds are several times faster than v3's PostCSS pipeline; incremental builds are nearly instant.
- **No PostCSS dance.** A single `@import "tailwindcss";` replaces the v3 trio of `@tailwind base; @tailwind components; @tailwind utilities;`. Auto-content detection scans the project for class names without an explicit `content` array.
- **Native CSS variables.** Every theme token is exposed as a CSS custom property (e.g., `--color-primary`, `--font-sans`). You can read and override them at runtime — color modes, theming, A/B variants — without recompiling.
- **Container queries built in.** `@container` and `@max-*`, `@min-*` modifiers (`@container (min-width: 24rem) { ... }`, class `@lg:flex`) ship in core; no plugin needed.
- **Cascade layers** (`@layer base/components/utilities`) preserved, with v4 emitting them automatically so utilities always beat your component layer without `!important` games.

## v3 → v4 regression checklist (AI safety)

AI coding assistants (Cursor, Claude Code, Copilot, Codex) are trained predominantly on Tailwind v3 data. Tailwind has no official `llms.txt`, so v3 patterns appear frequently in AI-generated code and code reviews. The table below lists the most common regressions to catch.

| v3 (wrong in v4) | v4 (correct) |
|---|---|
| `@tailwind base; @tailwind components; @tailwind utilities;` | `@import "tailwindcss";` |
| `tailwind.config.js` with `theme.extend` | CSS-first config via `@theme {}` block in `globals.css` |
| `theme('colors.red.500')` in CSS | `var(--color-red-500)` or `theme(--color-red-500)` |
| `bg-opacity-50`, `text-opacity-25` | `bg-red-500/50`, `text-white/25` (slash notation) |
| `!flex`, `!bg-red-500` (leading `!`) | `flex!`, `bg-red-500!` (trailing `!`) |
| `bg-[--brand-color]` (bracket) | `bg-(--brand-color)` (parenthesis) |
| `grid-cols-[max-content,auto]` (commas) | `grid-cols-[max-content_auto]` (underscores) |
| `@layer utilities { .tab-4 { ... } }` | `@utility tab-4 { ... }` |
| `aspect-w-16 aspect-h-9` (plugin) | `aspect-[16/9]` or `aspect-video` (core) |
| `module.exports = { content: [...] }` | Auto-content detection — no explicit `content` array needed |
| `prose-lg` via plugin only | `@plugin "@tailwindcss/typography";` (v4-compatible version required) |
| `ring` (defaults to 3px, blue-500) | `ring-3 ring-blue-500` (defaults changed to 1px, currentColor) |
| `shadow-sm` / `shadow` | `shadow-xs` / `shadow-sm` (scale shifted by one step) |
| `rounded-sm` / `rounded` | `rounded-xs` / `rounded-sm` (scale shifted by one step) |
| `first:*:pt-0` (right-to-left stacking) | `*:first:pt-0` (left-to-right stacking) |

**Why this matters:** Tailwind has no official `llms.txt`. AI training data heavily over-represents v3 (released 2020, dominant for four years). Even when a model "knows" v4, it defaults to v3 patterns under token pressure.

**How to defend:**

- Include this table as a PR review checklist item for any CSS or className changes.
- `eslint-plugin-tailwindcss` does **not** yet fully support v4; manual review is the primary defence.
- The automated upgrade tool (`npx @tailwindcss/upgrade`) catches many regressions in existing code, but does not prevent new regressions introduced post-migration.

## Migration from v3

Most v3 → v4 work is removing files and updating imports.

In `globals.css`:

```css
/* v3 */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```css
/* v4 */
@import "tailwindcss";
```

Then move the contents of your former `theme.extend` into a `@theme {}` block (see below). Custom plugins move from JS to `@plugin` directives, or stay in `tailwind.config.js` if they need JS APIs the new system doesn't yet expose.

The official upgrade tool handles most of this:

```bash
npx @tailwindcss/upgrade@latest
```

PostCSS users replace `tailwindcss` with `@tailwindcss/postcss`; Vite users adopt `@tailwindcss/vite`; Next.js apps continue with the PostCSS plugin (configured automatically by `create-next-app`).

## CSS-first config (`@theme`)

In v4, the `@theme {}` block in your CSS file _is_ the config. No JavaScript file is needed for the common case. The following is the canonical webstack `@theme` block, derived from the design tokens emitted by `design-system-architect` into `.webstack/design-system/theme.css`:

```css
@import "tailwindcss";

/*
 * Source of truth: .webstack/design-system/theme.css
 * Do NOT edit this block directly — regenerate via design-system-architect (re-run init P3).
 */
@theme {
  /* Brand colors (OKLCH for wide-gamut displays) */
  --color-primary:            oklch(0.6  0.18 264);
  --color-primary-foreground: oklch(1    0    0);
  --color-secondary:          oklch(0.55 0.16 300);
  --color-accent:             oklch(0.78 0.16  30);
  --color-destructive:        oklch(0.65 0.22  27);
  --color-muted:              oklch(0.96 0.00   0);
  --color-muted-foreground:   oklch(0.45 0.00   0);

  /* Typography */
  --font-sans:  "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono:  "JetBrains Mono", ui-monospace, monospace;
  --font-serif: "Lora", ui-serif, Georgia, serif;

  /* Spacing extensions */
  --spacing-section: 6rem;
  --spacing-prose:   72ch;

  /* Border radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;

  /* Custom breakpoints */
  --breakpoint-3xl: 120rem;

  /* Motion */
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-expo:  cubic-bezier(0.7,  0, 0.84, 1);

  /* Container queries (custom named) */
  --container-xs: 20rem;
  --container-sm: 24rem;
}
```

Generated utilities from the above: `bg-primary`, `text-secondary`, `font-sans`, `font-serif`, `max-w-prose`, `gap-section`, `rounded-xl`, `min-3xl:px-12`, `ease-out-expo`, `@xs:flex`.

**`@theme` vs `@theme inline`:**

- Default `@theme` (build-time): Tailwind resolves variable values at build time and generates static utility CSS. Use this for most tokens.
- `@theme inline`: The generated utility references the CSS variable at _runtime_ rather than inlining its value. Needed when your token value is itself a CSS variable (e.g., `--font-sans: var(--font-inter)`), so that runtime overrides propagate correctly.

**Sanctioned ShadCN exception to "tokens only in `@theme`".** ShadCN's theming maps `@theme inline { --color-background: var(--background); … }` to a separate `:root { --background: …; } .dark { … }` block. This two-variable indirection is **deliberate and allowed** — it is what lets a `class="dark"` toggle swap the underlying `--background` at runtime while Tailwind utilities (`bg-background`) keep resolving through the `@theme inline` alias. It does **not** violate the duplicate-`:root` anti-pattern below, because the names differ: `@theme inline` declares `--color-*`, while `:root` declares the bare `--background`/`--foreground`/etc. that those aliases point at. See [`docs/frontend/shadcn-customization.md`](shadcn-customization.md) § "CSS variables theming".

**Token override semantics:**

- Adding tokens to `@theme {}` extends the defaults — existing Tailwind tokens are preserved.
- Redeclaring a namespace (`--color-*: initial;`) wipes that namespace and replaces it with only your values.
- Redeclaring individual tokens (e.g., `--breakpoint-sm: 30rem`) overrides that specific default.

**Design-system workflow cross-link:** The `/webstack:init` P4 step copies the `@theme {}` block from `.webstack/design-system/theme.css` into `src/app/globals.css`. To update brand tokens, edit the design-system source and re-run; do not manually edit the `@theme` block in `globals.css`.

## Tokens via CSS variables

When you declare a token in `@theme`, Tailwind does two things automatically:

1. Emits the token as a CSS custom property on `:root` (e.g., `--color-primary: oklch(...)`)
2. Generates all matching utility classes (e.g., `bg-primary`, `text-primary`, `ring-primary`, `shadow-primary`, `border-primary`)

**Using tokens beyond utilities:**

```css
/* Direct CSS variable reference — always available */
.hero {
  background-color: var(--color-primary);
  font-family: var(--font-sans);
  border-radius: var(--radius-lg);
}
```

**Custom tokens beyond Tailwind defaults:** Any token you add under a supported namespace gets a utility for free:

```css
@theme {
  --color-brand-teal: oklch(0.72 0.11 178);  /* → bg-brand-teal, text-brand-teal, … */
  --spacing-gutter:   1.5rem;                 /* → p-gutter, m-gutter, gap-gutter, … */
  --radius-pill:      999px;                  /* → rounded-pill */
}
```

**Anti-pattern — duplicate `:root` definition:**

```css
/* WRONG: collides with @theme output */
:root {
  --color-primary: #3b82f6;
}
@theme {
  --color-primary: oklch(0.6 0.18 264);
}
```

Defining the **same** variable in both `:root {}` and `@theme {}` creates a specificity conflict. The `:root` declaration and the `@theme`-emitted `:root` declaration occupy the same cascade layer; whichever appears last in the file wins, silently breaking the other. Keep brand tokens in `@theme`. (The ShadCN `@theme inline` + `:root` pattern is **not** this anti-pattern — it uses two _different_ variable names, `--color-*` aliasing the bare `--background`/etc.; see the sanctioned exception under [`@theme` vs `@theme inline`](#css-first-config-theme) above.)

## @theme directive

`@theme` is where the design system lives. Each entry maps a CSS custom property to a Tailwind token namespace. The namespace prefix (`--color-`, `--font-`, `--spacing-`, `--radius-`, `--breakpoint-`, `--ease-`, etc.) determines which utilities are generated.

```css
@import "tailwindcss";

@theme {
  --color-primary: oklch(0.6 0.18 264);
  --color-primary-foreground: oklch(1 0 0);
  --color-accent: oklch(0.78 0.16 30);

  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  --spacing-section: 6rem;

  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  --breakpoint-3xl: 120rem;

  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
}
```

This generates utilities like `bg-primary`, `text-primary-foreground`, `font-sans`, `gap-section`, `rounded-md`, `min-3xl:px-12`, `ease-out-expo`. To **override** a default token, redeclare it. To **extend** without losing defaults, the old `theme.extend` semantics are now the default — adding tokens does not erase Tailwind's built-ins; only redeclaring the namespace (`--color-*: initial;`) clears the slate.

In webstack: the design-system-architect emits `design-system/theme.css`. The `/webstack:init` P4 step copies its `@theme {}` block into the frontend repo's `globals.css` so brand tokens are the source of truth for both Tailwind utilities and ShadCN CSS variables (see `docs/frontend/shadcn-customization.md`).

## Custom utilities

Use `@utility` to define a single-class custom utility that participates in Tailwind's variant system (`hover:`, `md:`, `dark:`):

```css
@utility text-balance {
  text-wrap: balance;
}

@utility no-scrollbar {
  scrollbar-width: none;
  &::-webkit-scrollbar {
    display: none;
  }
}

@utility scroll-snap-x {
  scroll-snap-type: x mandatory;
}
```

Variants compose automatically: `md:text-balance`, `hover:no-scrollbar`. Multi-class shortcuts that don't need variant support are still better implemented as components (a React component or a `@apply` block) — see below.

## @apply policy

`@apply` still exists in v4 and is occasionally useful for legacy CSS or third-party widgets that can't accept className props. However, the recommended pattern is component extraction: a React component with class names directly in JSX is editable, statically analyzable, and avoids the indirection of CSS-class-aliases-to-CSS-classes.

webstack convention:

- **Avoid** `@apply` in component files; use Tailwind classes inline plus `cva` variants (see `docs/frontend/shadcn-customization.md`).
- **Acceptable** in `globals.css` for prose styling (`@layer base { h1 { @apply text-3xl font-bold; } }`) or for styling third-party HTML you can't otherwise control (e.g., a CMS-rendered article).
- Ban: writing dozens of `@apply` blocks to recreate components in CSS — that is the exact pattern v4 is trying to retire.

## Anti-patterns (expanded for v4)

The following patterns are either broken in v4, mislead AI tooling, or produce unnecessarily fragile code.

### 1. Using `@tailwind` directives (v3 entry point)

```css
/* WRONG — v3 only */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```css
/* CORRECT — v4 */
@import "tailwindcss";
```

### 2. Creating `tailwind.config.js` for theme tokens

```js
// WRONG — avoid for theme; keep only if a JS-API plugin requires it
module.exports = {
  theme: {
    extend: {
      colors: { brand: '#3b82f6' }
    }
  }
}
```

```css
/* CORRECT — CSS-first */
@theme {
  --color-brand: oklch(0.6 0.18 264);
}
```

If a third-party plugin genuinely requires a JS config, point to it explicitly via `@config "../../tailwind.config.js";` in CSS and keep only plugin entries in the file.

### 3. Using `theme()` in CSS to read color values

```css
/* WRONG — v3 function form; v4 changed the argument syntax */
.card {
  background-color: theme('colors.red.500');
}
```

```css
/* CORRECT — use the generated CSS variable directly */
.card {
  background-color: var(--color-red-500);
}
```

If you must use `theme()` (e.g., inside `@media`), use the v4 CSS variable name syntax: `theme(--breakpoint-xl)`.

### 4. `aspect-w-*` / `aspect-h-*` plugin classes

```html
<!-- WRONG — @tailwindcss/aspect-ratio plugin (v3) -->
<div class="aspect-w-16 aspect-h-9">...</div>
```

```html
<!-- CORRECT — built-in v4 core utilities -->
<div class="aspect-video">...</div>      <!-- 16/9 -->
<div class="aspect-square">...</div>     <!-- 1/1 -->
<div class="aspect-[4/3]">...</div>      <!-- arbitrary -->
```

Do not install `@tailwindcss/aspect-ratio` in a v4 project — it is redundant and may cause conflicts.

### 5. `@apply` overuse

```css
/* BAD — defeats the utility-first approach */
.btn-primary {
  @apply rounded-md bg-primary px-4 py-2 text-white font-semibold shadow-sm hover:bg-primary/90;
}
.btn-secondary {
  @apply rounded-md bg-secondary px-4 py-2 text-white ...;
}
```

```tsx
// GOOD — component extraction with cva
const button = cva("rounded-md px-4 py-2 font-semibold shadow-sm", {
  variants: {
    intent: {
      primary:   "bg-primary text-primary-foreground hover:bg-primary/90",
      secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/90",
    },
  },
});
```

`@apply` is still valid for `globals.css` base styles and for styling third-party HTML you cannot reach with className props. It should never be used to recreate component APIs in CSS.

### 6. Deprecated opacity utilities

```html
<!-- WRONG — removed in v4 -->
<div class="bg-black bg-opacity-50 text-white text-opacity-75"></div>
```

```html
<!-- CORRECT — slash notation -->
<div class="bg-black/50 text-white/75"></div>
```

### 7. Redefining design tokens in `:root` alongside `@theme`

See the _Anti-pattern_ note in the [Tokens via CSS variables](#tokens-via-css-variables) section above. Keep brand tokens in `@theme` — the only sanctioned `:root` companion is the ShadCN `@theme inline` aliasing pattern (different variable names), documented above.

## Plugins in v4

The plugin API was rewritten. Most popular plugins (`@tailwindcss/typography`, `@tailwindcss/forms`, `@tailwindcss/aspect-ratio`) shipped v4-compatible versions. Load them in CSS:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
@plugin "@tailwindcss/forms";
```

`@tailwindcss/aspect-ratio` is no longer needed — the `aspect-*` utilities are core. `tailwindcss-animate`, used heavily by older ShadCN setups, is replaced by built-in `tw-animate-css` patterns; new `npx shadcn init` outputs use the v4-native approach.

For custom plugins requiring JavaScript APIs (matchUtilities, addVariant), keep a `tailwind.config.js` with only the plugin entries; v4 reads it as a fallback.

## webstack convention

In every webstack-generated frontend repo:

- **Single CSS entrypoint:** `src/app/globals.css` contains `@import "tailwindcss"`, the `@theme {}` block (copied from `design-system/theme.css`), and any project-wide `@utility` definitions.
- **No `tailwind.config.js`** unless a third-party JS plugin demands it — keep the source of truth in CSS.
- **Theme tokens flow:** brand-identity-discovery → design-system-architect → `design-system/theme.css` → `globals.css`. Only modify the design-system source; do not edit `globals.css` directly except for utilities specific to the frontend.
- **Generated SDK files** under `src/shared/api/generated/` are excluded from Tailwind content scanning if they emit class strings (rare, but configure `@source not "src/shared/api/generated/**";` if needed).

## Sources

- **Tailwind CSS v4 docs:** https://tailwindcss.com/docs — _authoritative_
- **Tailwind v4 announcement:** https://tailwindcss.com/blog/tailwindcss-v4 — _authoritative_
- **Tailwind CSS v4 upgrade guide:** https://tailwindcss.com/docs/upgrade-guide — _authoritative_
- **Tailwind CSS v4 `@theme` reference:** https://tailwindcss.com/docs/theme — _authoritative_
- **Lightning CSS:** https://lightningcss.dev — _authoritative_
- **ofershap/tailwind-best-practices (v4 AI rules):** https://github.com/ofershap/tailwind-best-practices — _community: ofershap_

Last verified: 2026-06-22 (Tailwind v4.x stable).
