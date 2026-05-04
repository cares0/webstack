# Frontend authentication

> Reference for build-fe SubAgent and frontend-implementer.
> ⚙️ **Optional integration** — activated via init's "needs auth" question (`manifest.project.needs_auth=true`). Backend setup walkthrough: `recipes/spring-security-auth.md`. This document covers the FE side (token storage, refresh, route guard, Server Action session).
> FE-side authentication patterns: httpOnly cookie storage, refresh rotation, route guard proxy, Server Action session check.

## What is FE auth in webstack

webstack implements authentication end-to-end across two paired documents. The backend side — JWT issuance, BCrypt password hashing, `SecurityFilterChain`, Spring Security 6 filter registration — lives in [`recipes/spring-security-auth.md`](../recipes/spring-security-auth.md). This document covers the frontend half: how the browser stores tokens, how token refresh works, how routes are protected, and how Server Actions verify sessions.

The pairing is intentional. The backend emits cookies via `Set-Cookie` response headers; the frontend never touches raw JWTs in JavaScript. The two docs must be read together when standing up auth from scratch.

webstack does not bundle Auth0, Clerk, Supabase Auth, or any external IdP. The project owns its identity flow. If you later migrate to an external IdP, replace the cookie-setting endpoints and update the refresh logic described here — the route guard and Server Action patterns remain the same.

## Why httpOnly cookie over localStorage

XSS (cross-site scripting) is the primary threat vector for token theft. A script injected through any content — third-party dependencies, user-generated content, a compromised CDN asset — can call `localStorage.getItem('access_token')` and exfiltrate the value to an attacker-controlled endpoint. There is no browser-level mitigation for this: once JavaScript can run on your page, localStorage is readable.

`httpOnly` cookies are invisible to JavaScript. `document.cookie` does not return them. `fetch` in user-land code cannot read them. The browser attaches them to outgoing same-origin (and SameSite-permitted cross-origin) requests automatically. An XSS payload cannot extract the token value; it can only trigger requests that carry the cookie, which is a much narrower attack surface.

OWASP recommends that session tokens be stored in `httpOnly` cookies set with `Secure` and `SameSite` attributes as the baseline (OWASP Session Management Cheat Sheet). localStorage is explicitly called out as inappropriate for sensitive session data.

Secondary considerations:

- Cookies survive tab close and page refresh without JavaScript coordination.
- The `__Host-` prefix locks a cookie to the exact origin (no subdomain leakage).
- `SameSite=Lax` blocks cross-site POST forgery while permitting top-level GET navigation, which is the correct default for most webstack projects.

## webstack convention

The convention matches the pattern documented in [`recipes/spring-security-auth.md`](../recipes/spring-security-auth.md):

- **Access token** — short-lived (15 min), stored in an httpOnly cookie named `__Host-access_token`. Sent automatically by the browser on same-origin requests. Also held in React in-memory state (`Zustand` or `Jotai`) as a decoded payload (user id, roles) for UI decisions — the raw token is never exposed.
- **Refresh token** — longer-lived (14 days), stored in an httpOnly cookie named `__Host-refresh_token` scoped to `/api/auth/refresh` only. Never readable by JavaScript. Sent automatically only when the browser hits that path.
- The Spring Security backend sets both cookies in `POST /api/auth/login` and `POST /api/auth/refresh` responses. The frontend does not construct `Set-Cookie` headers.
- The Next.js frontend (App Router) runs on Node.js; cookie verification in Server Actions uses the `cookies()` API from `next/headers`, not a client-side call.

The auth feature slice follows FSD-lite layout at `src/features/auth/`.

## Token storage

Spring Security sets both tokens as response cookies. The cookie attributes that must be present:

```
Set-Cookie: __Host-access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900
Set-Cookie: __Host-refresh_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/api/auth/refresh; Max-Age=1209600
```

Attribute breakdown:

| Attribute | Value | Reason |
|---|---|---|
| `HttpOnly` | — | Blocks JS access; prevents XSS token theft |
| `Secure` | — | HTTPS-only transmission |
| `SameSite` | `Lax` | Blocks cross-site POST; permits top-level GET navigation |
| `Path` | `/` (access) or `/api/auth/refresh` (refresh) | Refresh token sent only to refresh endpoint |
| `Max-Age` | 900 / 1209600 | Matches JWT TTL; browser expires cookie automatically |
| `__Host-` prefix | — | Enforces `Secure`, strips `Domain`, pins to exact origin |

The `__Host-` prefix is supported in all modern browsers. It requires `Secure` and `Path=/` — the refresh token deviates from `Path=/` (it uses `/api/auth/refresh`) so the full `__Host-` prefix applies only to the access token. Use `__Secure-refresh_token` for the refresh cookie if the narrower path is needed.

On the frontend, only the decoded payload is held in memory for UI logic:

```ts
// src/features/auth/model/store.ts
import { create } from 'zustand'

interface AuthState {
  userId: string | null
  roles: string[]
  setAuth: (userId: string, roles: string[]) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  userId: null,
  roles: [],
  setAuth: (userId, roles) => set({ userId, roles }),
  clearAuth: () => set({ userId: null, roles: [] }),
}))
```

The store is populated after login by parsing the JWT payload from the response body (not from the cookie). The raw token string is discarded after the store is updated.

## Refresh rotation

The backend rotates the refresh token on each use: every call to `POST /api/auth/refresh` invalidates the old refresh token and issues a new pair. This limits the damage window if a refresh token is somehow obtained.

The frontend must handle 401 responses by silently refreshing and retrying. The critical constraint: if multiple concurrent requests receive a 401 simultaneously, only one refresh call should be made; the others queue up and replay when the refresh resolves.

```ts
// src/features/auth/api/client.ts
let refreshPromise: Promise<void> | null = null

const pendingQueue: Array<{
  resolve: () => void
  reject: (err: unknown) => void
}> = []

async function runRefresh(): Promise<void> {
  const res = await fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) {
    // Refresh failed — redirect to login
    pendingQueue.forEach(({ reject }) => reject(new Error('session expired')))
    pendingQueue.length = 0
    window.location.replace('/login')
    throw new Error('refresh failed')
  }
  pendingQueue.forEach(({ resolve }) => resolve())
  pendingQueue.length = 0
}

function enqueueAfterRefresh(): Promise<void> {
  return new Promise((resolve, reject) => {
    pendingQueue.push({ resolve, reject })
  })
}

export async function apiFetch(
  input: RequestInfo,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(input, { ...init, credentials: 'include' })

  if (res.status !== 401) return res

  // Deduplicate: only one refresh in-flight at a time
  if (!refreshPromise) {
    refreshPromise = runRefresh().finally(() => {
      refreshPromise = null
    })
  } else {
    // Another request is already refreshing — wait for it
    await enqueueAfterRefresh()
    return fetch(input, { ...init, credentials: 'include' })
  }

  await refreshPromise
  return fetch(input, { ...init, credentials: 'include' })
}
```

Exponential backoff on refresh failure is unnecessary in the cookie model — if `POST /api/auth/refresh` returns 401, the refresh token is invalid or expired. Retrying will not help. Redirect immediately to `/login`.

The generated SDK in `src/shared/api/generated/` should delegate all HTTP calls through `apiFetch`. During codegen (`pnpm gen:api`), configure the custom fetch in the generator config so the wrapper is used project-wide.

## Route guard (proxy)

In Next.js 16, `middleware.ts` is renamed to `proxy.ts`. The route guard lives here. It runs before every route render and redirects unauthenticated visitors to `/login`.

