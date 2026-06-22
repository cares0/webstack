# Spring Security Auth Recipe (self-implemented, no external IdP)

> Reference for any webstack project that opted in (`needs_auth=true`) during `/webstack:init`. Recommended path: implement authentication directly with Spring Security 7 — JWT for session, BCrypt for password hashing — and model it as a regular bounded context. webstack does **not** bundle Supabase Auth, Auth0, Clerk, or any external IdP. The project owns its identity flow.
>
> **Frontend side** — Token storage (httpOnly cookies), refresh rotation, route guard middleware, and Server Action session checks live in `docs/frontend/auth-frontend.md`. This recipe is BE only.

This recipe is a checklist + code patterns, not a tutorial. If you have never used Spring Security, also read the official docs (linked at the bottom) before applying.

## When to use this recipe

- The init prompt set `needs_auth=true` and `spring-boot-starter-security` is on the classpath.
- You are about to add the first auth-bearing feature (typically `/webstack:feature auth` — registers a `User` aggregate, login/register use cases, JWT-issuing endpoints).
- You explicitly chose self-implemented auth over an external IdP.

If you want an external IdP instead (Auth0, Clerk, AWS Cognito, …), don't use this recipe — wire `spring-boot-starter-security-oauth2-resource-server` (renamed from `spring-boot-starter-oauth2-resource-server` in Spring Boot 4) to that provider's JWKS URL, skip the password-hashing parts, and most of this document doesn't apply.

## Architectural shape (DDD/Hexagonal/Modulith fit)

The auth feature is one Modulith module (`auth/`) with the standard hexagonal layout webstack uses everywhere:

```text
src/main/kotlin/com/<org>/<project>/auth/
├── package-info.java                # @ApplicationModule(displayName = "Auth")
├── UserRegistered.kt                # public domain event (other modules subscribe)
├── domain/
│   └── user/
│       ├── User.kt                  # aggregate root: id, email, hashedPassword, createdAt
│       ├── UserId.kt                # value object
│       ├── Email.kt                 # value object with format validation
│       ├── HashedPassword.kt        # value object — never holds plaintext
│       └── UserRepository.kt        # driven port
├── application/
│   ├── register/
│   │   ├── RegisterUserUseCase.kt
│   │   ├── RegisterUserService.kt   # @Service @Transactional — hashes password, persists, publishes UserRegistered
│   │   └── RegisterUserCommand.kt
│   ├── login/
│   │   ├── LoginUseCase.kt
│   │   ├── LoginService.kt          # @Service @Transactional(readOnly = true) — verifies password, issues JWT
│   │   └── LoginCommand.kt
│   └── token/
│       ├── TokenIssuer.kt           # driving port — implementations encode JWT
│       └── TokenVerifier.kt         # driving port — implementations decode + validate JWT
└── infrastructure/
    ├── http/
    │   ├── AuthController.kt        # POST /api/auth/register, POST /api/auth/login
    │   ├── AuthDto.kt               # Jackson-bound request/response DTOs
    │   └── SecurityConfig.kt        # @Configuration — SecurityFilterChain + JwtAuthenticationFilter
    ├── persistence/
    │   ├── UserJpaEntity.kt
    │   └── UserJpaRepository.kt
    └── token/
        └── NimbusTokenAdapter.kt    # implements TokenIssuer + TokenVerifier via Nimbus JOSE
```

Key constraints:

- The `domain/` layer holds zero Spring Security imports. `User`, `Email`, `HashedPassword` are pure Kotlin.
- `HashedPassword` is constructed only via a domain factory that takes plaintext + a `PasswordHasher` port (driven by the BCrypt adapter). The plaintext never leaves the application service.
- JWT issuance and verification are **driving ports** (`TokenIssuer`, `TokenVerifier`) so the domain doesn't know about Nimbus, jjwt, or any specific library.
- The Modulith module's public surface is the `UserRegistered` event + (if cross-module reads are needed) a small `UserDirectory` query interface that returns non-sensitive fields. The aggregate `User` and `HashedPassword` never leak.

