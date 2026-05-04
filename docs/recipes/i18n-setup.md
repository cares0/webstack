# Recipe — i18n setup (next-intl)

> Setup walkthrough for activating next-intl in webstack's frontend. Triggered when init's "Internationalization" question is answered Yes (`manifest.optional_integrations.i18n=true`).
> Reference doc: `docs/frontend/i18n.md`.

## What this recipe activates

**next-intl 3.X** — path-prefix locale routing (`/en/dashboard`, `/ko/dashboard`), Server + Client translations, ICU MessageFormat. All locale logic runs in middleware and the `[locale]` segment.

## Pre-conditions

- FE worktree on `main` (or feature branch from `/webstack:feature`).
- FSD-lite scaffold present: `src/app/`, `src/features/`, `src/shared/`.
- `next.config.ts` exists (created by init). Node.js ≥ 20, pnpm ≥ 9.

## Step 1 — Install

```bash
pnpm add next-intl
```

No peer deps beyond Next.js 16 (already present).

## Step 2 — Folder structure

```
messages/
├── en.json              # English messages
└── ko.json              # Korean messages
src/i18n/
├── routing.ts           # defineRouting — locales + defaultLocale
├── request.ts           # getRequestConfig — per-request locale resolution
└── navigation.ts        # createNavigation — locale-aware Link, useRouter, redirect
middleware.ts            # project root (next to package.json)
```

Move all pages under `src/app/[locale]/` — every route segment lives inside the locale param.

## Step 3 — middleware.ts

Create `middleware.ts` at the project root (same level as `package.json`):

```ts
import createMiddleware from 'next-intl/middleware'
import { routing } from './src/i18n/routing'

export default createMiddleware(routing)

export const config = {
  matcher: '/((?!api|trpc|_next|_vercel|.*\\..*).*)',
}
```

The matcher skips API routes, static assets, and Next.js internals.

`src/i18n/routing.ts` — single source of truth for locale config:

```ts
import { defineRouting } from 'next-intl/routing'

export const routing = defineRouting({
  locales: ['en', 'ko'],
  defaultLocale: 'en',
})
```

## Step 4 — `[locale]` segment

`src/i18n/request.ts`:

```ts
import { getRequestConfig } from 'next-intl/server'
import { hasLocale } from 'next-intl'
import { routing } from './routing'

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale
  return { locale, messages: (await import(`../../messages/${locale}.json`)).default }
})
```

`src/app/[locale]/layout.tsx`:

```tsx
import { NextIntlClientProvider, hasLocale } from 'next-intl'
import { notFound } from 'next/navigation'
import { setRequestLocale, getMessages } from 'next-intl/server'
import { routing } from '@/i18n/routing'

export const generateStaticParams = () =>
  routing.locales.map((locale) => ({ locale }))

export default async function LocaleLayout({ children, params }) {
  const { locale } = await params
  if (!hasLocale(routing.locales, locale)) notFound()
  setRequestLocale(locale)
  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider messages={await getMessages()}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

`generateStaticParams` pre-renders all locale variants. `setRequestLocale` must be called in every layout and page that uses next-intl in static context.

Wrap `next.config.ts` so `src/i18n/request.ts` is registered:

```ts
import createNextIntlPlugin from 'next-intl/plugin'
const withNextIntl = createNextIntlPlugin()
export default withNextIntl(/* your existing NextConfig */)
```

`src/i18n/navigation.ts`:

```ts
import { createNavigation } from 'next-intl/navigation'
import { routing } from './routing'

export const { Link, redirect, usePathname, useRouter } =
  createNavigation(routing)
```

Import `Link` and `useRouter` from `@/i18n/navigation` everywhere — never from `next/link` or `next/navigation`.

## Step 5 — First messages

`messages/en.json`:

```json
{
  "Common": {
    "loading": "Loading…",
    "error": "Something went wrong.",
    "retry": "Retry"
  },
  "Nav": {
    "home": "Home",
    "about": "About"
  }
}
```

`messages/ko.json`:

```json
{
  "Common": {
    "loading": "로딩 중…",
    "error": "오류가 발생했습니다.",
    "retry": "다시 시도"
  },
  "Nav": {
    "home": "홈",
    "about": "소개"
  }
}
```

Keep namespace keys PascalCase (`Common`, `Nav`) to avoid collisions with feature-scoped messages.

## Step 6 — Component usage

**Server Component** (default):

```tsx
import { getTranslations, setRequestLocale } from 'next-intl/server'

export default async function HomePage({ params }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('Nav')
  return <h1>{t('home')}</h1>
}
```

**Client Component** (`'use client'`):

```tsx
'use client'
import { useTranslations } from 'next-intl'

export function RetryButton() {
  const t = useTranslations('Common')
  return <button>{t('retry')}</button>
}
```

Rule: `getTranslations` (async) in Server Components/Actions; `useTranslations` (hook) in Client Components.

## Step 7 — RTL handling (if applicable)

Skip if no RTL locales (`ar`, `he`, `fa`) are in scope.

Add `dir` to `<html>` in `src/app/[locale]/layout.tsx`:

```tsx
const RTL_LOCALES = new Set(['ar', 'he', 'fa'])
const dir = RTL_LOCALES.has(locale) ? 'rtl' : 'ltr'
return <html lang={locale} dir={dir}>...</html>
```

Use Tailwind logical properties throughout so layouts mirror in RTL automatically:

| Avoid (physical) | Use (logical) |
|---|---|
| `ml-*` / `mr-*` | `ms-*` / `me-*` |
| `pl-*` / `pr-*` | `ps-*` / `pe-*` |
| `text-left` / `text-right` | `text-start` / `text-end` |

## Step 8 — Verify

```bash
pnpm dev
```

- `http://localhost:3000/` → redirects to `/en/` (middleware default).
- `http://localhost:3000/en` → 200, English strings.
- `http://localhost:3000/ko` → 200, Korean strings.

Network tab: no `messages/*.json` in the client bundle — Server Component messages are inlined in HTML.

## Step 9 — manifest flag ON

```yaml
# .webstack/manifest.yaml
optional_integrations:
  i18n: true
```

```bash
git -C <parent-dir> add .webstack/manifest.yaml && git -C <parent-dir> commit -m "chore: enable i18n integration"
```

This flag signals to `/webstack:feature` and `/webstack:deploy` that i18n is active.

## Reference doc

`docs/frontend/i18n.md` — ICU MessageFormat (pluralization, select, date/number), FSD message location convention, lazy loading, anti-patterns, navigation primitives.

## Sources

- **next-intl App Router with i18n routing:** https://next-intl.dev/docs/getting-started/app-router/with-i18n-routing — _authoritative_
- **next-intl App Router base setup:** https://next-intl.dev/docs/getting-started/app-router — _authoritative_
- **Next.js App Router internationalization:** https://nextjs.org/docs/app/building-your-application/routing/internationalization — _authoritative_
- **next-intl routing API:** https://next-intl.dev/docs/routing — _authoritative_
- **Tailwind CSS logical properties:** https://tailwindcss.com/docs/margin#using-logical-properties — _community: Tailwind Labs_

Last verified: 2026-05-04 (next-intl 3.X / Next.js 16.X).
