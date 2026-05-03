# Frontend error monitoring (Sentry)

> Reference for build-fe SubAgent and frontend-implementer.
> ⚙️ **Optional integration** — activated via init's "Observability" question (`manifest.optional_integrations.observability=true`). Until activated, this document is reference-only; setup steps live in `recipes/observability-setup.md`.
> Browser-side error capture and Sentry MCP usage in webstack's Next.js 16 + RSC stack.

## What is error monitoring in webstack

webstack uses **Sentry** (SDK 8.X) as its first-pick error monitoring tool. `@sentry/nextjs` instruments the Next.js 16 App Router across three runtimes simultaneously — browser, Node.js server, and edge — producing a unified view of errors regardless of where in the RSC pipeline they originate.

Two capabilities drive the choice:

**Browser SDK.** Captures unhandled exceptions, rejected promises, React render errors, Server Action failures, and edge-runtime errors. Every event carries a source-map-resolved stack trace, user browser/OS context, breadcrumbs of prior interactions, and a release tag tying the error to the exact deployment commit.

**Session Replay.** Records a video-like replay of the user's session at the moment an error occurred — the most effective tool for reproducing hard-to-repro bugs in production. Sampling is configurable; PII masking is aggressive by default.

Both feed into the same Sentry project. The Sentry MCP server (section 4) lets the build-fe SubAgent query issues without leaving the coding session.

## Why Sentry Cloud Free

Sentry's free tier is the correct starting point for a webstack project on Vercel Hobby + Oracle Always Free.

- **5,000 errors per month.** Sufficient for early-stage projects. The quota resets monthly; if a deployment regression floods errors, fix the regression rather than upgrading.
- **Source map upload.** Sentry's Webpack/Turbopack plugin (bundled in `@sentry/nextjs`) uploads source maps at build time on Vercel automatically via `SENTRY_AUTH_TOKEN`. Production source maps are hidden from the public — only the Sentry dashboard resolves them.
- **Replay sampling.** Free tier allows replay. Recommended settings (100% on error, 0.1% on session) stay well within quota.
- **Vercel native integration.** The Sentry Vercel integration (marketplace) injects `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` into Vercel build environments automatically — no manual CI secret wiring needed.
- **Sentry MCP.** Available to all Sentry users (cloud) at `https://mcp.sentry.dev/mcp` via OAuth. The agent-accessible tooling requires no paid plan.

The critical upgrade trigger is _error volume_, not feature gates — source maps, replay, and MCP are all available on the free plan.

## webstack convention

### Package installation

```bash
pnpm add @sentry/nextjs
```

The `@sentry/nextjs` package includes the core JavaScript SDK, Next.js-specific instrumentation, and the Webpack/Turbopack source map plugin.

### SDK initialisation files

Sentry 8.X with Next.js 16 uses three runtime-specific files plus `instrumentation.ts` for server-side registration.

**`instrumentation-client.ts`** — browser runtime (co-located at project root, not inside `src/`):

```ts
// instrumentation-client.ts
import * as Sentry from '@sentry/nextjs'

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  replaysSessionSampleRate: 0.001,   // 0.1% of sessions
  replaysOnErrorSampleRate: 1.0,     // 100% of sessions with an error
  integrations: [
    Sentry.replayIntegration({
      maskAllText: true,
      maskAllInputs: true,
      blockAllMedia: false,
      networkDetailAllowUrls: [],    // opt-in only; see §Replay sampling
    }),
  ],
  environment: process.env.NODE_ENV,
})
```

**`sentry.server.config.ts`** and **`sentry.edge.config.ts`** — Node.js and edge runtimes respectively. Both use the same minimal init (no replay — server-side only):

```ts
// sentry.server.config.ts  (identical shape for sentry.edge.config.ts)
import * as Sentry from '@sentry/nextjs'

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  environment: process.env.NODE_ENV,
})
```

**`instrumentation.ts`** — server-side registration entry point (Next.js 16 standard; replaces the old `sentry.server.config.ts`-only approach):

```ts
// instrumentation.ts  (project root, NOT inside src/)
import * as Sentry from '@sentry/nextjs'

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config')
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config')
  }
}

export const onRequestError = Sentry.captureRequestError
```

`onRequestError` is a Next.js 16 instrumentation hook that fires on every unhandled server-side request error, ensuring Server Actions and route handler errors are captured even when no Error Boundary wraps the call site.

