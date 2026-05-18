# Security beyond authentication

> Reference for build-be SubAgent and backend-implementer and security-auditor SubAgent.
> Defense-in-depth beyond authentication: headers, CORS, input sanitization, mass assignment, rate limiting.

## What is security beyond auth

Authentication (JWT, BCrypt, `SecurityFilterChain`) is covered in `recipes/spring-security-auth.md`. This document covers the defense layers that sit alongside auth:

- **Security headers** — browser-enforced policies against XSS, clickjacking, and MIME sniffing.
- **CORS** — controlled cross-origin access so browsers reject unexpected callers.
- **Mass assignment prevention** — request bodies must not overwrite `role`, `isAdmin`, or other admin fields.
- **Input sanitization** — contextual encoding before untrusted data reaches an output context.
- **Rate limiting** — token-bucket throttling for public and mutation endpoints.

Controls are split into two tiers. **Tier 1** (Section 1) is always-on baseline; **Tier 2** (Section 2) is opt-in.

---

## Section 1 — Baseline (Tier 1, always)

No extra dependencies beyond `spring-boot-starter-security` and `spring-boot-starter-webmvc`. Spring Security 7 enables a sensible header set automatically; CORS, mass assignment, and sanitization require DTO discipline and an optional encoder library.

---

## Security headers

Spring Security 7 adds a conservative header set automatically:

| Header | Default | Purpose |
|--------|---------|---------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | HTTPS enforcement (HTTPS responses only) |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME sniffing; blocks polyglot XSS |
| `X-Frame-Options` | `DENY` | Prevents clickjacking via iframe embedding |
| `X-XSS-Protection` | `0` | Disables legacy XSS auditor (OWASP-recommended) |
| `Cache-Control` | `no-cache, no-store, …` | Prevents caching of sensitive responses |

Not enabled by default — require opt-in: **`Referrer-Policy`**, **`Permissions-Policy`**, **`Content-Security-Policy`** (backend hint; Next.js `next.config.ts` is authoritative).

### Configuration via `HttpSecurity.headers { ... }` DSL

The defaults cover HSTS, `X-Content-Type-Options`, and `X-Frame-Options`. Opt in to `Referrer-Policy`, `Permissions-Policy`, and CSP inside the `SecurityConfig` `SecurityFilterChain`:

```kotlin
.headers { h ->
    h.httpStrictTransportSecurity { it.maxAgeInSeconds(63_072_000).includeSubDomains(true).preload(true) }
    h.referrerPolicy { it.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER_WHEN_DOWNGRADE) }
    h.permissionsPolicy { it.policy("camera=(), microphone=(), geolocation=()") }
    // Backend CSP hint only — Next.js next.config.ts owns the full policy:
    h.contentSecurityPolicy { it.policyDirectives("default-src 'none'; frame-ancestors 'none'") }
}
```

Key decisions:

- **HSTS `preload`** — only set when the domain is registered at hstspreload.org; never in development.
- **CSP** — the backend emits `default-src 'none'` as a fallback hint. The Next.js `next.config.ts` `headers()` array is authoritative for `script-src`, `style-src`, and `img-src`.
- **`X-Frame-Options` vs `frame-ancestors`** — keep both; CSP wins in modern browsers, the header is a fallback.
- **`Clear-Site-Data` on logout** — add via `HeaderWriter` to the logout handler if session cookies are used alongside JWT.

---

## CORS in Spring + Vercel

CORS must be processed before Spring Security's authentication filter. When a `CorsConfigurationSource` bean is present, Spring Security automatically installs a `CorsFilter` ahead of the auth filter — preflight `OPTIONS` requests are answered before any credential check.

Use `CorsConfigurationSource` + `http.cors { }`, not `WebMvcConfigurer.addCorsMappings`. Without `CorsConfigurationSource`, Spring Security rejects unauthenticated preflight requests before MVC CORS configuration is applied.

### Baseline CORS configuration

