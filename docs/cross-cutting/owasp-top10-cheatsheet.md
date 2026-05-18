# OWASP Top 10 (2021) — webstack stack mapping

> Reference for security-auditor SubAgent and code-reviewer SubAgent and feature-architect SubAgent.
> OWASP Top 10 (2021) cross-referenced to webstack defenses across FE / BE / Infra.

---

## What is this document

This cheat sheet maps each OWASP Top 10:2021 category to concrete defenses in the webstack stack: Next.js 16 (FE), Spring Boot 4 / Kotlin / Spring Modulith (BE), Postgres 16 (DB), OCI + Vercel (Infra). Use it as a security-auditor checklist during feature reviews — trace each external input and trust boundary against the five subsections of each relevant item.

---

## How to read each item

Five consistent subsections per A0X: **Threat** / **FE defense** / **BE defense** / **Infra defense** / **Where in webstack**. If a layer has no applicable control, that is noted explicitly.

---

## A01 Broken Access Control

### Threat

Attacker reads or modifies another user's data, escalates privileges, or accesses admin functionality. #1 in OWASP 2021. Vectors: IDOR, missing method-level authorization, JWT claim forgery, force-browsing.

### FE defense

Layout-level server-side session checks — hidden routes are not secured. `middleware.ts` is a UX redirect only. Role-based show/hide is cosmetic.

### BE defense

- `@PreAuthorize` on all controller methods and service operations (`@EnableMethodSecurity(prePostEnabled = true)`).
- Separate public and admin DTOs. Admin controller at `/api/admin/...` with `@PreAuthorize("hasRole('ADMIN')")`.
- Ownership check: application service reads aggregate, compares stored owner ID to caller's, rejects on mismatch.
- Spring Modulith: module A cannot import module B's domain entity — cross-module data leaks caught at compile time.

### Infra defense

Port 8080 on a private OCI subnet; only the LB reaches it. Postgres app user: DML only, no DDL, no superuser.

### Where in webstack

- `docs/backend/security-beyond-auth.md` — mass assignment, `@PreAuthorize`, admin DTO.
- `docs/recipes/spring-security-auth.md` — role claims, `SecurityFilterChain` rules.

---

## A02 Cryptographic Failures

### Threat

Cleartext HTTP, weak algorithms (MD5/SHA-1), hardcoded secrets, unencrypted fields at rest. Attacker intercepts traffic or reads a DB dump and extracts plaintext credentials or PII.

### FE defense

Fetch wrapper enforces `https://`. Access tokens in memory only — never `localStorage`. Refresh token in `HttpOnly; Secure; SameSite=Strict` cookie. `NEXT_PUBLIC_*` values must not be secrets.

### BE defense

- Passwords: BCrypt cost ≥ 10 or Argon2id. `HashedPassword` value object: plaintext never leaves the application service.
- JWT: HS256 (32+ byte `JWT_SIGNING_SECRET`) or RS256 for multi-service. `alg: none` rejected — algorithm hardcoded in `NimbusTokenAdapter`.
- Sensitive columns: AES-256-GCM via a JPA `AttributeConverter`; key in `FIELD_ENCRYPTION_KEY` env var.
- Spring Security auto-sets `Strict-Transport-Security` on HTTPS responses.

### Infra defense

