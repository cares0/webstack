# Frontend performance (Core Web Vitals)

> Reference for build-fe SubAgent and frontend-implementer.
> Core Web Vitals (LCP/INP/CLS) measurement and improvement for webstack's Next.js 16 + Vercel Hobby stack.

## What is FE performance

Frontend performance is measured through **Core Web Vitals** — real-user metrics that correlate with user experience and search ranking, measured at the **75th percentile** across mobile and desktop.

| Metric | Full name | What it measures | Good threshold |
|--------|-----------|-----------------|----------------|
| **LCP** | Largest Contentful Paint | Loading speed of above-the-fold content | ≤ 2.5 s |
| **INP** | Interaction to Next Paint | Responsiveness to every user gesture | ≤ 200 ms |
| **CLS** | Cumulative Layout Shift | Visual stability of the page | ≤ 0.1 |

**LCP** fires when the largest above-the-fold element (hero image, heading) becomes visible. Poor LCP comes from slow server responses, render-blocking resources, or un-optimized images.

**INP** replaced FID in March 2024. It measures the full processing time of every interaction (click, tap, keypress) across the page visit — not just the first. Long main-thread JS tasks are the primary cause.

**CLS** accumulates whenever a visible element shifts after layout. Common causes: images without explicit dimensions, dynamically injected banners, fonts that shift surrounding text.

## Why measure first

Optimization without measurement is guesswork. webstack uses **Vercel Speed Insights** as its primary field-measurement tool:

- Available on the **Hobby (free) tier** — enable in the Vercel dashboard, no code change required.
- Collects **Real User Monitoring (RUM)** across real networks and devices.
- Reports LCP, INP, CLS, FCP, and TTFB by route, country, and device at P75–P99.
- Tracks preview and production environments — compare a feature branch against main before merging.

Vercel's build pipeline injects the tracking snippet automatically. Access the dashboard under **Speed Insights** in the project sidebar.

For CI regression detection, use Lighthouse via `@lhci/cli`. Lab scores are directionally useful but cannot replace RUM — they do not capture real network or device variance.

## webstack convention

Four Next.js primitives cover the majority of performance optimizations. Adopt all four consistently.

### `next/image`

Replace every `<img>` with `next/image`. It provides automatic WebP/AVIF conversion, responsive `srcset`, lazy loading by default, and aspect-ratio reservation that prevents CLS.

Convention:

- Explicit `width` + `height` for all images with known dimensions.
- `priority` on the above-the-fold image (hero, logo, main product shot).
- `placeholder="blur"` + `blurDataURL` on hero images for a LQIP preview.
- `sizes` on all responsive images to generate the full `srcset`.

### `next/font`

All font loading must go through `next/font/google` or `next/font/local`. Fonts are self-hosted at build time — **no requests are sent to Google Fonts at runtime**. The module eliminates the `fonts.googleapis.com` DNS + TLS round trip, defaults to `display: 'swap'` (FOIT prevention), injects a `<link rel="preload">`, and sets `adjustFontFallback: true` to compute a metric-matched fallback that minimizes CLS from the font swap.

### Dynamic import (`next/dynamic`)

Use `next/dynamic` for components that:

- Are below the fold or conditionally shown (modals, drawers, tooltips).
- Depend on large third-party libraries (rich text editors, chart libraries, date pickers).
- Do not need to be included in the initial JS bundle.

`next/dynamic` wraps React's `React.lazy` + `<Suspense>` with SSR control. Pair it with a `loading` fallback to preserve layout space and avoid CLS.

### Bundle analyzer

Run `@next/bundle-analyzer` to understand bundle composition before shipping. The target for initial JS is **< 200 KB** (compressed). Keep this as a recurring check — new dependencies silently inflate the bundle.

## LCP — Largest Contentful Paint

**Target: < 2.5 s at P75.**

LCP is most directly impacted by image loading and TTFB. The patterns below address the most common causes.

### Hero image — `priority` + `blur` placeholder