```kotlin
@Bean
fun corsConfigurationSource(): CorsConfigurationSource {
    val config = CorsConfiguration()
    config.allowedOrigins = listOf("https://app.example.com")
    // Vercel preview deploys — every PR gets a URL like: https://my-app-git-feature-abc-org.vercel.app
    config.allowedOriginPatterns = listOf(
        "https://my-app-*.vercel.app",
        "https://my-app-git-*-org.vercel.app",
    )
    config.allowedMethods = listOf("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    config.allowedHeaders = listOf("Authorization", "Content-Type", "X-Requested-With")
    config.exposedHeaders = listOf("X-RateLimit-Remaining", "X-RateLimit-Retry-After")
    config.allowCredentials = true  // required for HttpOnly refresh-token cookie
    config.maxAge = 3600            // preflight cache: 1 hour
    return UrlBasedCorsConfigurationSource().also {
        it.registerCorsConfiguration("/api/**", config)
    }
}
```

Wire into the `SecurityFilterChain`:

```kotlin
.cors { cors -> cors.configurationSource(corsConfigurationSource()) }
```

Preflight `OPTIONS` requests carry no credentials — `CorsFilter` answers them before any auth check; no `permitAll()` entry is needed. Never combine `allowedOrigins = listOf("*")` with `allowCredentials = true`; browsers reject that combination. For local development add `http://localhost:3000` via a gitignored `application-local.yml` and a `@Value("\${cors.extra-origins:}")` property appended to `config.allowedOrigins`.

---

## Mass assignment prevention

The fix is write-only DTOs: one DTO per operation, admin fields absent from public DTOs entirely.

```kotlin
// Public create — no status, no internalNote, no createdByAdminId
data class CreateInvoiceRequest(
    @field:NotBlank @field:Size(max = 255) val recipientName: String,
    @field:NotBlank @field:Email           val recipientEmail: String,
    @field:NotNull  @field:Positive        val amountCents: Long?,
)

// Admin update — separate DTO, separate @PreAuthorize-gated controller
data class AdminUpdateInvoiceRequest(
    val status: InvoiceStatus?,
    val internalNote: String?,
    val overrideAmountCents: Long?,
)
```

Map each DTO to a command in the application layer; never pass a DTO into the domain (see `docs/backend/validation.md`).

### `@JsonIgnoreProperties` + role separation

Add `@JsonIgnoreProperties(ignoreUnknown = true)` to every request DTO as an explicit contract signal (Spring Boot silently ignores unknown fields by default; the annotation protects against configuration drift). Admin-only fields must live behind a separate `@PreAuthorize`-gated controller:

```kotlin
@RestController @RequestMapping("/api/admin/invoices")
@PreAuthorize("hasRole('ADMIN')")
class AdminInvoiceController(private val adminUpdateInvoice: AdminUpdateInvoiceUseCase) {
    @PatchMapping("/{id}")
    fun adminUpdate(@PathVariable id: String, @RequestBody @Valid req: AdminUpdateInvoiceRequest) =
        InvoiceResponse.from(adminUpdateInvoice.execute(id, req.toCommand()))
}
```

The public `BillingController` never receives `AdminUpdateInvoiceRequest`. The routing enforces the boundary.

---

## Input sanitization

Two distinct operations are both required:

- **Sanitization (on input):** reject or strip dangerous characters before storing.
- **Encoding (on output):** contextually encode stored data before it reaches an HTML, JavaScript, or URL context.

### Bean Validation as a first gate

Use `@field:Pattern` to whitelist allowed characters for free-text fields (see `docs/backend/validation.md`): `@field:Pattern(regexp = "^[\\p{L}\\p{N} .,'-]{1,200}$")`.

### OWASP Java Encoder for HTML output

For Thymeleaf emails, PDF reports, or any backend-rendered HTML, add `implementation("org.owasp.encoder:encoder:1.4.0")` and escape at the output call site:

```kotlin
import org.owasp.encoder.Encode
val safeBody = Encode.forHtml(untrusted)          // element body
val safeAttr = Encode.forHtmlAttribute(untrusted) // inside attribute=""
val safeUrl  = Encode.forUriComponent(untrusted)  // URI segment
```

The library is zero-dependency; the same input needs different escaping depending on its output context.

### Custom `@NoHtmlContent` validator (`@SafeHtml` replacement)

`@SafeHtml` was removed in Hibernate Validator 7. Replace with a custom `ConstraintValidator`:

