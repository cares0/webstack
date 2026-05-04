# Frontend security (CSP nonce + XSS + cookies)

> Reference for build-fe SubAgent and frontend-implementer and security-auditor SubAgent.
> Strict CSP with nonces, XSS prevention with DOMPurify, and cookie security for webstack's Next.js 16 + RSC frontend.

---

## What is FE security in webstack

Frontend security in webstack is a set of layered browser-side defenses against the most common client-facing attack classes. The layers fail independently so a gap in one does not collapse the posture.

**Four layers:** (1) Transport — HTTPS + HSTS + `upgrade-insecure-requests`. (2) Content Security Policy — per-request nonce blocks injected scripts and styles. (3) XSS sanitization — React auto-encoding + DOMPurify for rich-text paths. (4) Cookie security — `httpOnly; Secure; SameSite` for session and refresh tokens; access tokens in memory only.

CSP and XSS sanitization address **A03 Injection** (XSS). Cookie security addresses **A07 Identification & Authentication Failures** (session theft). See [`cross-cutting/owasp-top10-cheatsheet.md`](../cross-cutting/owasp-top10-cheatsheet.md) for the full stack-wide mapping.

---

## Why CSP nonce

Content Security Policy is an HTTP response header that tells the browser which script and style sources are trusted. Without CSP, any injected script — from an XSS flaw, compromised CDN, or browser extension — executes with full DOM access.

A **strict CSP** eliminates `'unsafe-inline'` and `'unsafe-eval'`. Both undermine XSS protection: an attacker who can inject HTML can inject an inline script or call `eval()`. Allowlist-based CSP is routinely bypassed by injecting through trusted domains (JSONP endpoints, open redirects on CDN origins).

A **nonce** is a cryptographically random single-use token minted server-side per request. It appears in the `Content-Security-Policy` header as `'nonce-<value>'` and as an attribute on every trusted `<script>` and `<style>` tag. The browser executes a script only when its nonce matches the header value — injected markup cannot know the current nonce.

**Trade-off with static rendering.** Nonces require per-request rendering; static pages and CDN-cached HTML cannot carry them. PPR is incompatible with nonce-based CSP for the static shell. For static exports, use hash-based SRI (`experimental.sri` in `next.config.ts`).

---

## webstack convention — middleware CSP nonce

webstack uses Next.js 16's `proxy.ts` (the renamed `middleware.ts`) to generate a per-request nonce, write it to the `Content-Security-Policy` response header, and forward it via a custom `x-nonce` request header so Server Components can read it.

### `proxy.ts` — generate and inject

```ts
// proxy.ts  (project root)
import { NextRequest, NextResponse } from 'next/server'

export function proxy(request: NextRequest): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64')
  const isDev = process.env.NODE_ENV === 'development'

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ''};
    style-src 'self' 'nonce-${nonce}'${isDev ? " 'unsafe-inline'" : ''};
    img-src 'self' blob: data:;
    font-src 'self';
    connect-src 'self';
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-ancestors 'none';
    upgrade-insecure-requests;
  `.replace(/\s{2,}/g, ' ').trim()

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('x-nonce', nonce)            // read by layout via headers()
  requestHeaders.set('Content-Security-Policy', cspHeader)

  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set('Content-Security-Policy', cspHeader) // sent to browser
  return response
}

export const config = {
  matcher: [
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
}
```

The nonce is written to both `requestHeaders` (so layout reads it via `headers()`) and `response.headers` (browser receives CSP). `isDev` adds `'unsafe-eval'` in development only — React uses `eval()` for error stack reconstruction.

### Layout — read nonce via `headers()`

```tsx
// src/app/layout.tsx
import { headers } from 'next/headers'
import Script from 'next/script'

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get('x-nonce') ?? ''

  return (
    <html lang="en">
      <body>
        {children}
        <Script
          src="https://www.googletagmanager.com/gtag/js"
          strategy="afterInteractive"
          nonce={nonce}
        />
      </body>
    </html>
  )
}
```

Next.js 16 automatically propagates the nonce to its own framework scripts (React runtime, page bundles, inline hydration) when `Content-Security-Policy` contains `'nonce-...'`. You do not need to add it to every Next.js-generated tag.

### Force dynamic rendering where needed

```tsx
// src/app/some-page/page.tsx
import { connection } from 'next/server'