The above-the-fold image must load as fast as possible. `priority` injects a `<link rel="preload">` into `<head>` and disables lazy loading:

```tsx
// src/widgets/hero/ui/HeroBanner.tsx
import Image from 'next/image'

export function HeroBanner() {
  return (
    <section className="relative h-[480px] w-full">
      <Image
        src="/images/hero.jpg"
        alt="Product hero"
        fill priority
        placeholder="blur"
        blurDataURL="data:image/jpeg;base64,..."
        sizes="100vw"
        className="object-cover"
      />
    </section>
  )
}
```

Set `priority` on the **single** largest above-the-fold image per route only — multiple `priority` props compete for bandwidth.

### Font preload

`next/font` injects a `<link rel="preload">` automatically. Remove any `@font-face` rules pointing to a CDN — convert them to `next/font/local`.

### Server-render above-the-fold content

LCP content must be in the initial HTML. Server Components stream HTML before client JS executes, so RSC-rendered content is always in the initial response. Never fetch LCP content in `useEffect` without a server prefetch.

### TTFB — the upstream factor

The Oracle Always Free backend can have cold starts > 300 ms, which directly raises LCP. Cache responses at the Next.js Data Cache layer via `'use cache'` + `cacheLife('hours')` so the Vercel function does not call the backend on every request. See `docs/frontend/caching-strategies.md`.

## INP — Interaction to Next Paint

**Target: ≤ 200 ms at P75.**

INP replaced FID in March 2024. It measures every interaction (click, keypress, tap) across the full page visit and reports the worst-case value. High INP means the main thread is blocked when the user acts.

### Split long JavaScript tasks

Tasks > 50 ms on the main thread push INP above threshold. Common sources: hydrating a large client bundle, rendering hundreds of list items in one pass, heavy event handler computations. React 19's concurrent renderer yields between component renders when it sees pending input — small Client Components and `<Suspense>` boundaries help the scheduler insert yield points.

### `startTransition` and `useDeferredValue`

Wrap non-urgent updates in `startTransition` so React treats them as interruptible — the browser can service a higher-priority gesture first:

```tsx
'use client'
import { useState, startTransition, useDeferredValue } from 'react'

export function FilterableList({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('')
  const [filtered, setFiltered] = useState(items)
  const deferredFiltered = useDeferredValue(filtered)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value)
    startTransition(() => {
      setFiltered(items.filter((i) => i.name.includes(e.target.value)))
    })
  }

  return (
    <>
      <input value={query} onChange={handleChange} />
      <ul>
        {deferredFiltered.map((item) => <li key={item.id}>{item.name}</li>)}
      </ul>
    </>
  )
}
```

`useDeferredValue` passes the previous list to the expensive child until the transition commits, keeping the input's INP well below 200 ms.

### Minimize Client Component surface area

Every `'use client'` boundary adds hydration cost. The directive belongs on the smallest interactive leaf, not a parent layout — reducing hydrated JS lowers the INP risk window at load. See `docs/frontend/server-components.md`.

## CLS — Cumulative Layout Shift

**Target: ≤ 0.1 at P75.**

CLS accumulates whenever a visible element shifts after layout. Three common sources to eliminate:

### Explicit image dimensions

Every `<Image>` needs either explicit `width` + `height` props or `fill` with a positioned parent. Next.js emits an inline `aspect-ratio` style that reserves space before the file loads:

```tsx
<Image src="/avatar.png" width={64} height={64} alt="User avatar" />

// fill — parent must be position:relative/fixed/absolute
<div className="relative h-48 w-full">
  <Image src="/banner.png" fill alt="Banner" className="object-cover" />
</div>
```

Static imports (`import logo from './logo.svg'`) provide intrinsic dimensions automatically — no explicit width/height needed.

### Font swap without metric-matched fallback

`next/font` defaults to `display: 'swap'` and `adjustFontFallback: true`. The adjusted fallback matches `size-adjust`, `ascent-override`, and `descent-override` so the font-swap shift is sub-pixel. Never set `adjustFontFallback: false` without verifying CLS in Speed Insights.