```kotlin
@Target(AnnotationTarget.FIELD) @Retention(AnnotationRetention.RUNTIME)
@Constraint(validatedBy = [NoHtmlValidator::class])
annotation class NoHtmlContent(
    val message: String = "Field must not contain HTML markup",
    val groups: Array<KClass<*>> = [], val payload: Array<KClass<out Payload>> = [],
)

class NoHtmlValidator : ConstraintValidator<NoHtmlContent, String?> {
    private val tag = Regex("[<>]")
    override fun isValid(v: String?, ctx: ConstraintValidatorContext) = v == null || !tag.containsMatchIn(v)
}
```

For rich-text fields where markup is intentional, use an allowlist parser (OWASP AntiSamy or jsoup `Safelist`) instead of a regex.

---

## OWASP Top 10 mapping (BE)

The OWASP Top 10:2021 provides the threat model. The table below maps each category to the webstack control that addresses it. Cross-reference with `cross-cutting/owasp-top10-cheatsheet.md` (arriving in Phase C) for the full cheatsheet.

| Code | Category | webstack mitigation |
|------|----------|-------------------|
| A01 | Broken Access Control | `@PreAuthorize` on admin endpoints; separate public/admin DTOs; cross-module refs by ID only |
| A02 | Cryptographic Failures | HSTS forces HTTPS; no plaintext secrets in code; sensitive fields encrypted at rest |
| A03 | Injection | Parameterized queries (jOOQ/Spring Data); `@Pattern` whitelist; OWASP Java Encoder for HTML output |
| A04 | Insecure Design | DDD/hexagonal layering; domain invariants in aggregates; write-only DTOs |
| A05 | Security Misconfiguration | Spring Security default headers; explicit CORS allowlist; `problemdetails.enabled=true` hides stack traces |
| A06 | Vulnerable and Outdated Components | Gradle `dependencyUpdates` task; Dependabot/Renovate in infrastructure repo |
| A07 | Identification and Authentication Failures | JWT filter; BCrypt cost ≥ 10; see `recipes/spring-security-auth.md`; Tier 2 rate limit on login |
| A08 | Software and Data Integrity Failures | Signed JWTs (HS256/RS256); Gradle dependency verification; no untrusted deserialization |
| A09 | Security Logging and Monitoring Failures | Structured Logback JSON; `GlobalExceptionHandler` logs full trace; Actuator endpoints secured |
| A10 | Server Side Request Forgery | No user-controlled URL fetches; external hostname allowlist; block `169.254.0.0/16` at egress |

---

## Section 2 — Rate limiting & advanced (Tier 2, opt-in)

Apply when the endpoint is public, involves credential submission, is a high-value mutation, or carries meaningful abuse risk (enumeration, scraping, brute-force). Depends on **Bucket4j 8.x** (token-bucket, Vladimir Bukhtoyarov) — in-memory by default, Redis-backed for multi-instance deployments.

---

## Bucket4j with Spring MVC

### Dependency

```kotlin
// build.gradle.kts
implementation("com.bucket4j:bucket4j-core:8.10.1")
// Optional — Redis-backed distributed limiting:
// implementation("com.bucket4j:bucket4j-redis:8.10.1")
// implementation("io.lettuce:lettuce-core:6.3.2.RELEASE")
```

### Rate limit interceptor + service

Use a `HandlerInterceptor` to short-circuit with a `ProblemDetail` 429 before the controller body executes.

```kotlin
@Component
class RateLimitInterceptor(private val rateLimitService: RateLimitService) : HandlerInterceptor {

    override fun preHandle(req: HttpServletRequest, res: HttpServletResponse, h: Any): Boolean {
        val probe = rateLimitService.tryConsume(resolveKey(req))
        res.setHeader("X-RateLimit-Remaining", probe.remainingTokens.toString())
        if (probe.isConsumed) return true

        val retryAfter = TimeUnit.NANOSECONDS.toSeconds(probe.nanosToWaitForRefill)
        res.status = 429; res.contentType = "application/problem+json"
        res.setHeader("X-RateLimit-Retry-After", retryAfter.toString())
        ObjectMapper().writeValue(res.writer,
            ProblemDetail.forStatus(HttpStatus.TOO_MANY_REQUESTS).apply {
                type   = URI.create("https://api.example.com/errors/RATE_LIMIT_EXCEEDED")
                title  = "Too many requests"
                detail = "Retry in $retryAfter seconds."
                setProperty("retryAfterSeconds", retryAfter)
            })
        return false
    }

    private fun resolveKey(req: HttpServletRequest): String {
        val p = SecurityContextHolder.getContext().authentication?.name
        return if (p != null && p != "anonymousUser") "user:$p"
        else "ip:${req.getHeader("X-Forwarded-For")?.split(",")?.first()?.trim() ?: req.remoteAddr}"
    }
}

@Service
class RateLimitService {
    private val buckets = ConcurrentHashMap<String, Bucket>()
    fun tryConsume(key: String): ConsumptionProbe =
        buckets.computeIfAbsent(key) {
            Bucket.builder()
                .addLimit { it.capacity(60).refillGreedy(60, Duration.ofMinutes(1)) }
                .addLimit { it.capacity(10).refillGreedy(10, Duration.ofSeconds(1)) }
                .build()
        }.tryConsumeAndReturnRemaining(1)
}
```