export default async function SomePage() {
  await connection() // opts this route into per-request rendering
  // ...
}
```

Any page that calls `cookies()` or `headers()` is already dynamic and requires no extra step.

---

## Strict CSP

Full strict CSP for webstack's Next.js 16 frontend:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-{NONCE}' 'strict-dynamic';
  style-src 'self' 'nonce-{NONCE}';
  img-src 'self' blob: data:;
  font-src 'self';
  connect-src 'self';
  object-src 'none';
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
  upgrade-insecure-requests;
```

### Directive reference

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `default-src` | `'self'` | Catch-all; same-origin only unless overridden. |
| `script-src` | `'self' 'nonce-{NONCE}' 'strict-dynamic'` | `'strict-dynamic'` propagates trust to dynamically loaded chunks — no need to list every hash. No `'unsafe-inline'`. |
| `style-src` | `'self' 'nonce-{NONCE}'` | Tailwind v4 extracts to static files at build time; complies naturally. |
| `img-src` | `'self' blob: data:` | Covers `next/image` data-URI placeholders and canvas-to-blob. |
| `connect-src` | `'self'` | Restricts `fetch`, XHR, WebSocket. Extend with backend URL in production. |
| `object-src` | `'none'` | Blocks `<object>`, `<embed>` — deprecated plugin vectors. |
| `base-uri` | `'self'` | Prevents base tag injection redirecting relative URLs to an attacker's origin. |
| `frame-ancestors` | `'none'` | Blocks framing; equivalent to `X-Frame-Options: DENY`. |
| `upgrade-insecure-requests` | — | Browser upconverts HTTP sub-resource URLs to HTTPS. |

**Report-Only rollout.** Before enforcing in production, swap `Content-Security-Policy` for `Content-Security-Policy-Report-Only` and add `Reporting-Endpoints: csp="https://api.example.com/csp-report"`. Enforce once the violation log is quiet.

---

## next-safe — header library

`next-safe` generates a sensible default bundle of HTTP security response headers for Next.js applications in a single call, covering CSP, Permissions Policy, Referrer Policy, `X-Content-Type-Options`, `X-Frame-Options`, and `X-XSS-Protection`.

```bash
pnpm add next-safe
```

```ts
// next.config.ts
import type { NextConfig } from 'next'
const nextSafe = require('next-safe')
const isDev = process.env.NODE_ENV !== 'production'

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: '/:path*', headers: nextSafe({ isDev }) }]
  },
}
export default nextConfig
```

### Default header bundle

| Header | Default |
|--------|---------|
| `Content-Security-Policy` | Strict policy; `isDev: true` relaxes inline restrictions for HMR |
| `Permissions-Policy` | Empty (deny all features unless granted) |
| `Referrer-Policy` | `no-referrer` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |

### Combining with the nonce pattern

`next-safe` writes headers statically — it cannot generate per-request nonces. Delegate CSP to `proxy.ts`; keep the rest in `next-safe`:

```ts
headers: nextSafe({ isDev, contentSecurityPolicy: false }),
```

---

## XSS prevention

Cross-site scripting (XSS) injects malicious scripts into pages viewed by other users. React auto-encodes JSX interpolated values before DOM insertion, preventing the majority of reflected and stored XSS through standard JSX paths. The gap: `dangerouslySetInnerHTML` bypasses encoding entirely.

### DOMPurify via `isomorphic-dompurify`

Never pass user input directly to `dangerouslySetInnerHTML`:

```tsx
// WRONG
return <div dangerouslySetInnerHTML={{ __html: userContent }} />
```

When rendering trusted-but-potentially-unsafe HTML (CMS rich-text, markdown output), sanitize first:

```bash
pnpm add isomorphic-dompurify
```

`isomorphic-dompurify` wraps DOMPurify to work in both browser and Node.js / RSC environments where `document` is absent.

#### Server Component (RSC)

```tsx
// src/entities/article/ui/ArticleBody.tsx
import DOMPurify from 'isomorphic-dompurify'

export function ArticleBody({ htmlContent }: { htmlContent: string }) {
  const clean = DOMPurify.sanitize(htmlContent, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li',
                   'h2', 'h3', 'h4', 'blockquote', 'a', 'code', 'pre'],
    ALLOWED_ATTR: ['href', 'target', 'rel'],
  })
  return <div className="prose prose-neutral" dangerouslySetInnerHTML={{ __html: clean }} />
}
```

#### Client Component

```tsx
'use client'
// src/features/rich-text-preview/ui/RichTextPreview.tsx
import DOMPurify from 'isomorphic-dompurify'

export function RichTextPreview({ html }: { html: string }) {
  const clean = DOMPurify.sanitize(html)
  return <div dangerouslySetInnerHTML={{ __html: clean }} />
}
```

#### Key options

| Option | Purpose |
|--------|---------|
| `ALLOWED_TAGS` | Restrict to a safe element allowlist; default allows a broad set. |
| `ALLOWED_ATTR` | Restrict allowed attributes. |
| `FORCE_BODY` | Wraps output in `<body>` to avoid browser edge-cases with certain root nodes. |
| `USE_PROFILES: { html: true }` | Apply the built-in HTML-safe preset. |

### Validate `href` against `javascript:` URIs

React does not strip `javascript:` href values. Validate user-controlled links:

```ts
// src/shared/lib/url.ts
export function isSafeHref(href: string): boolean {
  return href.startsWith('https://') || href.startsWith('/')
}
```

```tsx
return isSafeHref(href) ? <a href={href}>{label}</a> : <span>{label}</span>
```

---

## Cookie security

Session and refresh tokens are the highest-value credentials in the application. Cookie attributes are the last line of defense once XSS fires.

```
Set-Cookie: __Host-session=<token>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900
Set-Cookie: __Host-refresh=<token>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=1209600
```

### Attribute reference

| Attribute | Purpose |
|-----------|---------|
| `HttpOnly` | Blocks `document.cookie` from JavaScript. XSS cannot read the token. |
| `Secure` | Transmits cookie over HTTPS only. Required in production. |
| `SameSite=Lax` | Sent on same-site requests and top-level cross-site navigations. Blocks CSRF while preserving OAuth redirects. Use for session cookies. |
| `SameSite=Strict` | Never sent on cross-site requests. Use for refresh tokens. |
| `SameSite=None; Secure` | Cross-origin embedded flows only — never without an explicit reason. |
| `Path=/` | Scopes cookie to the whole application. |
| `Max-Age` | Explicit TTL. Refresh tokens require one; access tokens can be session-duration. |

### `__Host-` prefix

`__Host-` locks a cookie to the exact host that set it and requires `Secure`, `Path=/`, and no `Domain` attribute, preventing leakage to subdomains (subdomain takeover) and alternative ports:

```
Set-Cookie: __Host-session=<token>; HttpOnly; Secure; SameSite=Lax; Path=/
```

Use `__Host-` for all webstack session and refresh token cookies.

### Token storage summary

| Token | Where | Why |
|-------|-------|-----|
| Access token (15 min) | React state / memory | Short TTL limits blast radius of XSS. Never `localStorage`. |
| Refresh token (14 days) | `__Host-refresh; HttpOnly; Secure; SameSite=Strict` | JavaScript-inaccessible; rotated on every use. |