**`src/shared/lib/sentry.ts`** — thin re-export so FSD-lite code imports from `@/shared/lib/sentry` instead of `@sentry/nextjs` directly (single seam for test stubbing):

```ts
export * from '@sentry/nextjs'
```

**`next.config.ts`** — wrap with `withSentryConfig`:

```ts
// next.config.ts
import { withSentryConfig } from '@sentry/nextjs'
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  cacheComponents: true,
}

export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  tunnelRoute: '/sentry-tunnel',   // avoids ad-blocker interference
  silent: !process.env.CI,
  sourcemaps: {
    disable: false,
    deleteSourcemapsAfterUpload: true,   // do not serve maps publicly
  },
})
```

### Environment variables

| Variable | Context | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | Browser + server | DSN — safe to expose in JS bundle |
| `SENTRY_AUTH_TOKEN` | Build only | Source map upload authentication |
| `SENTRY_ORG` | Build only | Sentry organisation slug |
| `SENTRY_PROJECT` | Build only | Sentry project slug |

`NEXT_PUBLIC_SENTRY_DSN` is not a secret — it is a receive-only ingest endpoint, safe in the browser bundle. `SENTRY_AUTH_TOKEN` is build-time only; never assign it a `NEXT_PUBLIC_` prefix.

### FSD slice Error Boundary placement

Each FSD feature slice that owns a user-facing route owns its own Error Boundary. Do not rely solely on `app/global-error.tsx` — it catches only root layout errors and provides no feature-level context.

Three tiers: `app/global-error.tsx` (root layout) → `app/(features)/<route>/error.tsx` (route segment) → `src/features/<feature>/ui/<Feature>ErrorBoundary.tsx` (widget-level graceful degradation).

## Sentry MCP integration

### Connecting the MCP server

The Sentry MCP server runs at `https://mcp.sentry.dev/mcp` and authenticates via OAuth. No local installation is required for cloud Sentry users.

Add to Claude Code:

```bash
claude mcp add --transport http sentry https://mcp.sentry.dev/mcp
```

Or add manually to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "sentry": {
      "type": "http",
      "url": "https://mcp.sentry.dev/mcp"
    }
  }
}
```

On first use, the MCP server initiates an OAuth browser flow. Credentials cache automatically. For non-interactive environments (CI, headless agents), pre-authenticate with:

```bash
npx @sentry/mcp-server@latest auth login
```

### What the agent can do

The Sentry MCP server exposes 19 tools. The build-fe SubAgent uses them to:

- **Query issues:** `search_issues` translates natural language into Sentry query syntax. "Find all TypeError crashes on the dashboard page in the last 7 days" returns structured issue data with stack traces.
- **Inspect events:** `search_events` retrieves individual error events with full context — breadcrumbs, user agent, replay link.
- **Manage releases:** list releases, associate commits, verify that source maps uploaded correctly for a given release.
- **Seer AI analysis:** the MCP exposes Sentry's built-in Seer AI which can propose root cause hypotheses directly from the issue data.

Scope the MCP session to the current project to reduce noise:

```bash
claude mcp add --transport http sentry "https://mcp.sentry.dev/mcp?org=my-org&project=my-project"
```

### Agent workflow example

A typical build-fe SubAgent debugging loop: `search_issues` with a natural language query → read the source-map-resolved stack trace → open the relevant file and fix → commit → Vercel deploys → confirm error rate dropped on the new release via `search_issues` again. No browser tab switching, no copy-pasting stack traces.

## Error Boundary patterns

### Next.js App Router `error.tsx`

Every dynamic route segment should have an `error.tsx` file. Next.js automatically renders it when an error escapes from a Server or Client Component in that segment.

```tsx
// src/app/(features)/dashboard/error.tsx
'use client'

import { useEffect } from 'react'
import * as Sentry from '@/shared/lib/sentry'

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    Sentry.captureException(error, {
      tags: { feature: 'dashboard' },
      extra: { digest: error.digest },
    })
  }, [error])

  return (
    <div role="alert">
      <p>Something went wrong loading the dashboard.</p>
      <button onClick={reset}>Try again</button>
    </div>
  )
}
```

`error.digest` is a Next.js-generated hash correlating the client-side boundary with the server-side `onRequestError` event. Always include it so Sentry groups client and server occurrences together.

### `app/global-error.tsx`

Catches errors in the root layout. Must render `<html>` and `<body>` since it replaces the entire document:

```tsx
// app/global-error.tsx
'use client'