### Dynamic content injection

Do not insert elements above existing content after load. Common culprits: cookie banners injected below the header, ads without reserved height, skeleton loaders taller or shorter than the real content. Reserve space with `min-height`, or render server-side so the content is in the initial HTML. Skeleton dimensions must match the content they replace exactly.

## Web Vitals API reporting

### Automatic via Vercel Speed Insights

When Speed Insights is enabled, Vercel injects its beacon automatically — no `web-vitals` install needed. The dashboard reports LCP, INP, CLS, FCP, and TTFB per route.

### Manual reporting with the `web-vitals` library

To also send metrics to your own backend, install the library and wire it into a small client component:

```bash
pnpm add web-vitals
```

```tsx
// src/shared/lib/WebVitalsInit.tsx
'use client'

import { useEffect } from 'react'
import { onCLS, onINP, onLCP, onFCP, onTTFB, type Metric } from 'web-vitals'

function send(metric: Metric) {
  navigator.sendBeacon('/api/vitals', JSON.stringify({
    name: metric.name,
    value: metric.value,
    rating: metric.rating, // 'good' | 'needs-improvement' | 'poor'
  }))
}

export function WebVitalsInit() {
  useEffect(() => {
    onCLS(send); onINP(send); onLCP(send); onFCP(send); onTTFB(send)
  }, [])
  return null
}
```

Mount `<WebVitalsInit />` inside `<body>` in `app/layout.tsx`. The `metric.rating` field (`'good'` | `'needs-improvement'` | `'poor'`) makes pass/fail aggregation straightforward.

Wire up a minimal Route Handler to receive the beacon:

```ts
// app/api/vitals/route.ts
import { NextRequest, NextResponse } from 'next/server'
export async function POST(req: NextRequest) {
  console.log('[WebVital]', await req.json())
  return NextResponse.json({ ok: true })
}
```

## Bundle analyzer

### Setup

```bash
pnpm add -D @next/bundle-analyzer
```

```ts
// next.config.ts
import withBundleAnalyzer from '@next/bundle-analyzer'
import type { NextConfig } from 'next'

const nextConfig: NextConfig = { cacheComponents: true }  // enable 'use cache' directives (see caching-strategies.md)

export default withBundleAnalyzer({ enabled: process.env.ANALYZE === 'true' })(nextConfig)
```

> The `next.config.ts` snippets across these docs are partial. The canonical merged config — composing `withBundleAnalyzer`, `withSentryConfig` (see `docs/frontend/error-monitoring.md`), the next-intl plugin (`docs/frontend/i18n.md`), and `next-safe` headers (`docs/frontend/frontend-security.md`) around a single base `NextConfig` — is assembled by `/webstack:init`. Treat each snippet here as one layer of that wrapper chain, not a standalone file.

Add `"analyze": "ANALYZE=true next build"` to `package.json` scripts and run `pnpm analyze`. The **client** treemap is the relevant one for performance.

### What to look for

**Target: < 200 KB initial JS (compressed).** Look for:

- **Unexpectedly large modules** — a chart library at route level instead of behind `next/dynamic`.
- **Duplicate dependencies** — two versions of the same package.
- **Full library imports** — `import _ from 'lodash'` (70 KB) vs `import pick from 'lodash/pick'` (~1 KB).

Use `next/dynamic` to move large components out of the initial bundle:

```tsx
import dynamic from 'next/dynamic'

// lazy-loaded only when the edit modal opens
const RichTextEditor = dynamic(
  () => import('@/shared/ui/RichTextEditor').then((m) => m.RichTextEditor),
  { loading: () => <div className="h-48 animate-pulse bg-muted rounded" /> }
)
```

ShadCN components already import named icons from `lucide-react` (tree-shakeable). Follow the same named-import pattern for all icon and utility libraries.

## Code splitting

### Route-based — automatic

Next.js App Router splits at each route segment boundary (`page.tsx`, `layout.tsx`, `loading.tsx`) automatically. JS on `/dashboard` is not loaded on `/marketing` — no configuration needed.

