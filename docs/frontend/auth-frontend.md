# Frontend authentication

> Reference for build-fe SubAgent and frontend-implementer.
> ⚙️ **Optional integration** — activated via init's "needs auth" question (`manifest.project.needs_auth=true`). Backend setup walkthrough: `recipes/spring-security-auth.md`. This document covers the FE side (token storage, refresh, route guard, Server Action session).
> FE-side authentication patterns: httpOnly cookie storage, refresh rotation, route guard proxy, Server Action session check.

## What is FE auth in webstack

webstack implements authentication end-to-end across two paired documents. The backend side — JWT issuance, BCrypt hashing, `SecurityFilterChain`, Spring Security 7 filter registration — lives in [`recipes/spring-security-auth.md`](../recipes/spring-security-auth.md). This document covers the frontend half: token storage, silent refresh, route protection, and Server Action session verification.

The pairing is intentional. The backend emits cookies via `Set-Cookie`; the frontend never touches raw JWTs in JavaScript. Read both docs together when standing up auth from scratch.

webstack does not bundle Auth0, Clerk, or any external IdP. The project owns its identity flow. If you migrate to an external IdP later, replace the cookie-setting endpoints and update the refresh logic here — the route guard and Server Action patterns remain the same.

## Why httpOnly cookie over localStorage

XSS is the primary threat vector for token theft. A script injected through any content — third-party dependencies, user-generated content, a compromised CDN asset — can call `localStorage.getItem('access_token')` and exfiltrate it. There is no browser mitigation: once JavaScript runs on your page, localStorage is fully readable.

`httpOnly` cookies are invisible to JavaScript. `document.cookie` does not return them; `fetch` cannot read them. An XSS payload cannot extract the token value — it can only trigger requests that carry the cookie, which is a much narrower attack surface and does not expose the credential itself.

OWASP recommends session tokens be stored in `httpOnly` cookies with `Secure` and `SameSite` attributes as the baseline (OWASP Session Management Cheat Sheet). localStorage is explicitly called out as inappropriate for sensitive session data.

Secondary considerations:

- Cookies survive tab close and page refresh without JavaScript coordination.
- The `__Host-` / `__Secure-` prefixes pin cookies to the exact origin and prevent subdomain leakage.
- `SameSite=Lax` blocks cross-site POST forgery while permitting top-level GET navigation.

## webstack convention

Convention matches [`recipes/spring-security-auth.md`](../recipes/spring-security-auth.md):

- **Access token** — 15-min JWT, httpOnly cookie `__Host-access_token`, `Path=/`. Sent automatically on same-origin requests. Decoded payload (userId, roles) also held in a Zustand/Jotai store for UI decisions — the raw token is never exposed to JS.
- **Refresh token** — 14-day JWT, httpOnly cookie `__Secure-refresh_token`, `Path=/api/auth/refresh`. Never readable by JS; sent automatically only to that path.
- Spring Security sets both cookies in `POST /api/auth/login` and `POST /api/auth/refresh`. The frontend never constructs `Set-Cookie` headers.
- Cookie verification in Server Actions uses `cookies()` from `next/headers` — server-only, never client-side.

The auth feature slice lives at `src/features/auth/` (FSD-lite: `ui/`, `model/`, `api/`, `index.ts`).

## Token storage

Spring Security sets both tokens as response cookies with these attributes:

```
Set-Cookie: __Host-access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900
Set-Cookie: __Secure-refresh_token=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/api/auth/refresh; Max-Age=1209600
```

| Attribute | Reason |
|---|---|
| `HttpOnly` | Blocks JS read; prevents XSS token theft |
| `Secure` | HTTPS-only transmission |
| `SameSite=Lax` | Blocks cross-site POST; permits top-level GET |
| `Path=/api/auth/refresh` | Refresh token travels only to the refresh endpoint |
| `Max-Age` | Browser expires cookie aligned with JWT TTL |
| `__Host-` / `__Secure-` | Enforces `Secure`, pins origin, strips `Domain` |