## Dependencies

In `build.gradle.kts`:

```kotlin
dependencies {
    // already present from init when needs_auth=true:
    implementation("org.springframework.boot:spring-boot-starter-security")

    // add for JWT (Nimbus is Spring's default; comes via the resource-server starter):
    // Note: renamed from spring-boot-starter-oauth2-resource-server in Spring Boot 4.
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-resource-server")
    // Nimbus JOSE for issuing tokens (decoder is provided by the starter above):
    // (verify the version the resource-server starter pulls on Boot 4 — Nimbus 9.x vs 10.x — and align this pin to it)
    implementation("com.nimbusds:nimbus-jose-jwt:9.40")

    // BCrypt for password hashing comes with spring-security-crypto, already pulled in by
    // spring-boot-starter-security. No extra dep needed.

    testImplementation("org.springframework.security:spring-security-test")
}
```

If you prefer `io.jsonwebtoken:jjwt-*` over Nimbus, swap the JWT dep — the rest of the recipe (hexagonal ports + BCrypt + filter chain) is unchanged. Nimbus is recommended because Spring's resource-server starter already uses it.

## Password hashing

BCrypt is the default for any new project. Argon2id is acceptable; SHA/MD5/PBKDF2 are not. Never store plaintext.

```kotlin
// auth/application/register/PasswordHasher.kt — driving port
interface PasswordHasher {
    fun hash(plaintext: String): HashedPassword
    fun matches(plaintext: String, hashed: HashedPassword): Boolean
}

// auth/infrastructure/token/BCryptPasswordHasher.kt — adapter
@Component
class BCryptPasswordHasher : PasswordHasher {
    private val encoder = BCryptPasswordEncoder()
    override fun hash(plaintext: String) = HashedPassword(encoder.encode(plaintext))
    override fun matches(plaintext: String, hashed: HashedPassword) =
        encoder.matches(plaintext, hashed.value)
}
```

The `BCryptPasswordEncoder` from `org.springframework.security.crypto.bcrypt` ships with `spring-boot-starter-security`. Default cost factor is 10, which is appropriate as of 2026. Bump to 12 for high-stakes products.

## JWT issuance & verification

Issue short-lived access tokens (15 min) + longer-lived refresh tokens (14 days). **webstack defaults to RS256** (asymmetric): the BE signs with the private key, and the Next.js middleware verifies access tokens with only the **public** key (`importSPKI(process.env.JWT_PUBLIC_KEY, 'RS256')`, `algorithms: ['RS256']` — see `docs/frontend/auth-frontend.md`). Because the FE is a second party that verifies the same token, a shared HS256 secret will not do — the FE must never hold a signing secret. Use HS256 with a single shared secret (`JWT_SIGNING_SECRET` env var, 32+ bytes random) only when the BE is the sole party that ever verifies the token (no FE-side verification). The example below shows the HS256 single-service path; for the default RS256 path, swap `MACSigner`/`MACVerifier` for `RSASSASigner`/`RSASSAVerifier` and `JWSAlgorithm.RS256`, load the private key from `app.env`, and publish only the public key to the FE.