Cookies are set by the Spring Boot backend on `/api/auth/token` responses. The frontend never writes session or refresh cookies — it reads the access token from the JSON body and holds it in memory.

---

## OWASP A03/A07 mapping

See [`cross-cutting/owasp-top10-cheatsheet.md`](../cross-cutting/owasp-top10-cheatsheet.md) for the full stack-wide (FE + BE + Infra) breakdown of every OWASP category. This section focuses on the FE-layer controls.

### A03 — Injection (Cross-Site Scripting)

XSS is classified under A03: untrusted data injected into an HTML context the browser interprets as markup.

| Threat vector | webstack FE control |
|---------------|---------------------|
| Reflected XSS via JSX interpolation | React auto-encodes `{variable}` — no action needed. |
| Stored XSS via rich-text / CMS content | `DOMPurify.sanitize()` before `dangerouslySetInnerHTML`. |
| DOM-based XSS via `javascript:` href | `isSafeHref()` validation before rendering user-provided links. |
| Injected script execution | Strict CSP nonce blocks scripts without the current-request nonce. |
| Server Action input injection | Zod schema parses every Server Action input before the application layer. |

### A07 — Identification & Authentication Failures

Session token theft via XSS leads to authentication failure — the attacker assumes the victim's identity.

| Threat vector | webstack FE control |
|---------------|---------------------|
| Token stolen via XSS (`document.cookie`) | `HttpOnly` — JavaScript cannot access the cookie. |
| Token transmitted over HTTP | `Secure` — browser refuses to send on non-HTTPS. |
| CSRF using session cookie | `SameSite=Lax` / `Strict` — browser withholds cookie on cross-origin requests. |
| Token in `localStorage` stolen via XSS | Access tokens in memory only; refresh tokens in `HttpOnly` cookie. |
| Cookie leaking to subdomain | `__Host-` prefix — locked to exact host, no `Domain` attribute. |

---

## Anti-patterns

**`dangerouslySetInnerHTML` with unfiltered user input.** Always pass through `DOMPurify.sanitize()` first.

**`localStorage` for tokens.** Any script on the page can read it. XSS achieves full account takeover. Access tokens in memory; refresh tokens in `httpOnly` cookies.

**CSP `'unsafe-inline'`.** Defeats nonce-based CSP — any injected inline script executes. Stamp the nonce onto the specific `<script>` tag instead.

**CSP `'unsafe-eval'`.** Permitted in `NODE_ENV=development` only. Never in production.

**`SameSite=None` without a cross-origin requirement.** Sends cookie on every cross-origin request; enables CSRF. Default to `Lax` or `Strict`.

**Missing `httpOnly` on session cookies.** Exposed to `document.cookie` — XSS trivially exfiltrates the token.

**Missing `Secure` in production.** Browser sends cookie on the HTTP leg of an HTTP→HTTPS redirect. Passive observers capture it.

**Nonce in a static export.** `output: 'export'` has no server; the nonce is identical for every visitor. Use hash-based SRI (`experimental.sri`) instead.

---

## Sources

- **Next.js docs — Content Security Policy (nonce pattern):** https://nextjs.org/docs/app/building-your-application/configuring/content-security-policy — _authoritative: Next.js / Vercel; v16.2.4, 2026-04-10_
- **DOMPurify — XSS sanitizer by Cure53:** https://github.com/cure53/DOMPurify — _community: Cure53 security research; v3.4.2, April 2026_
- **next-safe — security header library:** https://trezy.gitbook.io/next-safe/ — _community: Tre Zimmermann (trezy)_
- **OWASP Content Security Policy Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html — _community: OWASP_
- **OWASP HttpOnly cookie attribute:** https://owasp.org/www-community/HttpOnly — _community: OWASP_

---

Last verified: 2026-05-04 (Next.js 16.X / React 19 / DOMPurify 3.X / next-safe X.X).