`__Host-` requires `Path=/`, so it applies only to the access token. The refresh token uses `__Secure-` (narrower path is allowed). Both prefixes are supported in all modern browsers.

On the frontend, hold only the decoded payload in an in-memory Zustand store (`src/features/auth/model/store.ts`). Populate it after login from the response body (not from the cookie); discard the raw token string immediately. Zustand state resets on page reload — the silent refresh mechanism restores it automatically.

## Refresh rotation

The backend rotates the refresh token on every use: `POST /api/auth/refresh` invalidates the old pair and issues a new one. The frontend must silently handle 401 responses and deduplicate concurrent refresh calls so only one refresh fires while others queue.

```ts
// src/features/auth/api/client.ts
let refreshPromise: Promise<void> | null = null
const pending: Array<{ resolve: () => void; reject: (e: unknown) => void }> = []

async function runRefresh(): Promise<void> {
  const res = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
  if (!res.ok) {
    pending.forEach(({ reject }) => reject(new Error('session expired')))
    pending.length = 0
    window.location.replace('/login')
    throw new Error('refresh failed')
  }
  pending.forEach(({ resolve }) => resolve())
  pending.length = 0
}

export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, { ...init, credentials: 'include' })
  if (res.status !== 401) return res

  if (!refreshPromise) {
    refreshPromise = runRefresh().finally(() => { refreshPromise = null })
  } else {
    await new Promise<void>((resolve, reject) => pending.push({ resolve, reject }))
    return fetch(input, { ...init, credentials: 'include' })
  }

  await refreshPromise
  return fetch(input, { ...init, credentials: 'include' })
}
```

If `POST /api/auth/refresh` returns 401, the session is gone — retrying will not help. Redirect immediately. Exponential backoff does not apply in the cookie model.

Wire the generated SDK (`src/shared/api/generated/`) to delegate through `apiFetch` so the wrapper covers the entire project during codegen (`pnpm gen:api`).

## Route guard (middleware)

The route guard lives in `middleware.ts` at the project root and redirects unauthenticated visitors to `/login`, preserving the original destination in a `returnTo` query param.

```ts
// middleware.ts  (project root)
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { jwtVerify } from 'jose'

const PUBLIC = new Set(['/login', '/register', '/forgot-password'])
const PROTECTED = /^\/(dashboard|settings|profile|admin)(\/.*)?$/
const secretKey = new TextEncoder().encode(process.env.JWT_PUBLIC_KEY ?? '')

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  if (PUBLIC.has(pathname) || !PROTECTED.test(pathname)) return NextResponse.next()

  const token = request.cookies.get('__Host-access_token')?.value
  const returnTo = encodeURIComponent(pathname + request.nextUrl.search)

  if (!token) return NextResponse.redirect(new URL(`/login?returnTo=${returnTo}`, request.url))

  try {
    await jwtVerify(token, secretKey, { algorithms: ['HS256'] })
    return NextResponse.next()
  } catch {
    const res = NextResponse.redirect(new URL(`/login?returnTo=${returnTo}`, request.url))
    res.cookies.delete('__Host-access_token')
    return res
  }
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon\\.ico|sitemap\\.xml|robots\\.txt).*)'],
}
```

After login, redirect to `returnTo`. Validate with `startsWith('/')` to prevent open redirect:

```ts
'use server'
const returnTo = formData.get('returnTo')
const target = typeof returnTo === 'string' && returnTo.startsWith('/') ? returnTo : '/dashboard'
redirect(target)
```

## Server Action session check

Server Actions have no automatic session context. Read the cookie explicitly, then verify the JWT. Wrap in React's `cache()` so the crypto call runs once per render pass even if multiple components call `getSession()`.

