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

- Tailwind v4 docs: https://tailwindcss.com/docs
- Tailwind v4 announcement: https://tailwindcss.com/blog/tailwindcss-v4
- Migration guide: https://tailwindcss.com/docs/upgrade-guide
- Lightning CSS: https://lightningcss.dev

Last verified: 2026-04-26 (Tailwind v4.x stable).
