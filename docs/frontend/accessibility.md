# Frontend accessibility (WCAG 2.2 AA)

> Reference for build-fe SubAgent and frontend-implementer.
> WCAG 2.2 AA baseline, ShadCN/Radix patterns, RHF a11y wiring, and automated axe testing for webstack's Next.js 16 + RSC + ShadCN/Radix + RHF stack.

## What is webstack a11y

webstack frontends target **WCAG 2.2 AA** conformance as the production baseline. WCAG 2.2 (October 2023) supersedes 2.1 with nine new success criteria covering mobile accessibility, cognitive accessibility, and pointer input.

The stack is built on **ShadCN UI + Radix Primitives**. Radix implements WAI-ARIA Authoring Practices 1.2 patterns out of the box: focus trapping in dialogs, roving tabindex in composite widgets, `aria-expanded`/`aria-selected` state toggling, and Esc-key dismissal. The webstack a11y contract is:

- **Trust Radix** for widget-level semantics — do not override its ARIA attributes without understanding the WAI-ARIA pattern.
- **Enforce** labelling, heading structure, color contrast, and skip navigation at the application level — Radix does not do these for you.
- **Automate** detection with axe-core at the component (jest-axe) and E2E (@axe-core/playwright) layers.
- **Audit** manually for WCAG 2.2-specific criteria (target size, focus appearance, accessible authentication) that axe cannot fully cover.

ShadCN primitives live at `src/shared/ui/`. Customizing `cva` variants (colors, sizes) carries a11y risk — verify contrast ratios after changing color tokens and maintain 24×24 CSS pixel minimum targets when adjusting button sizing (WCAG 2.5.8).

## Why this approach

**Radix as the accessibility floor.** Building interactive widgets from raw `<div>` elements is the leading source of a11y regressions in React apps. Radix implements each WAI-ARIA pattern correctly. ShadCN wraps Radix with styled shells; webstack adds `cva` variants. Each layer adds styling — none replaces semantics.

**Shift-left with automation.** axe-core inside Vitest catches violations when a component is written. `@axe-core/playwright` covers the composed page including Server Components (jsdom cannot render RSC). Zero infrastructure cost.

**WCAG 2.2 over 2.1.** Key new AA criteria over 2.1: 2.4.11 Focus Appearance, 2.5.7 Dragging Movements, 2.5.8 Target Size Minimum, 3.3.7 Redundant Entry, 3.3.8 Accessible Authentication. axe-core enforces 2.1 rules by default; 2.2-specific rules require the `wcag22aa` tag.

## Section 1 — Baseline (Tier 1, always)

Every component and page must meet these requirements unconditionally.

### Semantic HTML

Use the element that describes the content.

| Instead of | Use |
|---|---|
| `<div onClick={...}>` | `<button>` or `<a href>` |
| `<div role="heading">` | `<h1>`–`<h6>` |
| `<div class="list">` + `<div>` items | `<ul>` / `<ol>` + `<li>` |
| `<span class="label">` | `<label htmlFor="...">` |
| `<div class="nav">` | `<nav aria-label="...">` |

One `<h1>` per page. Heading levels must not skip. Navigation landmarks (`<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`) let screen reader users jump directly to regions. Set `lang` on `<html>` in `src/app/layout.tsx` (WCAG 3.1.1).

### Focus management

Every interactive element must be keyboard-reachable and show a visible focus indicator. ShadCN's `cva` base classes include `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2` — never remove them.

`focus-visible:ring-*` uses CSS `:focus-visible`: ring shows for keyboard navigation only, not mouse clicks. WCAG 2.4.11 (WCAG 2.2 AA) requires minimum area and contrast for the focus indicator; `ring-2 ring-offset-2` with a contrasting `--ring` token meets this.

Radix Dialog returns focus to the trigger on close automatically. For custom transitions outside Radix, save and restore focus via `useRef`.

### Keyboard trap avoidance

A keyboard trap occurs when focus enters a widget and cannot escape standard keys (Tab, Shift+Tab, Esc, Arrow). This is a WCAG 2.1.2 failure.