import { useEffect } from 'react'
import * as Sentry from '@/shared/lib/sentry'

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error, { tags: { scope: 'global' } })
  }, [error])

  return (
    <html><body><p>A critical error occurred. Please refresh.</p></body></html>
  )
}
```

### Feature slice Error Boundary

Place an explicit React Error Boundary in `src/features/<feature>/ui/` for widgets that should degrade without crashing the whole route. Standard class component with `componentDidCatch`:

```tsx
// src/features/analytics/ui/AnalyticsErrorBoundary.tsx
'use client'

import { Component, type ReactNode } from 'react'
import * as Sentry from '@/shared/lib/sentry'

type Props = { children: ReactNode; fallback?: ReactNode }
type State = { hasError: boolean }

export class AnalyticsErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }
  static getDerivedStateFromError = (): State => ({ hasError: true })

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    Sentry.captureException(error, {
      tags: { feature: 'analytics' },
      extra: { componentStack: info.componentStack },
    })
  }

  render() {
    return this.state.hasError
      ? (this.props.fallback ?? <p>Analytics unavailable.</p>)
      : this.props.children
  }
}
```

Wrap in the widget layer: `<AnalyticsErrorBoundary fallback={<p>Chart unavailable.</p>}><AnalyticsDashboard /></AnalyticsErrorBoundary>`.

### Server Action error capture

Capture errors from Server Actions explicitly to add structured context. Do not rely solely on `onRequestError`:

```ts
// src/features/checkout/api/mutations.ts
'use server'

import * as Sentry from '@/shared/lib/sentry'

export async function submitCheckout(formData: FormData) {
  const parsed = checkoutSchema.safeParse(Object.fromEntries(formData))
  if (!parsed.success) return { error: 'Invalid form data' }

  try {
    await PaymentService.createCharge({ body: parsed.data })
  } catch (err) {
    Sentry.captureException(err, { tags: { feature: 'checkout' } })
    return { error: 'Payment failed. Please try again.' }
  }
}
```

Return a typed result object rather than re-throwing — unhandled throws propagate to the nearest `error.tsx` and lose the structured context.

## Source map upload

### Automatic via Vercel

When the Sentry Vercel integration is installed (Sentry marketplace → Vercel → Connect), Vercel injects `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` as build environment variables automatically. The `withSentryConfig` wrapper in `next.config.ts` uploads source maps at the end of every Vercel build. No further configuration is needed. Verify the integration is active: Sentry → Settings → Integrations → Vercel.

### Release tag synchronisation

`withSentryConfig` reads `VERCEL_GIT_COMMIT_SHA` automatically on Vercel and sets the release identifier to the commit SHA. Every deployment creates a corresponding Sentry release, tying each error event to the exact commit that introduced it.

For non-Vercel CI, set `SENTRY_RELEASE=$(git rev-parse --short HEAD)` before `pnpm build`, or pass `release` explicitly in `withSentryConfig`.

### Source map visibility policy

Source maps uploaded to Sentry are **not** served publicly. The `deleteSourcemapsAfterUpload: true` option in `withSentryConfig` removes the `.map` files from the Vercel output after upload — they are stored only in Sentry's servers and resolved server-side when rendering stack traces in the dashboard.

Do not commit source map files to the repository. Do not set `productionBrowserSourceMaps: true` in `next.config.ts` — this serves `.map` files from the CDN and exposes your source to anyone who requests them.

### Manual CLI upload

For non-Vercel deployments or when debugging source map resolution, use `@sentry/cli`:

```bash
npx sentry-cli releases \
  --org "$SENTRY_ORG" --project "$SENTRY_PROJECT" \
  files "$RELEASE" upload-sourcemaps .next \
  --url-prefix '~/_next' --rewrite
