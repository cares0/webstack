# Testing strategy (Next.js 16 + RSC + FSD-lite)

> Reference for build-fe SubAgent and frontend-implementer.
> Testing pyramid, toolchain conventions, and patterns for webstack's Next.js 16 + RSC + FSD-lite stack — Vitest 3, Playwright 1.x, MSW 2, and axe-core.

## What is the test pyramid

webstack frontends apply a four-layer pyramid tuned to an RSC-first, FSD-lite codebase.

**1. Unit tests (Vitest 3).** Pure functions, hooks, Zod schemas, utilities — no DOM, no network. Fast and cheap.

**2. Component tests (Vitest 3 + RTL).** Client Component slices in isolation. `userEvent` drives interactions; assertions check accessible roles and text. Server Components are not rendered here — RSC coverage lives at layer 3.

**3. E2E tests (Playwright 1.x).** Full user flows against a running Next.js dev/preview server. Server Components, route handlers, middleware, and streaming SSR all participate. Catches the class of bug layers 1–2 structurally cannot — RSC serialisation errors, route-level redirects, cookie-gated pages, streaming failures.

**4. Accessibility tests (axe-core).** Bolt-on to layers 2 and 3. `jest-axe` inside Vitest for component checks; `@axe-core/playwright` inside Playwright fixtures for full-page audits. Both enforce WCAG 2.1 AA.

```
          ┌───────────────────┐
          │  a11y (axe)       │  ← bolt-on to layers 2 and 3
          ├───────────────────┤
          │  E2E (Playwright) │  ← slowest, highest confidence
          ├───────────────────┤
          │  Component (RTL)  │  ← DOM, no network
          ├───────────────────┤
          │  Unit (Vitest)    │  ← fastest, pure logic
          └───────────────────┘
```

The pyramid shape is intentional. Inverting it — writing mostly E2E tests — produces a slow, flaky suite with poor failure locality.

## Why this approach

**Free-tier context.** Vitest runs in GitHub Actions free minutes. Playwright runs headless with no paid browser grid. MSW eliminates the need for a live backend. Cost floor: zero.

**Signal vs noise.** Snapshot tests of full render trees, real network hits, and internal-state assertions all produce noise. webstack conventions eliminate these structurally: MSW intercepts all network; RTL's "query by accessible role" keeps assertions behaviour-focused; Playwright fixtures encapsulate setup.

**Fast feedback.** `pnpm test` (unit + component) must complete under 30 seconds. Vitest watch achieves sub-second re-runs. Playwright E2E is excluded from the default watch cycle — it runs on `pnpm test:e2e` or in CI.

**RSC-aware coverage.** Server Components cannot run in Vitest + jsdom — they may suspend, access the filesystem, or call `cookies()`. RSC coverage lives at the E2E layer. This is deliberate. Extract logic-heavy helpers from Server Components and unit-test them separately.

## webstack convention

### File placement

Tests live beside the slice they cover. The FSD import rule (`app > widgets > features > entities > shared`) applies to test files too.

```
src/
  features/
    auth/
      ui/
        LoginForm.tsx
        LoginForm.test.tsx       ← component test beside the component
      model/
        schema.ts
        schema.test.ts           ← unit test beside the schema
  entities/
    user/
      ui/
        UserCard.tsx
        UserCard.test.tsx

src/shared/test/msw/
  handlers.ts                    ← all MSW handlers, grouped by domain
  server.ts                      ← setupServer() for Vitest (Node)
  browser.ts                     ← setupWorker() for Storybook / dev

tests/e2e/
  auth.spec.ts
  dashboard.spec.ts
playwright.config.ts             ← project root
```

### `playwright.config.ts` standard

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html'], ['github']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit',   use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

`trace: 'on-first-retry'` captures a trace archive on the first retry of a failing test, enabling Trace Viewer replay without overhead on passing tests.

### npm scripts

```jsonc
{
  "scripts": {
    "test":        "vitest run",
    "test:watch":  "vitest",
    "test:e2e":    "playwright test",
    "test:e2e:ui": "playwright test --ui"
  }
}
```

`pnpm test` is the inner-loop command: unit + component, no browser. `pnpm test:e2e` is the full E2E suite. CI runs both sequentially.

### `vitest.config.ts` + MSW setup

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/shared/test/setup.ts'],
  },
});
```

```typescript
// src/shared/test/setup.ts
import '@testing-library/jest-dom';
import { beforeAll, afterEach, afterAll } from 'vitest';
import { server } from './msw/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