```ts
// proxy.ts  (project root, same level as app/ and src/)
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { jwtVerify, type JWTPayload } from 'jose'

const PUBLIC_PATHS = new Set(['/login', '/register', '/forgot-password'])

const PROTECTED_MATCHER =
  /^\/(dashboard|settings|profile|admin)(\/.*)?$/

const secretKey = new TextEncoder().encode(process.env.JWT_PUBLIC_KEY ?? '')

async function verifyAccessToken(token: string): Promise<JWTPayload | null> {
  try {
    const { payload } = await jwtVerify(token, secretKey, {
      algorithms: ['HS256'],
    })
    return payload
  } catch {
    return null
  }
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Public paths — always allow
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next()

  // Only guard matched protected paths
  if (!PROTECTED_MATCHER.test(pathname)) return NextResponse.next()

  const accessToken = request.cookies.get('__Host-access_token')?.value

  if (!accessToken) {
    const returnTo = encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)
    return NextResponse.redirect(
      new URL(`/login?returnTo=${returnTo}`, request.url),
    )
  }

  const payload = await verifyAccessToken(accessToken)

  if (!payload) {
    // Token present but invalid or expired — clear it and redirect
    const response = NextResponse.redirect(
      new URL(`/login?returnTo=${encodeURIComponent(pathname)}`, request.url),
    )
    response.cookies.delete('__Host-access_token')
    return response
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon\\.ico|sitemap\\.xml|robots\\.txt).*)',
  ],
}
```

After successful login, redirect the user back to the `returnTo` URL:

```ts
// src/features/auth/api/mutations.ts
'use server'

import { redirect } from 'next/navigation'

export async function loginAction(formData: FormData) {
  // ... call backend, which sets cookies via Set-Cookie
  const returnTo = formData.get('returnTo')
  const target = typeof returnTo === 'string' && returnTo.startsWith('/')
    ? returnTo
    : '/dashboard'
  redirect(target)
}
```

Validate `returnTo` against an allow-list or check `startsWith('/')` to prevent open redirect attacks.

## Server Action session check

Server Actions run on the server but have no automatic session context. Read the cookie explicitly using `cookies()` from `next/headers`, then verify the JWT. This is the canonical pattern for protecting any `'use server'` action.

```ts
// src/shared/lib/auth.ts
import 'server-only'
import { cookies } from 'next/headers'
import { jwtVerify, type JWTPayload } from 'jose'
import { redirect } from 'next/navigation'
import { cache } from 'react'

const secretKey = new TextEncoder().encode(process.env.JWT_PUBLIC_KEY ?? '')

export interface SessionPayload extends JWTPayload {
  sub: string    // userId
  roles: string[]
}

export const getSession = cache(async (): Promise<SessionPayload> => {
  const cookieStore = await cookies()
  const token = cookieStore.get('__Host-access_token')?.value

  if (!token) redirect('/login')

  try {
    const { payload } = await jwtVerify(token, secretKey, {
      algorithms: ['HS256'],
    })
    return payload as SessionPayload
  } catch {
    redirect('/login')
  }
})
```

Use `getSession()` at the top of any protected Server Action or Server Component. React's `cache()` deduplicates the JWT verification within a single render pass — the crypto operation runs once even if multiple components call `getSession()`.

```ts
// src/features/settings/api/mutations.ts
'use server'

import { getSession } from '@/shared/lib/auth'

export async function updateProfileAction(formData: FormData) {
  const session = await getSession()  // redirects to /login if invalid

  const name = formData.get('name')
  // session.sub is the verified userId
  await updateUser(session.sub, { name: String(name) })
}
```

For role-based checks, inspect `session.roles` after `getSession()` returns:

```ts
const session = await getSession()
if (!session.roles.includes('admin')) {
  throw new Error('Forbidden')
}
```

## Logout

Logout must clear both cookies, reset client-side state, and invalidate any cached data. Three places to hit in order:

1. **Server Action** — clear cookies via `Max-Age=0`
2. **TanStack Query** — call `queryClient.clear()` to remove all cached data
3. **Sentry** — call `setUser(null)` to stop associating errors with the previous user (see [`frontend/error-monitoring.md`](error-monitoring.md))

```ts
// src/features/auth/api/mutations.ts
'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export async function logoutAction() {
  const cookieStore = await cookies()

  // Clear access token
  cookieStore.set('__Host-access_token', '', {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  })

  // Clear refresh token
  cookieStore.set('__Secure-refresh_token', '', {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/api/auth/refresh',
    maxAge: 0,
  })

  redirect('/login')
}
```