```kotlin
// auth/application/token/TokenIssuer.kt — port
interface TokenIssuer {
    fun issueAccess(userId: UserId, claims: Map<String, Any> = emptyMap()): String
    fun issueRefresh(userId: UserId): String
}

// auth/infrastructure/token/NimbusTokenAdapter.kt — adapter
@Component
class NimbusTokenAdapter(
    @Value("\${jwt.signing-secret}") signingSecret: String,
    @Value("\${jwt.access-ttl-minutes:15}") private val accessTtlMin: Long,
    @Value("\${jwt.refresh-ttl-days:14}") private val refreshTtlDays: Long,
) : TokenIssuer, TokenVerifier {

    private val signer = MACSigner(signingSecret.toByteArray())
    private val verifier = MACVerifier(signingSecret.toByteArray())

    override fun issueAccess(userId: UserId, claims: Map<String, Any>): String {
        val now = Instant.now()
        val claimsBuilder = JWTClaimsSet.Builder()
            .subject(userId.value.toString())
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plus(accessTtlMin, ChronoUnit.MINUTES)))
            .claim("typ", "access")
        claims.forEach { (k, v) -> claimsBuilder.claim(k, v) }
        return signed(claimsBuilder.build())
    }

    override fun issueRefresh(userId: UserId): String { /* similar with typ=refresh */ }

    override fun verify(token: String): VerifiedToken { /* parse, check signature, exp, typ */ }

    private fun signed(claims: JWTClaimsSet): String {
        val jwt = SignedJWT(JWSHeader(JWSAlgorithm.HS256), claims)
        jwt.sign(signer)
        return jwt.serialize()
    }
}
```

Configuration in `application.yml`:

```yaml
jwt:
  signing-secret: ${JWT_SIGNING_SECRET}
  access-ttl-minutes: 15
  refresh-ttl-days: 14
```

Add `JWT_SIGNING_SECRET` to `<infra>/.env` (gitignored, set during init) and to the systemd `app.env` file SCP'd by `/webstack:deploy`. Generate once with `openssl rand -base64 48`.

## SecurityFilterChain

Replace the permissive default (created during init when `needs_auth=true`) with a real chain that requires authentication on everything except the auth endpoints and public read paths:

```kotlin
@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val tokenVerifier: TokenVerifier,
) {
    @Bean
    fun filterChain(http: HttpSecurity): SecurityFilterChain {
        return http
            .csrf { it.disable() }                                  // stateless API, no CSRF token
            .sessionManagement { it.sessionCreationPolicy(SessionCreationPolicy.STATELESS) }
            .authorizeHttpRequests {
                it.requestMatchers("/api/auth/register", "/api/auth/login").permitAll()
                it.requestMatchers("/actuator/health").permitAll()
                it.anyRequest().authenticated()
            }
            .addFilterBefore(JwtAuthenticationFilter(tokenVerifier), UsernamePasswordAuthenticationFilter::class.java)
            .build()
    }
}
```

`JwtAuthenticationFilter` reads the `Authorization: Bearer <token>` header, asks `TokenVerifier` to decode + validate it, and writes a `UsernamePasswordAuthenticationToken` to the `SecurityContext`. The principal is the `UserId` (UUID); domain code reads it via `SecurityContextHolder.getContext().authentication.name`.

For role-based authorization: include `roles` claim in the JWT, expose them as Spring authorities (`ROLE_ADMIN`, etc.), and gate endpoints with `@PreAuthorize("hasRole('ADMIN')")`. Most webstack projects start with one role tier (any authenticated user) and add roles later.

## Endpoints

```kotlin
// auth/infrastructure/http/AuthController.kt
@RestController
@RequestMapping("/api/auth")
class AuthController(
    private val register: RegisterUserUseCase,
    private val login: LoginUseCase,
) {
    @PostMapping("/register")
    fun register(@RequestBody @Valid req: RegisterRequest): ResponseEntity<TokenPair> {
        val result = register.execute(RegisterUserCommand(req.email, req.password))
        return ResponseEntity.status(201).body(TokenPair(result.accessToken, result.refreshToken))
    }

    @PostMapping("/login")
    fun login(@RequestBody @Valid req: LoginRequest): ResponseEntity<TokenPair> {
        val result = login.execute(LoginCommand(req.email, req.password))
        return ResponseEntity.ok(TokenPair(result.accessToken, result.refreshToken))
    }
}

data class RegisterRequest(@Email val email: String, @Size(min = 8, max = 100) val password: String)
data class LoginRequest(@Email val email: String, @NotBlank val password: String)
data class TokenPair(val accessToken: String, val refreshToken: String)
```