`onUnhandledRequest: 'error'` turns unexpected network calls into test failures, preventing silent real fetches from slipping through.

## Playwright MCP integration

`@playwright/mcp` exposes a Playwright-controlled browser as MCP tools. The build-fe SubAgent uses it to verify UI behaviour, capture screenshots, and inspect the accessibility tree without running `playwright test` manually.

### Setup

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--headless"]
    }
  }
}
```

Or via Claude Code CLI: `claude mcp add playwright npx @playwright/mcp@latest`

### What the agent can do

The MCP server provides structured accessibility snapshots — element references from the live DOM — rather than pixel images. Key capabilities:

- **Navigate:** open URLs, follow links, handle redirects.
- **Interact:** click, type, fill forms, keyboard shortcuts.
- **Inspect:** read accessible names, roles, and ARIA attributes.
- **Capture:** screenshots for visual verification; console logs and network requests for debugging.
- **Run code:** arbitrary Playwright scripts via `browser_run_code`.
- **Mock network:** intercept requests by URL pattern without a real backend.

### Typical agent workflow

```
Agent: "Navigate to http://localhost:3000/login and capture the accessibility tree"
→ MCP server returns structured element references (roles, names, ARIA attrs)
→ Agent verifies semantic correctness, then writes RTL assertions to match
```

The agent sees live page state directly — no write–run–read loop. Trace files from `trace: 'on-first-retry'` help diagnose failures before adding assertions.

## MSW patterns

MSW 2 intercepts at the `fetch` / `XHR` level in both Node (Vitest) and browser (Storybook, dev) environments. The handler API changed materially from MSW 1 — do not copy 1.x examples.

### Defining handlers

```typescript
// src/shared/test/msw/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users/:id', ({ params }) =>
    HttpResponse.json({ id: params.id, name: 'Alice', email: 'alice@example.com' }),
  ),

  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json();
    if (body.email === 'invalid@example.com') {
      return HttpResponse.json({ error: 'Invalid credentials' }, { status: 401 });
    }
    return HttpResponse.json({ token: 'test-token' });
  }),
];
```

Resolver signature: `({ request, params, cookies }) => HttpResponse`. Constructors: `HttpResponse.json()`, `HttpResponse.text()`, `HttpResponse.error()`.

### Composing on top of the generated SDK

Type handler responses against generated DTOs so TypeScript surfaces drift when `pnpm gen:api` regenerates the SDK:

```typescript
import type { UserDto } from '@/shared/api/generated';
import { http, HttpResponse } from 'msw';

const mockUser: UserDto = { id: '1', name: 'Alice', email: 'alice@example.com', role: 'MEMBER' };
export const userHandlers = [http.get('/api/users/:id', () => HttpResponse.json(mockUser))];

### Runtime overrides

Per-test overrides use `server.use()`. `server.resetHandlers()` in the global `afterEach` restores defaults.

```typescript
it('shows error state when API returns 500', async () => {
  server.use(
    http.get('/api/users/:id', () =>
      HttpResponse.json({ error: 'Internal Server Error' }, { status: 500 }),
    ),
  );
  render(<UserProfile userId="1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
});
```

### Request matching

MSW 2 supports exact paths, path parameters (`/api/users/:id`), and wildcards (`/api/*`). When the generated SDK calls an absolute URL (e.g., `NEXT_PUBLIC_API_BASE_URL` is set), match the full URL:

```typescript
http.get('https://api.example.com/v1/users/:id', resolver)
```

Use `passthrough()` for requests that should reach the real network during development.

## a11y testing

Accessibility is built into both the component and E2E layers, not deferred to a separate audit phase.

### Component layer: jest-axe

```typescript
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { expect } from 'vitest';
import { LoginForm } from './LoginForm';

expect.extend(toHaveNoViolations);

it('has no axe violations', async () => {
  const { container } = render(<LoginForm onSubmit={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});
```

### E2E layer: @axe-core/playwright