- **Modal dialogs** intentionally trap focus — Radix Dialog handles this correctly and always responds to Esc.
- **Non-modal overlays** (tooltips, dropdowns) must not trap focus — Tab should close them and advance.
- **Custom widgets** that consume Arrow keys must release focus on Tab/Shift+Tab.

### ARIA patterns (role / state / property)

First rule of ARIA: use native HTML instead when a suitable element exists.

```tsx
// Status (non-interrupting) vs alert (immediate)
<div role="status" aria-live="polite">Saved successfully.</div>
<div role="alert" aria-live="assertive">Submission failed.</div>

// Decorative icon — hidden from screen readers
<button aria-label="Delete project">
  <TrashIcon aria-hidden="true" />
</button>

// Visible label elsewhere — reference by ID
<section aria-labelledby="billing-heading">
  <h2 id="billing-heading">Billing</h2>
</section>
```

Radix manages `aria-expanded`, `aria-selected`, `aria-checked`, `aria-modal` automatically. Do not duplicate these manually on Radix components.

### Label–input pairing

Every input must have an associated label. Placeholder text is not a label: it disappears on input and has insufficient contrast in most browsers.

```tsx
// ShadCN FormLabel sets htmlFor automatically via useFormField()
<FormField name="email" render={({ field }) => (
  <FormItem>
    <FormLabel>Email address</FormLabel>
    <FormControl>
      <Input type="email" placeholder="you@example.com" {...field} />
    </FormControl>
    <FormMessage />
  </FormItem>
)} />
```

For groups (radio, checkbox), wrap in `<fieldset>` + `<legend>`.

### Skip navigation

Add a skip link as the first focusable element in `<body>`:

```tsx
// src/app/layout.tsx
<html lang="en">
  <body>
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-4 focus:bg-background focus:text-foreground"
    >
      Skip to main content
    </a>
    <SiteHeader />
    <main id="main-content" tabIndex={-1}>{children}</main>
  </body>
</html>
```

`tabIndex={-1}` on `<main>` allows programmatic focus when the skip link is activated.

## ShadCN + Radix a11y patterns

ShadCN components are Radix primitives + `cva` styling. Accessibility is Radix's responsibility; visuals are ShadCN's. Key Radix behaviors:

See also: `docs/frontend/shadcn-customization.md` for cva variant patterns and `cn()` utility.

| Component | ARIA pattern | Built-in behavior |
|---|---|---|
| `Dialog` | Modal dialog | Focus trap, Esc dismiss, `aria-modal="true"`, `role="dialog"` |
| `AlertDialog` | Alert dialog | Focus moves to Cancel on open |
| `DropdownMenu` | Menu | Arrow key navigation, `role="menu"` / `role="menuitem"` |
| `Select` | Listbox | `role="listbox"`, `role="option"`, keyboard selection |
| `Tabs` | Tabs | Roving tabindex, Arrow navigation, `role="tablist"` |
| `Checkbox` | Checkbox | `role="checkbox"`, `aria-checked`, Space to toggle |
| `Tooltip` | Tooltip | Shown on hover and focus, Esc to dismiss |

### Dialog focus trap

Radix `Dialog` traps focus inside `DialogContent`. Tab cycles within the dialog; Esc dismisses and returns focus to the trigger. `DialogTitle` is mandatory — omitting it fails the accessible name rule. If a visually hidden title is needed, use `@radix-ui/react-visually-hidden`.

### FormMessage aria-live

`<FormMessage>` mounts when an error exists and unmounts when cleared. Screen readers announce inserted DOM nodes inside live regions. Do not suppress `<FormMessage>` with `display: none` — let it mount/unmount so live region behavior works.

### cva variants and a11y

When adding custom variants, verify:

- **Color contrast (1.4.3 AA):** Text ≥ 4.5:1 against background (3:1 for large text). UI components/borders ≥ 3:1 (1.4.11).
- **Target size (2.5.8 WCAG 2.2 AA):** Interactive elements minimum 24×24 CSS px. Default ShadCN `h-9` (36 px) passes. If adding compact sizes, enforce the minimum:

```tsx
sm: 'h-6 min-w-6 px-2 text-xs',  // 24px — meets 2.5.8 minimum
// xs: 'h-5 px-1'  ← 20px, fails 2.5.8
```

## RHF a11y

ShadCN's `useFormField` hook wires ARIA automatically. Use `Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage` — do not manually set `aria-invalid`, `aria-describedby`, or `id` on the inner `<Input>`; `FormControl` spreads them.

### useFormField ARIA mapping

| ID | Applied to | Purpose |
|---|---|---|
| `formItemId` | `<FormControl>` input | Stable `id` for `htmlFor` |
| `formDescriptionId` | `<FormDescription>` | Referenced by `aria-describedby` |
| `formMessageId` | `<FormMessage>` | Appended to `aria-describedby` when error exists |

`<FormControl>` sets `aria-invalid={!!error}` automatically. Screen readers announce "invalid entry" on flip, then read `<FormMessage>` via `aria-describedby`.

### aria-required and autocomplete

```tsx
<FormField name="email" render={({ field }) => (
  <FormItem>
    <FormLabel>
      Email <span aria-hidden="true">*</span>  {/* visual asterisk hidden from SR */}
    </FormLabel>
    <FormControl>
      <Input
        type="email"
        autoComplete="email"     // WCAG 1.3.5 — identify input purpose
        aria-required="true"    // explicit for ARIA consumers
        {...field}
      />
    </FormControl>
    <FormMessage />
  </FormItem>
)} />
```

Personal data inputs require `autoComplete` values per WCAG 1.3.5 (AA). Common values: `email`, `given-name`, `family-name`, `tel`, `organization`, `street-address`, `current-password`, `new-password`.

### Error message mapping

Map server-returned field errors via `form.setError(fieldName, { message })` — `<FormMessage>` reads from `formState.errors` and announces via the `aria-describedby` relationship. For cross-field errors, render with `role="alert"` (assertive) for failures or `role="status"` (polite) for success messages.

## Section 2 — Automated testing (Tier 2, opt-in)

Automated a11y testing is opt-in. Enable when the project requires WCAG 2.2 AA conformance documentation or a continuous regression gate. All tools integrate into the existing Vitest + Playwright setup.

### @axe-core/playwright (E2E)

`pnpm add -D @axe-core/playwright`. Audits the full rendered page including Server Components and streaming SSR — jsdom cannot cover this.

```typescript
// tests/e2e/a11y.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('login page — WCAG 2.2 AA', async ({ page }) => {
  await page.goto('/login');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

`wcag22aa` enables `target-size` (WCAG 2.5.8) and other 2.2 rules disabled by default. Suppress false positives narrowly with a ticket reference; use `.exclude('#selector')` or `.disableRules(['rule-id'])`.

### jest-axe (component layer, Vitest)

`pnpm add -D jest-axe`. Catches violations in isolated component renders at near-zero overhead inside the existing Vitest process.

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe, toHaveNoViolations } from 'jest-axe';
import { expect, it } from 'vitest';

expect.extend(toHaveNoViolations);

it('login form — initial state', async () => {
  const { container } = render(<LoginForm onSubmit={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});

it('login form — error state', async () => {
  const { container } = render(<LoginForm onSubmit={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
  await waitFor(() => screen.getByRole('alert'));
  expect(await axe(container)).toHaveNoViolations();
});
```

Test both initial and error states — `aria-invalid`/`aria-describedby` changes are invisible to functional assertions but caught by axe.

### Storybook a11y addon

`pnpm add -D @storybook/addon-a11y` then add `'@storybook/addon-a11y'` to the `addons` array in `.storybook/main.ts`. Adds an Accessibility panel to Storybook that highlights violating elements in canvas. Does not fail CI — use jest-axe and `@axe-core/playwright` for hard gates.

### WCAG 2.2-specific axe rules