Register in `WebMvcConfigurer.addInterceptors`: `.addPathPatterns("/api/**").excludePathPatterns("/actuator/**")`.

### Per-user quota and login brute-force protection

`resolveKey` switches from IP to user ID for authenticated requests automatically. For login endpoints add a dedicated `LoginRateLimitService` with a tighter bucket (5 attempts / 5 minutes per IP — matching `recipes/spring-security-auth.md`) and register it on `/api/auth/login` only in `WebMvcConfig`:

```kotlin
private fun buildLoginBucket(): Bucket = Bucket.builder()
    .addLimit { it.capacity(5).refillIntervally(5, Duration.ofMinutes(5)) }
    .build()
```

### Redis backend option (distributed deployments)

In-memory buckets are per-instance. For horizontally scaled backends, add `com.bucket4j:bucket4j-redis:8.10.1` + `io.lettuce:lettuce-core`, create a `LettuceBasedProxyManager` bean, and replace `ConcurrentHashMap.computeIfAbsent` in `RateLimitService` with `proxyManager.builder().build(key, config).tryConsumeAndReturnRemaining(1)`.

---

## Anti-patterns

**1. `permitAll()` on broad path patterns.** `it.requestMatchers("/api/**").permitAll()` disables authentication for every endpoint under `/api/`. Use the narrowest possible matchers; the catch-all is `anyRequest().authenticated()`.

**2. `CORS *` with credentials.** `allowedOrigins = listOf("*")` combined with `allowCredentials = true` is rejected by browsers. Use an explicit origin list or `allowedOriginPatterns`.

**3. Admin fields in a public request body (mass assignment).** `data class RegisterRequest(val email: String, val role: String)` lets any caller self-assign a role. Admin fields belong in a separate `@PreAuthorize`-gated DTO and controller. The public DTO must not contain them.

**4. Delegating HTML escaping to the frontend only.** The backend writes to email templates, PDFs, and webhook payloads — none of which pass through the Next.js renderer. Any code that interpolates user input into an HTML context must call `Encode.forHtml()` directly.

**5. No rate limit on a public mutation endpoint.** A contact form, password-reset request, or registration endpoint with no throttle lets an attacker flood the mail server or enumerate accounts at zero cost. Apply Tier 2 rate limiting to every public mutation.

**6. Using `request.remoteAddr` for the rate-limit key behind a proxy.** Behind nginx, Vercel, or the Oracle Load Balancer, `remoteAddr` is the proxy's IP — all callers share one bucket. Read the first non-private IP from `X-Forwarded-For`, and restrict which headers your infrastructure forwards to prevent spoofing.

---

## Sources

- **Spring Security — Security HTTP Response Headers:** https://docs.spring.io/spring-security/reference/features/exploits/headers.html — _authoritative_
- **Spring Security — CORS:** https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html — _authoritative_
- **OWASP Top 10:2021:** https://owasp.org/Top10/2021/ — _authoritative_
- **OWASP Java Encoder Project:** https://owasp.org/www-project-java-encoder/ — _community: OWASP_
- **Bucket4j 8.x documentation (Vladimir Bukhtoyarov):** https://bucket4j.com/8.10.1/toc.html — _community: Vladimir Bukhtoyarov_

Last verified: 2026-05-04 (Spring Boot 4.0.X / Spring Security 7.X / Bucket4j 8.X / Kotlin 2.X).