```typescript
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('login page meets WCAG 2.1 AA', async ({ page }) => {
  await page.goto('/login');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

### Baseline rules

webstack enforces `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`. Key rules at this level:

| Rule | Impact | Description |
|---|---|---|
| `color-contrast` | Serious | Text ≥ 4.5:1 ratio (AA normal), 3:1 (large) |
| `button-name` | Critical | `<button>` must have discernible text or `aria-label` |
| `image-alt` | Critical | `<img>` must have meaningful `alt` |
| `label` | Critical | Form input must have an associated `<label>` |
| `aria-required-attr` | Critical | ARIA roles must have required attributes |

WCAG 2.2 rules are disabled by default in axe-core. Enable per-test when validating 2.2-specific features.

### False positive handling

Suppress narrowly — never globally:

```typescript
// @axe-core/playwright — exclude by selector
const results = await new AxeBuilder({ page })
  .withTags(['wcag2a', 'wcag2aa'])
  .exclude('#third-party-datepicker')
  .analyze();

// jest-axe — disable specific rule with ticket reference
const results = await axe(container, {
  rules: {
    'aria-hidden-focus': { enabled: false }, // tracked in #1234
  },
});
```

Every suppression must include a ticket number so it is periodically reviewed.

## Visual regression

Playwright's `toHaveScreenshot()` captures pixel-level baselines and catches layout shifts, colour regressions, and text truncation that functional assertions miss.

### Basic snapshot test

```typescript
test('dashboard layout matches snapshot', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('dashboard.png', {
    mask: [page.locator('[data-testid="timestamp"]')],
    maxDiffPixelRatio: 0.02,
  });
});
```

`maxDiffPixelRatio: 0.02` tolerates sub-pixel rendering differences. Set to `0` for pixel-perfect comparisons in controlled environments.

### Baseline management

Baselines live in `tests/e2e/__snapshots__/`. CI never runs `--update-snapshots`; the PR author updates locally and commits the diff. Baselines must be generated on Linux to match CI — use the official `mcr.microsoft.com/playwright` Docker image to regenerate.

Use visual regression for high-stability, high-value surfaces: design system components in `src/shared/ui/`, critical landing pages, data visualisations. Avoid blanketing every feature component — baseline maintenance costs compound quickly.

## Anti-patterns

**Piling integration tests into a single slice.** If an `auth` slice test imports and renders `dashboard` components to verify a flow, it is an E2E test in the wrong layer. Move it to `tests/e2e/`.

**Network calls without MSW.** Disabling `onUnhandledRequest: 'error'` lets real fetches slip through. Tests pass locally with a live backend, fail in CI. Every network boundary in component tests must have an MSW handler.

**Indiscriminate snapshot testing.** `toMatchSnapshot()` on a full render tree breaks on every unrelated change — added data-testid, reordered classes, copy updates. Use `toHaveScreenshot` for visual regression; write behavioural assertions for everything else.

**Snapshots as a substitute for behavioural assertions.** A snapshot of `<button class="btn-primary">Submit</button>` says nothing about whether the button works. Assert on outcomes: success state appears, error message shows on failure. Snapshots catch structural regressions; they do not replace intent-driven assertions.

**Testing implementation details.** Asserting on internal state or CSS class names couples tests to implementation. Query by accessible role — `getByRole('button', { name: /submit/i })` — and assert on what the user sees.

**Running E2E against shared environments.** E2E tests mutate data. Always target a local dev server or an ephemeral preview deployment.

## Sources

- **Playwright documentation** — _authoritative_ — https://playwright.dev/docs/intro and https://playwright.dev/docs/getting-started-mcp. Official Playwright 1.x API reference, `playwright.config.ts` options, and MCP integration guide.

- **Mock Service Worker documentation** — _authoritative_ — https://mswjs.io/docs. MSW 2.x handler API (`http.*`, `HttpResponse`), `setupServer` / `setupWorker`, and the 1.x-to-2.x migration guide.

- **axe-core rule descriptions** — _authoritative_ — https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md. Canonical list of axe-core rules, WCAG level mappings, impact ratings, and default-enabled status.

- **Vitest documentation** — _authoritative_ — https://vitest.dev/guide/. Vitest 3.x configuration, jsdom environment, watch mode, and RTL integration.

- **@axe-core/playwright** — _authoritative_ — https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright. Integration package for running axe audits inside Playwright test fixtures.

- **Testing Library guiding principles** — _community: Kent C. Dodds_ — https://testing-library.com/docs/guiding-principles. The "query by accessible role, not implementation detail" principle and rationale for behaviour-focused assertions.

Last verified: 2026-05-04 (Playwright 1.X / Vitest 3.X / MSW 2.X / @axe-core/playwright X.X).