```ts
// src/shared/lib/auth.ts
import 'server-only'
import { cookies } from 'next/headers'
import { jwtVerify, type JWTPayload } from 'jose'
import { redirect } from 'next/navigation'
import { cache } from 'react'

const secretKey = new TextEncoder().encode(process.env.JWT_PUBLIC_KEY ?? '')

export interface SessionPayload extends JWTPayload {
  sub: string      // userId
  roles: string[]
}

export const getSession = cache(async (): Promise<SessionPayload> => {
  const token = (await cookies()).get('__Host-access_token')?.value
  if (!token) redirect('/login')
  try {
    const { payload } = await jwtVerify(token, secretKey, { algorithms: ['HS256'] })
    return payload as SessionPayload
  } catch {
    redirect('/login')
  }
})
```

Usage in any protected Server Action or Server Component:

```ts
'use server'
import { getSession } from '@/shared/lib/auth'

export async function updateProfileAction(formData: FormData) {
  const session = await getSession()   // redirects to /login if token invalid
  await updateUser(session.sub, { name: String(formData.get('name')) })
}
```

For role gating, check `session.roles.includes('admin')` after `getSession()` returns and throw or return early.

## Logout

Three places to clear in order: cookies (server), TanStack Query cache, Sentry user context (see [`frontend/error-monitoring.md`](error-monitoring.md)).

Server Action expires both cookies with `Max-Age=0`:

```ts
'use server'
export async function logoutAction() {
  const jar = await cookies()
  jar.set('__Host-access_token', '', { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 0 })
  jar.set('__Secure-refresh_token', '', { httpOnly: true, secure: true, sameSite: 'strict', path: '/api/auth/refresh', maxAge: 0 })
  redirect('/login')
}
```

Client-side `LogoutButton` (`'use client'`) runs cleanup before the Server Action:

```ts
queryClient.clear()     // 1. purge TanStack Query cache
Sentry.setUser(null)    // 2. unlink errors from this user
clearAuth()             // 3. clear Zustand store
await logoutAction()    // 4. expire cookies + redirect
```

If the backend maintains a refresh token revocation list, also call `POST /api/auth/logout` inside `logoutAction()` to invalidate the token server-side before it naturally expires.

## Anti-patterns

**localStorage or sessionStorage for tokens.** Both are fully readable by any JavaScript on the page, including third-party scripts and XSS payloads. Use httpOnly cookies exclusively.

**Exposing a refresh path or token in client-visible code.** The `__Secure-refresh_token` is scoped to `/api/auth/refresh`. An alternative refresh endpoint that accepts a token from the request body or URL param breaks the scope isolation that prevents leakage.

**`SameSite=None` without a CSRF compensating control.** `SameSite=Lax` blocks cross-site POST. If `SameSite=None` is needed for cross-origin embeds, add a CSRF double-submit cookie or Synchronizer Token Pattern.

**Client-side JWT decoding.** The middleware verifies the access token cryptographically. Never use `atob()` on a cookie value in client code — the cookie is httpOnly (unreadable from JS anyway) and `atob()` only decodes; it does not verify the signature.

**Infinite refresh loop.** The middleware deletes the invalid access token cookie on redirect to `/login`. Do not retry `POST /api/auth/refresh` more than once — a second failure means the session is gone. Redirect immediately or the browser's loop-detection will force a hard stop.

**`NEXT_PUBLIC_` prefix on the JWT key.** Variables with that prefix are inlined into the browser bundle. Keep `JWT_PUBLIC_KEY` server-only; the browser never needs to verify tokens.

## Sources

- **OWASP Authentication Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html — _community: OWASP_
- **OWASP Session Management Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html — _community: OWASP_
- **Next.js App Router authentication guide:** https://nextjs.org/docs/app/building-your-application/authentication — _authoritative_
- **Next.js middleware file convention:** https://nextjs.org/docs/app/api-reference/file-conventions/middleware — _authoritative_
- **Spring Security backend pairing:** `recipes/spring-security-auth.md` — _community: webstack_

Last verified: 2026-05-04 (Next.js 16.X / React 19 / Spring Security 7.X / OWASP).