```

`--rewrite` rewrites `sourceMappingURL` comments so Sentry can resolve stacks correctly.

## Replay sampling

### Recommended rates

```ts
// instrumentation-client.ts
Sentry.init({
  // ...
  replaysSessionSampleRate: 0.001,  // 0.1% of all sessions — keeps quota safe
  replaysOnErrorSampleRate: 1.0,    // 100% of sessions that produce an error
})
```

The 0.1% + 100%-on-error combination is the webstack default for Sentry Cloud Free. It stays well within the free-tier replay quota. Raise `replaysSessionSampleRate` only for proactive UX research sessions, then reset it.

### PII reduction

Sentry Replay defaults to aggressive masking: all text is replaced with asterisks (`*`), all form inputs are masked. These defaults are correct for a webstack project and should not be weakened without explicit review.

```ts
Sentry.replayIntegration({
  maskAllText: true,       // default: true — keep enabled
  maskAllInputs: true,     // default: true — keep enabled
  blockAllMedia: false,    // false is safe for most apps; set true if images contain PII
})
```

For safe elements (page titles, static labels), use `unmask` rather than disabling global masking:

```ts
replayIntegration({ maskAllText: true, unmask: ['[data-sentry-unmask]'] })
```

Add `data-sentry-unmask` to JSX elements with known-safe content.

### Network and console capture

Network request/response body capture is opt-in — bodies are not sent to Sentry unless you configure `networkDetailAllowUrls`. Leave it empty (`[]`). Do not add endpoints that return user data: capturing response bodies from authenticated endpoints will send user data to Sentry.

Console capture (errors and warnings) is on by default. Filter sensitive calls at the log site rather than disabling console capture globally.

### `beforeAddRecordingEvent` hook

Use the `beforeAddRecordingEvent` hook to drop specific recording events before transmission:

```ts
Sentry.replayIntegration({
  beforeAddRecordingEvent: (event) => {
    if (event.data.tag === 'console' && event.data.payload.level === 'verbose') {
      return null
    }
    return event
  },
})
```

## Anti-patterns

**Sending every error to Sentry.** Validation errors, expected 4XX responses, and user-input errors are application state, not Sentry events. Calling `Sentry.captureException` on a 400 from the backend floods Sentry with noise, exhausts the monthly quota, and buries real failures. Only capture unexpected system failures.

**Assigning `SENTRY_AUTH_TOKEN` a `NEXT_PUBLIC_` prefix.** `NEXT_PUBLIC_SENTRY_DSN` is safe in the browser bundle — it is a receive-only ingest endpoint. `SENTRY_AUTH_TOKEN` is an administrative secret. Never expose it in client-side code.

**Throwing all fetch errors up to the nearest Error Boundary.** A 503 or timeout should show an inline retry UI within the feature slice, not crash the route segment. Reserve Error Boundary escalation for unrecoverable render errors; handle fetch errors with typed result objects.

**Disabling PII masking in Replay for convenience.** `maskAllText: false` exposes every text node — user names, emails, form values — to anyone with Sentry dashboard access. Keep global masking enabled and use `unmask` selectively for known-safe elements.

**Committing `SENTRY_AUTH_TOKEN` to source.** The token grants write access to your Sentry project. Keep it in Vercel environment variables or CI secrets — never in `.env.local` or `.env.sentry-build-plugin` in the repository. Add `.env.sentry-build-plugin` to `.gitignore`.

**Omitting `deleteSourcemapsAfterUpload: true` in `withSentryConfig`.** Without it, Vercel serves `.map` files from the CDN and anyone can download your original TypeScript source. Always set it in production configurations.

**Setting `replaysOnErrorSampleRate` below 1.0.** Subsampling error replays means some production errors never produce a replay. The entire value of error-triggered replay is that it fires on every error — keep it at 1.0.

## Sources

- **Sentry MCP overview:** https://docs.sentry.io/ai/mcp/ — _authoritative_
- **Sentry Next.js setup guide:** https://docs.sentry.io/platforms/javascript/guides/nextjs/ — _authoritative_
- **Sentry Session Replay privacy:** https://docs.sentry.io/platforms/javascript/session-replay/privacy/ — _authoritative_
- **sentry-mcp AGENTS.md:** https://github.com/getsentry/sentry-mcp/blob/main/AGENTS.md — _community: Sentry MCP repo agent guide_
- **Sentry source map documentation:** https://docs.sentry.io/platforms/javascript/sourcemaps/ — _authoritative_
- **Sentry withSentryConfig API:** https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/ — _authoritative_
- **Next.js instrumentation hooks:** https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation — _authoritative: Next.js 16 server-side init pattern_

Last verified: 2026-05-04 (Sentry SDK 8.X / Next.js 16.X / React 19).