### Component-level — `next/dynamic`

Within a single route, defer heavyweight components with `next/dynamic`:

```tsx
import dynamic from 'next/dynamic'
import { Skeleton } from '@/shared/ui/skeleton'

// ~80KB chart library excluded from initial bundle
const RevenueChart = dynamic(
  () => import('./RevenueChart').then((m) => m.RevenueChart),
  {
    loading: () => <Skeleton className="h-64 w-full" />,
    ssr: false, // chart library requires window
  }
)
```

Set `ssr: false` only for components that truly need browser APIs. For large-but-SSR-compatible components, keep SSR on.

### Suspense boundaries

Suspense boundaries give independent control over fallbacks and enable React 19 streaming — content above the boundary flushes to the browser without waiting for the deferred component below it:

```tsx
// src/app/dashboard/page.tsx (Server Component)
import { Suspense } from 'react'
import { DashboardHeader } from '@/widgets/dashboard/ui/DashboardHeader'
import { AnalyticsDashboard } from '@/widgets/analytics/ui/AnalyticsDashboard'
import { Skeleton } from '@/shared/ui/skeleton'

export default function DashboardPage() {
  return (
    <>
      <DashboardHeader />  {/* flushes immediately */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <AnalyticsDashboard />  {/* streams in once ready */}
      </Suspense>
    </>
  )
}
```

## Anti-patterns

**Adding `'use client'` to every component.** `'use client'` at page or layout level forces the entire subtree into the client bundle, eliminating RSC benefits and inflating initial JS. Put the directive on the smallest interactive leaf. See `docs/frontend/server-components.md`.

**Importing large libraries indiscriminately.** A top-level `import _ from 'lodash'` includes the entire library in the initial bundle. Use named imports for tree-shakeable packages and `next/dynamic` for non-tree-shakeable ones. Run `pnpm analyze` before merging any PR that adds a dependency.

**Disabling image optimization.** `unoptimized={true}` disables WebP/AVIF conversion and `srcset` generation, worsening LCP directly. Only use it for images that require auth headers. Never set `images: { unoptimized: true }` globally.

**Blocking fonts.** A raw `<link href="https://fonts.googleapis.com/...">` in `app/layout.tsx` adds a cross-origin round trip to the critical path and causes FOIT/FOUT. Always use `next/font/google` or `next/font/local` — fonts are self-hosted at build time.

**`priority` on every image.** Setting `priority` on multiple images causes simultaneous preloads that compete for bandwidth and delay the true LCP element. Reserve it for the single most important above-the-fold image per route.

**Missing `sizes` on responsive images.** Without `sizes`, the browser assumes 100vw and may download a 1920px image on a 375px phone. Always provide a `sizes` string matching actual rendered widths at each breakpoint.

**No `Suspense` boundary around dynamic imports.** Without a `loading` fallback, `next/dynamic` renders nothing until the chunk arrives, causing the container to collapse to zero and then jump — CLS. Always provide a `loading` fallback whose height matches the content.

## Sources

- **Core Web Vitals:** https://web.dev/articles/vitals — _community: web.dev / Google; defines LCP/INP/CLS thresholds and measurement guidance_
- **Next.js docs — Image Component (v16.2.4):** https://nextjs.org/docs/app/api-reference/components/image — _authoritative; priority, sizes, placeholder, fill props_
- **Next.js docs — Font Module (v16.2.4):** https://nextjs.org/docs/app/api-reference/components/font — _authoritative; next/font/google, next/font/local, display:swap, adjustFontFallback_
- **Vercel Speed Insights:** https://vercel.com/docs/speed-insights — _authoritative; RUM collection, Hobby tier availability, dashboard metrics_
- **GoogleChrome/web-vitals library:** https://github.com/GoogleChrome/web-vitals — _community: Google Chrome team; onLCP, onINP, onCLS API, sendBeacon reporting pattern_

Last verified: 2026-06-22 (Next.js 16.2.4 / React 19 / Vercel Speed Insights / Web Vitals).