TLS at OCI LB (Let's Encrypt / OCI Certificate Service). OCI Block Volumes AES-256 at rest. DB password from OCI Vault.

### Where in webstack

- `docs/recipes/spring-security-auth.md` — BCrypt, JWT, refresh token cookie.
- `docs/infrastructure/domain-and-tls.md` — TLS, certificates, HSTS preload.
- `docs/backend/security-beyond-auth.md` — HSTS config.

---

## A03 Injection

### Threat

Untrusted data sent to an interpreter: SQL, OS command, LDAP, SpEL, template injection. Attacker reads unauthorized data, modifies records, or executes arbitrary server code.

### FE defense

React JSX auto-encodes `{variable}`. `dangerouslySetInnerHTML`: use `DOMPurify.sanitize()` first. Validate user-controlled `href` to start with `https://` or `/` (`javascript:` bypasses React). Parse Server Action inputs through Zod.

### BE defense

- JPA and jOOQ use parameterized queries — never concatenate user input into query strings.
- Bean Validation gate: `@field:Pattern(regexp = "^[\\p{L}\\p{N} .,'-]{1,200}$")` on free-text DTO fields.
- `@NoHtmlContent` rejects HTML in non-markup fields. OWASP AntiSamy / jsoup `Safelist` for intentional rich-text.
- OWASP Java Encoder at output: `Encode.forHtml()`, `forHtmlAttribute()`, `forUriComponent()` in emails, PDFs, backend-rendered HTML.
- SpEL in `@PreAuthorize` must be compile-time literals — never user input.

### Infra defense

Postgres app user: no `COPY TO/FROM PROGRAM`, no `pg_read_file` — limits injection blast radius.

### Where in webstack

- `docs/backend/security-beyond-auth.md` — Bean Validation, `@NoHtmlContent`, Java Encoder.
- `docs/backend/validation.md` — Bean Validation patterns.

---

## A04 Insecure Design

### Threat

Design-level weaknesses no post-implementation patch can fully fix: missing threat modeling, absent rate limits, business logic abusable by design (negative quantities, enumeration), insecure defaults, weak domain invariant enforcement.

### FE defense

Opaque tokens for public-facing identifiers prevent enumeration. Client-side business rule validation is UX only — all rules enforced server-side.

### BE defense

- Domain invariants in the aggregate root, not in controller or service — prevents bypass via alternative paths.
- Cross-aggregate references by ID only; no object traversal across boundaries.
- Rate limits are a design requirement — apply Bucket4j to endpoints accepting unauthenticated input or abusable at volume.
- Feature `plan.md`: enumerate inputs, calling identities, business rules, invariant bounds.

### Infra defense

OCI security groups default to deny; new ingress rules require explicit review. `tofu plan` before `tofu apply` is a human gate on infrastructure design changes.

### Where in webstack

- `docs/backend/security-beyond-auth.md` — rate limiting, Bucket4j.
- `shared/methodologies/ddd.md` — aggregate invariants.
- `docs/cross-cutting/adr-and-c4.md` (pending) — ADR, C4 threat surface.

---

## A05 Security Misconfiguration

### Threat

Unnecessary features enabled (Actuator on public port), default credentials unchanged, stack traces leaked in error responses, permissive CORS, missing security headers, public cloud storage buckets. Most common penetration test finding.

### FE defense

`next.config.ts` `headers()` owns browser security headers: `Content-Security-Policy` (`default-src 'self'`, widen deliberately), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer-when-downgrade`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`. `error.tsx` shows user-facing messages only.

### BE defense

- Actuator: expose `health,info` only; bind to localhost or a separate management port.
- `server.error.include-stacktrace=never`, `server.error.include-message=never` in production. `ProblemDetail` (RFC 9457) — no internal detail to caller.
- CORS: explicit `allowedOrigins` in `CorsConfigurationSource`. `allowedOrigins = listOf("*")` + `allowCredentials = true` is rejected by browsers.
- Spring Security 7: HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection: 0` by default. Opt in to `Referrer-Policy`, `Permissions-Policy`, CSP via `HttpSecurity.headers {}`.

### Infra defense

OCI security lists: allowlist rules only; no `0.0.0.0/0` except 443 inbound to LB. Object storage private by default. SSH key-only.

### Where in webstack

- `docs/backend/security-beyond-auth.md` — headers, CORS, Actuator, `ProblemDetail`.
- `docs/infrastructure/domain-and-tls.md` — OCI network, subnet topology.

---

## A06 Vulnerable & Outdated Components

### Threat

Components with known CVEs expose the application to public exploits. Log4Shell (CVE-2021-44228) made a ubiquitous Java logging library into an RCE vector. Attackers scan version headers and exploit CVEs before patches are applied.

### FE defense

`pnpm audit --audit-level=high` in CI; block merges on high/critical. Renovate auto-merges patch/minor on green CI. `pnpm-lock.yaml` committed; reproduced exactly in CI (`--frozen-lockfile`).

### BE defense

- Gradle `dependencyUpdates` (Ben Manes) reports outdated deps. OWASP Dependency-Check fails on CVSS ≥ 7.
- Spring Boot BOM: upgrading `spring-boot-starter-parent` pulls patched transitives automatically.
- Docker base image (`eclipse-temurin:21-jre-alpine`): pin the digest, not just the tag. Re-pin on CVE notification.

### Infra defense

Trivy in CI on every build and nightly — CRITICAL CVEs block deployment. CodeQL on PRs and weekly on main. Renovate covers `versions.tf` / `required_providers`.

### Where in webstack

- `docs/cross-cutting/dependency-management.md` (pending) — Renovate, `pnpm audit`, Gradle plugins.
- `docs/infrastructure/ci-cd.md` — CodeQL, Trivy, scans.

---

## A07 Identification & Authentication Failures

### Threat

Broken authentication lets attackers assume other users' identities. Patterns: credential stuffing with no lockout, JWT `alg: none`, refresh tokens without rotation, sessions not invalidated on logout.

### FE defense

Login form: same error for "user not found" and "wrong password" (prevents enumeration). Access tokens in memory only. Old refresh token invalidated after every rotation. On second 401, redirect to login.

### BE defense

- BCrypt cost ≥ 10. `HashedPassword` value object: plaintext never logged or returned.
- JWT: `JWSAlgorithm.HS256` hardcoded; verify before inspecting claims (`alg: none` attack). Access TTL: 15 min; Refresh: 14 days.
- Rate limit `/api/auth/login`: 5 attempts / email / 5 min (Bucket4j); 429 + `Retry-After`.
- Account lockout: `failedAttempts` on `User` aggregate; email unlock after N failures.
- MFA: not bundled. TOTP (`dev.samstevens.totp:totp`) via short-lived `mfa_pending` JWT (5-min TTL).

### Infra defense

`JWT_SIGNING_SECRET` in OCI Vault; injected as a systemd env var by the deploy step.

### Where in webstack

- `docs/recipes/spring-security-auth.md` — BCrypt, JWT, `SecurityFilterChain`, refresh token.
- `docs/backend/security-beyond-auth.md` — rate limiting on login.

---

## A08 Software & Data Integrity Failures

### Threat

CI/CD pulls untrusted plugins, deserialization of untrusted data, unsigned artifacts. SolarWinds (build pipeline) and `event-stream` (malicious npm) are canonical supply-chain compromise examples.

### FE defense

`pnpm-lock.yaml` content hashes pinned (`--frozen-lockfile` in CI). SRI `integrity="sha256-..."` on manually added CDN `<script>` and `<link>` tags. Review Renovate major bumps before merging.

### BE defense

- Gradle dependency verification (`gradle/verification-metadata.xml`) pins JAR checksums; build fails on mismatch.
- No `ObjectInputStream` on untrusted input. Jackson: allowlisted `@JsonTypeInfo`; `enableDefaultTyping()` disabled.
- JWT signature check precedes all claim inspection in `NimbusTokenAdapter.verify()`.
- SpEL `@Value("#{...}")` compile-time literals only — never from user input or the database.

### Infra defense

GitHub Actions pinned to full commit SHA (`uses: actions/checkout@<sha>`), not mutable tags. Renovate keeps SHAs current. OIDC short-lived tokens for CI-to-OCI/Vercel auth — no long-lived secrets in CI.

### Where in webstack

- `docs/infrastructure/ci-cd.md` — SHA pinning, OIDC credentials, Trivy SBOM.

---

## A09 Security Logging & Monitoring Failures

### Threat

Incidents invisible for 200+ days on average. Failures: auth events not logged, no alerting on repeated failures, logs deleted with the application, no request correlation across FE and BE.

### FE defense

Never log passwords, tokens, or PII to console or error-tracking services. Include `X-Correlation-Id` in all API calls. Next.js server component logs appear in Vercel function logs.

### BE defense

- Structured Logback JSON: `timestamp`, `level`, `traceId`, `spanId`, `userId`, `requestId`.
- Security events at `WARN`+: `LoginResult.Invalid`, `AccessDeniedException`, JWT failure, rate limit, unhandled exceptions.
- Never log passwords, full JWTs, or PII — IDs and truncated identifiers only.
- `GlobalExceptionHandler` logs stack trace at `ERROR`; returns RFC 9457 `ProblemDetail` with no internal detail.
- `X-Correlation-Id` stored in MDC via `OncePerRequestFilter`; propagated on all log statements.

### Infra defense

OCI Logging via Logging Agent; 30-day retention. OCI Monitoring Alarms on error-rate spikes. Vercel log drain (Axiom/Datadog) for retention past 1-hour default.

### Where in webstack

- `docs/backend/observability.md` — Micrometer, tracing, OCI Monitoring.
- `docs/cross-cutting/logging-strategy.md` (pending) — structured logging, MDC, correlation ID.

---

## A10 Server-Side Request Forgery (SSRF)

### Threat

Attacker induces the server to make HTTP requests to arbitrary destinations. In cloud, `http://169.254.169.254/` (instance metadata) returns IAM credentials. Enables: internal scanning, credential exfiltration, non-public port probing.

### FE defense

Never forward user-provided URLs to a backend fetch verbatim. URL-fetching features must use a server-side function with an allowlist. Next.js proxy routes: validate destination before forwarding.

### BE defense

- Hostname allowlist: `require(URI(url).host in allowed)` before any outbound fetch of user-supplied URLs.
- Resolve hostname; reject private ranges (`10/8`, `172.16/12`, `192.168/16`) and link-local `169.254/16`.
- Disable auto-redirect (`followRedirect(false)`) — bounces from allowed to internal.
- Reject `localhost` and `0.0.0.0` unconditionally.

### Infra defense

OCI Security List: block egress to `169.254.0.0/16`. OCI IMDSv2: metadata requests require a TTL-limited token; plain HTTP GET is rejected.

### Where in webstack

- `docs/infrastructure/domain-and-tls.md` — OCI Security Lists, subnet topology.
- `docs/backend/security-beyond-auth.md` — outbound request controls.

---

## Anti-patterns

**"Security is the last step."** Post-implementation findings often require core redesign (auth model, aggregate boundaries). Address security in `plan.md` before writing code.

**Checklist-free implementation.** "This is a simple feature" is how vulnerabilities are introduced. User-input → A03; external calls → A10; auth → A07.

**Single-layer defense.** "The FE validates input, so BE does not need to." Every layer can be bypassed — that is why each A0X section has three defense layers.

**Logging without monitoring.** Structured logs without OCI Alarms or alert rules are compliance theater. `WARN` spikes on `LoginResult.Invalid` signal credential stuffing; `AccessDeniedException` clusters signal enumeration.

**Hardcoded secrets.** Rotate and revoke immediately; audit repository history. Use env vars and OCI Vault.

**Ignoring Renovate PRs.** Known CVEs stay in production for weeks. Merge patch/minor with green CI within 48 hours.

---

## Sources

- **OWASP Top 10:2021 official list:** https://owasp.org/Top10/2021/ — _authoritative: OWASP_
- **OWASP Authentication Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html — _community: OWASP_
- **OWASP XSS Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html — _community: OWASP_
- **OWASP SSRF Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html — _community: OWASP_
- **OWASP Java Encoder Project:** https://owasp.org/www-project-java-encoder/ — _community: OWASP_
- **Spring Security HTTP Response Headers:** https://docs.spring.io/spring-security/reference/features/exploits/headers.html — _authoritative: Spring_
- **Spring Security Method Security:** https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html — _authoritative: Spring_
- **DOMPurify:** https://github.com/cure53/DOMPurify — _community: cure53_

Last verified: 2026-05-04 (OWASP Top 10:2021 / Next.js 16.X / Spring Boot 4.0.X / Postgres 16.X).