Client-side cleanup in the logout button component:

```tsx
// src/features/auth/ui/LogoutButton.tsx
'use client'

import { useQueryClient } from '@tanstack/react-query'
import * as Sentry from '@/shared/lib/sentry'
import { useAuthStore } from '@/features/auth/model/store'
import { logoutAction } from '@/features/auth/api/mutations'
import { useTransition } from 'react'

export function LogoutButton() {
  const queryClient = useQueryClient()
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const [isPending, startTransition] = useTransition()

  function handleLogout() {
    startTransition(async () => {
      // 1. Clear TanStack Query cache
      queryClient.clear()

      // 2. Clear Sentry user context
      Sentry.setUser(null)

      // 3. Clear in-memory auth store
      clearAuth()

      // 4. Clear cookies + redirect (server action)
      await logoutAction()
    })
  }

  return (
    <button onClick={handleLogout} disabled={isPending}>
      {isPending ? 'Signing out…' : 'Sign out'}
    </button>
  )
}
```

Also call the Spring Security logout endpoint (`POST /api/auth/logout`) if the backend maintains a refresh token revocation list (recommended for high-security applications). This invalidates the refresh token server-side before the cookie expires naturally.

## Anti-patterns

**Storing access tokens in localStorage or sessionStorage.** localStorage is readable by any JavaScript on the page, including third-party scripts and injected XSS payloads. sessionStorage survives only one tab and is equally readable. Use httpOnly cookies exclusively.

**Exposing the refresh endpoint path in client-side code.** The refresh token cookie is scoped to `/api/auth/refresh`. If you move the path or expose a public refresh endpoint that accepts a token from a request body or URL param, you break the scope isolation that prevents the token from leaking.

**No CSRF protection on cookie-based flows.** `SameSite=Lax` mitigates most CSRF for POST mutations (cross-site POSTs are blocked). However, if you ever enable `SameSite=None` (for cross-origin embeds), add a CSRF double-submit cookie or the `Synchronizer Token Pattern`. Never disable `SameSite` without a compensating control.

**Verifying the JWT on the client.** The proxy verifies the access token cryptographically via `jwtVerify`. This is correct. Never use `atob()` on the cookie value in client code to extract claims — cookies are httpOnly and `atob()` only decodes; it does not verify the signature.

**Infinite refresh loop.** If the access token cookie is malformed and the proxy always rejects it, redirecting to `/login` clears the cookie (see the proxy example above). Do not retry the refresh endpoint more than once — if it fails, redirect. Failing to break the loop causes a redirect storm that logs out the user by browser loop detection.

**Storing the JWT signing secret in `NEXT_PUBLIC_` variables.** `NEXT_PUBLIC_` variables are inlined into the browser bundle. The signing secret or private key must remain server-only. Use `JWT_PUBLIC_KEY` (no `NEXT_PUBLIC_` prefix) for verification in Server Actions and the proxy; the browser never needs it.

**Using `middleware.ts` instead of `proxy.ts` in Next.js 16.** The file convention was renamed in Next.js 16. A `middleware.ts` file will not be loaded; rename it to `proxy.ts` and rename the exported function from `middleware` to `proxy`. Run the provided codemod: `npx @next/codemod@canary middleware-to-proxy .`.

## Sources

- **OWASP Authentication Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html — _community: OWASP_
- **OWASP Session Management Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html — _community: OWASP_
- **Next.js App Router authentication guide:** https://nextjs.org/docs/app/building-your-application/authentication — _authoritative_
- **Next.js proxy.ts file convention (formerly middleware):** https://nextjs.org/docs/app/api-reference/file-conventions/middleware — _authoritative_
- **Spring Security backend pairing:** `recipes/spring-security-auth.md` — _internal_

Last verified: 2026-05-04 (Next.js 16.X / React 19 / Spring Security 6.X / OWASP).