Validation uses Bean Validation annotations on the DTO; the application service receives a clean command. Domain `Email` value object re-validates as a defense-in-depth.

## Frontend integration

The frontend stores tokens in **memory + a same-site secure cookie for refresh**. webstack convention:

- Access token: in-memory only (a `Zustand`/`Jotai` store or just a React state at the app root). Lost on refresh; the refresh token endpoint regenerates a new pair.
- Refresh token: `Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict; Path=/api/auth/refresh`. Never readable by JS. Sent automatically when the FE calls `POST /api/auth/refresh`.
- On 401 from any backend call, the FE calls `/api/auth/refresh`; on 401 there too, redirect to login.

The auth feature slice lives at `src/features/auth/` (FSD-lite):

```text
src/features/auth/
├── ui/
│   ├── LoginForm.tsx            # 'use client'; RHF + Zod
│   └── RegisterForm.tsx
├── model/
│   ├── schema.ts                # Zod schemas — must match backend DTOs
│   └── store.ts                 # in-memory access token store
├── api/
│   ├── mutations.ts             # useLoginMutation, useRegisterMutation, useRefreshMutation
│   └── client.ts                # fetch wrapper that injects Bearer + retries on 401
└── index.ts
```

The fetch wrapper (in `client.ts`) is the one place that knows about tokens; the rest of the app calls the generated SDK.

## Testing

Domain layer (KoTest BehaviorSpec, pure JVM):

- `User` aggregate: registration creates a user with hashed password; login matches plaintext against the hash.
- `Email` value object: format validation rejects invalid inputs.
- `HashedPassword` value object: cannot be constructed with empty input; `matches` returns false on tamper.

Application layer (KoTest + MockK, no Spring):

- `RegisterUserService`: when called twice with the same email, the second call surfaces a domain conflict (test the use case's port behavior, not the JPA exception).
- `LoginService`: invalid password returns a `LoginResult.Invalid`, never an exception (avoid timing-attack hints).

Infrastructure layer (KoTest + Spring slice + Testcontainers):

- `AuthController`: integration test hitting `/api/auth/register` and `/api/auth/login` against a real Postgres in a Testcontainer. Verifies status codes, JWT shape, password not echoed back.
- `JwtAuthenticationFilter`: forged tokens (wrong signature, expired, wrong typ) are rejected with 401.

## Security checklist

- [ ] JWT signing secret is ≥ 32 bytes random, in env var, not in source.
- [ ] Access token TTL ≤ 15 min, refresh token TTL ≤ 14 days; refresh token rotation on use.
- [ ] Password hashed with BCrypt (cost ≥ 10) or Argon2id; plaintext never logged or persisted.
- [ ] `/api/auth/login` does not distinguish "wrong email" from "wrong password" in the response (timing or message).
- [ ] Rate-limit `/api/auth/login` (Spring's `Bucket4j` integration is the easy path) — 5 attempts per email per 5 minutes.
- [ ] CORS whitelist limits the FE origin only — no `*`.
- [ ] CSRF disabled because the API is stateless JWT-bearer; if any cookie-based session is later added, re-enable.
- [ ] HTTPS enforced in production (Spring's `requireSecure`, or upstream Caddy TLS termination on 443 → `localhost:8080`).
- [ ] Refresh token cookie: `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth/refresh`.
- [ ] Account lockout after N failed attempts (or progressive delay).
- [ ] Email verification before allowing login (if requirements need it) — emit a `UserRegistered` event, an email-sender module subscribes and sends the verification link.

## Sources

- Spring Security reference: https://docs.spring.io/spring-security/reference/
- Spring Security OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- BCryptPasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Nimbus JOSE + JWT: https://connect2id.com/products/nimbus-jose-jwt
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP JWT Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html

Last verified: 2026-06-22 (Spring Boot 4.0.X / Spring Security 7.X / Nimbus JOSE 9.X / BCrypt).