| axe rule | WCAG SC | Impact | Default |
|---|---|---|---|
| `target-size` | 2.5.8 (AA) | Serious | Disabled — add `wcag22aa` tag |
| `scrollable-region-focusable` | 2.1.1 | Serious | Enabled in `wcag21a` |
| `css-orientation-lock` | 1.3.4 | Serious | Enabled in `wcag21aa` |

axe-core has no automated rules for 2.4.11 (Focus Appearance) or 3.3.8 (Accessible Authentication) — manual review required.

## Playwright MCP for a11y

`@playwright/mcp` (Microsoft, G1) exposes a Playwright-controlled browser as MCP tools. The build-fe SubAgent uses it to inspect the live accessibility tree without writing a test file.

Setup — add to `.claude/settings.json` mcpServers:

```json
{ "command": "npx", "args": ["@playwright/mcp@latest", "--headless"] }
```

Or: `claude mcp add playwright npx @playwright/mcp@latest`

See `docs/frontend/testing-strategy.md` § Playwright MCP integration for the full `mcpServers` config.

### Accessibility tree inspection

Playwright MCP returns **structured accessibility snapshots** — the page's accessibility tree (roles, names, states, hierarchy) rather than pixels. Unlabeled inputs, missing heading hierarchy, and incorrect roles are immediately visible.

Typical a11y agent prompts:

- `"Navigate to /checkout and capture the accessibility snapshot"` — identify roles and names
- `"Tab through all interactive elements and report focus order"` — verify logical interaction order
- `"Submit the form without filling fields — check aria-invalid states"` — verify live region announcements
- `"Open the dialog and attempt Tab outside it"` — confirm Radix focus trap
- `"Close the dialog with Escape and report which element has focus"` — verify focus restoration

Playwright MCP is for exploratory, ad-hoc inspection during development. Use `@axe-core/playwright` for automated rule-based regression gates in CI.

## Anti-patterns

**`<div onClick>` instead of `<button>`** — not keyboard-reachable, no role, no implicit focus. Requires manual `role="button"`, `tabIndex={0}`, and `onKeyDown` to approximate native behavior. Use `<button>` and style it.

**Placeholder as label** — disappears on input, typically fails contrast, not announced as a label by assistive technology. Use `<FormLabel>` from ShadCN; placeholder is a hint, not a label.

**Color as sole meaning carrier** — fails WCAG 1.4.1. Always pair color with text or an `aria-hidden` icon so meaning does not depend on color perception alone.

**Removing focus outlines** — `* { outline: none }` or `button:focus { outline: none }` fails WCAG 2.4.7 and 2.4.11. ShadCN's `focus-visible:ring-2 focus-visible:ring-ring` is the approved replacement. Never add `focus:outline-none` without the ring classes.

**`aria-label` on non-interactive `<div>`** — ignored by screen readers per ARIA spec. Use landmark elements or `aria-labelledby` referencing a heading ID.

**Suppressing axe rules without a ticket** — always include a comment with a ticket reference so suppressions are periodically reviewed.

**Missing `lang` on `<html>`** — WCAG 3.1.1 failure. Set `lang="en"` (or current locale) in `src/app/layout.tsx`.

## Sources

- **WCAG 2.2 Quick Reference:** https://www.w3.org/WAI/WCAG22/quickref/ — _authoritative_
- **axe-core rule descriptions:** https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md — _authoritative_
- **Radix UI Primitives accessibility overview:** https://www.radix-ui.com/primitives/docs/overview/accessibility — _authoritative_
- **Playwright MCP getting started:** https://playwright.dev/docs/getting-started-mcp — _authoritative (Microsoft / G1)_
- **@axe-core/playwright:** https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright — _authoritative_
- **WAI-ARIA Authoring Practices 1.2:** https://www.w3.org/WAI/ARIA/apg/ — _authoritative_
- **WebAIM contrast checker:** https://webaim.org/resources/contrastchecker/ — _community: WebAIM_

Last verified: 2026-05-04 (axe-core 4.10 / Playwright 1.X / WCAG 2.2 / React 19 / Next.js 16.X).
