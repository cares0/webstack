# API versioning (URI + deprecation/sunset headers)

> Reference for build-be SubAgent and backend-implementer and feature-architect SubAgent.
> URI versioning, RFC 9745 Deprecation, RFC 8594 Sunset, springdoc multi-group exposure for webstack's Spring Boot + OpenAPI 3.1 backend.

## What is API versioning in webstack

API versioning in webstack gives each **incompatible contract generation** its own stable URI so existing consumers keep working while new consumers adopt the updated contract. webstack applies versioning at the URI level (`/v1/`, `/v2/`) and records every version as a discrete OpenAPI 3.1 document.

### Minor vs major change policy

**Minor (backward-compatible) changes** — safe to ship without a new version path. Examples: adding an optional request field, adding a response field (consumers ignore unknown fields per the robustness principle), adding an optional enum value with a documented default, adding a new endpoint under the existing prefix, relaxing a constraint.

**Major (breaking) changes** — require a new URI prefix (`/v2/...`). The old version continues serving traffic for the sunset window. Examples: removing or renaming a field, changing a field type, making an optional field required, removing an endpoint, changing authentication semantics.

The `info.version` in the OpenAPI 3.1 contract follows `MAJOR.MINOR.PATCH`. A bump to `MAJOR` always coincides with a new URI prefix.

### OpenAPI 3.1 contract-first

webstack is contract-first: `.webstack/contracts/<feature>.yaml` is the source of truth before any code is written. See `shared/methodologies/api-first.md` for the full workflow. When a feature requires a breaking change, a new contract (`<feature>-v2.yaml`) is authored and reviewed before implementation begins.

## Why URI versioning

webstack chooses URI versioning as its primary strategy for these reasons:

**Simplicity.** The version appears in every log line, browser URL bar, and curl command. No HTTP header knowledge needed to identify the target version.

**CDN and Vercel friendliness.** CDNs and Vercel's edge cache by URL path by default. Path-prefix routing rules (`/v1/` vs `/v2/`) require zero special configuration. Header-based versioning requires custom `Vary` cache-key setup that many CDNs ignore.

**springdoc multi-group.** `GroupedOpenApi.builder().pathsToMatch("/v1/**")` needs no extra code. springdoc exposes `/v3/api-docs/v1` and `/v3/api-docs/v2` as independent OpenAPI 3.1 documents without custom request matchers.

**Tooling alignment.** OpenAPI 3.1 `servers` entries, Postman, Swagger UI, and the generated TypeScript SDK `baseURL` all use URL paths as the natural version token.

## webstack convention

### URI prefix

```
/v1/<resource>
/v1/<resource>/{id}
```

There is no unversioned public endpoint. Actuator probes (`/actuator/health`) are excluded — they are infrastructure concerns.

### Spring `@RequestMapping`

Declare the version prefix at the class level; handlers use relative paths:

```kotlin
// order/infrastructure/http/OrderController.kt
@RestController
@RequestMapping("/v1/orders")
class OrderController(private val placeOrder: PlaceOrderUseCase) {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun place(@Valid @RequestBody req: PlaceOrderRequest): OrderResponse =
        placeOrder(req.toCommand()).toResponse()

    @GetMapping("/{orderId}")
    fun get(@PathVariable orderId: String): OrderResponse =
        placeOrder.findById(orderId).toResponse()
}
```

When v2 is introduced, a second controller handles `/v2/orders`. The v1 controller stays intact for the sunset window. Both may delegate to the same application service; they differ only in DTO shapes.

### springdoc `GroupedOpenApi` per version

One `GroupedOpenApi` bean per active version, keyed by path prefix. See [springdoc multi-version groups](#springdoc-multi-version-groups) for the full configuration. springdoc exposes `/v3/api-docs/v1` and `/v3/api-docs/v2` (JSON and `.yaml` variants). Swagger UI renders a version selector drop-down automatically.

## URI vs media-type vs header — comparison

| Criterion | URI versioning (`/v1/`) | Media-type versioning (`Accept: application/vnd.api.v1+json`) | Header versioning (`X-API-Version: 1`) |
|---|---|---|---|
| **Cache friendliness** | Excellent — URL is the natural cache key; CDNs and Vercel edge work out of the box. | Poor — requires `Vary: Accept`; many CDNs ignore `Vary`. | Poor — custom `Vary` header; rarely supported by default CDN config. |
| **Discoverability** | High — visible in URL, logs, curl, browser address bar. | Low — version hidden in request headers. | Low — custom header invisible without HTTP inspection tooling. |
| **Client library ergonomics** | Excellent — SDK `baseURL` is `https://api.example.com/v1`; v2 changes only the base URL. | Moderate — each request must set `Accept` correctly. | Moderate — easy to forget; proxy stripping is a common failure mode. |
| **REST purity** | Debated — pragmatically accepted by Stripe, GitHub, Twilio. | Higher — same resource URL, representation negotiated by `Accept`. | Lower — no standard RFC backing for versioning via custom header. |
| **springdoc support** | First-class — `pathsToMatch("/v1/**")` requires no extra code. | Limited — needs custom `RequestMappingHandlerMapping`. | Limited — `GroupedOpenApi` cannot filter by arbitrary request headers. |

**webstack verdict:** URI versioning. CDN, springdoc, and tooling advantages outweigh the REST-purity objection.

## Backward-compatible changes

Safe without a new URI version:

| Change | Rule |
|---|---|
| Add optional response field | Clients ignore unknown JSON fields (robustness principle); OAS 3.1 allows extra properties by default. |
| Add optional request field | Existing callers omit it; server uses a default. |
| Add a new enum value | Safe if contract documents an `UNKNOWN` sentinel. Kotlin: `@JsonEnumDefaultValue`; TS SDK: union with string fallback. |
| Add a new endpoint | Callers unaware of new paths are unaffected. |
| Relax a constraint | Smaller `minLength`, removed `pattern`, etc. |

**Client safety guarantee.** `pnpm gen:api` regenerating the TypeScript SDK cleanly with no type errors confirms backward compatibility by construction. `contract-drift-detective` verifies the runtime spec against the contract YAML.

```kotlin
// Backward-compatible DTO extension example
data class OrderResponse(
    val orderId: String,
    val status: OrderStatus,
    val totalCents: Long,
    val currencyCode: String = "KRW",   // new optional field — safe
)
```

## Breaking changes — new major

### Process

1. **Author a new contract.** Create `.webstack/contracts/<feature>-v2.yaml`, `info.version: 2.0.0`.
2. **Implement v2 controllers.** Add `OrderV2Controller` at `/v2/orders`. Keep `OrderController` (`/v1/orders`) intact.
3. **Add a v2 `GroupedOpenApi` bean** (see [springdoc multi-version groups](#springdoc-multi-version-groups)).
4. **Add `Deprecation` and `Sunset` headers to all v1 responses** on the day v2 ships (see [Deprecation & sunset headers](#deprecation--sunset-headers)).
5. **Announce the window.** Minimum sunset: **6 months** public / **3 months** internal.
6. **Monitor v1 traffic.** Spring Boot Actuator per-path metrics; alert if traffic does not decline.
7. **Remove v1 after sunset date.** Delete v1 controller + bean. Archive contract YAML under `docs/backend/deprecated-contracts/` (never delete).

## Deprecation & sunset headers

### RFC 9745 — `Deprecation` header

RFC 9745 defines `Deprecation` as an Item Structured Field whose value is a Unix timestamp (Section 2.1). The date indicates when the resource entered deprecation — it may be past or future:

```
Deprecation: @1751328000
```

Per Section 7, once the deprecation date has passed, clients must not assume stable behaviour. RFC 9745 Section 3 also defines a `deprecation` link relation for pairing with a `Link` header:

```
Deprecation: @1751328000
Link: <https://api.example.com/docs/migration/v2>; rel="deprecation"
```

### RFC 8594 — `Sunset` header

RFC 8594 defines `Sunset` as an HTTP-date string (Section 3) representing when the resource becomes unresponsive:

```
Sunset: Tue, 01 Jul 2027 00:00:00 GMT
```

Per RFC 9745 Section 4, the `Sunset` timestamp must not be earlier than the `Deprecation` timestamp. Clients treat it as a hint, not a hard guarantee.

### `@Operation(deprecated = true)`

Mark deprecated operations in the OpenAPI document using the Swagger annotation. springdoc renders them with a strikethrough in Swagger UI:

```kotlin
@Operation(
    deprecated = true,
    summary = "Place an order (deprecated — use /v2/orders)",
    description = "Deprecated since 2026-06-01. Sunset: 2027-01-01. Migrate to POST /v2/orders.",
)
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
fun place(@Valid @RequestBody req: PlaceOrderRequest): OrderResponse =
    placeOrder(req.toCommand()).toResponse()
```

The `deprecated: true` flag propagates to the OpenAPI 3.1 operation object (OAS spec Section 4.8.10), which `contract-drift-detective` can verify.

### Controller interceptor to inject headers

Use a `HandlerInterceptor` to inject `Deprecation` and `Sunset` headers for all requests matching the deprecated prefix — no per-method repetition:

```kotlin
// shared/infrastructure/http/DeprecationHeaderInterceptor.kt
@Component
class DeprecationHeaderInterceptor : HandlerInterceptor {

    private val deprecatedPaths: Map<String, DeprecationEntry> = mapOf(
        "/v1/" to DeprecationEntry(
            deprecationEpoch = 1751328000L,
            sunsetHttpDate   = "Tue, 01 Jul 2027 00:00:00 GMT",
            linkUrl          = "https://api.example.com/docs/migration/v2",
        ),
    )

    override fun postHandle(
        request: HttpServletRequest,
        response: HttpServletResponse,
        handler: Any,
        modelAndView: ModelAndView?,
    ) {
        val path = request.requestURI
        deprecatedPaths.entries
            .firstOrNull { (prefix, _) -> path.startsWith(prefix) }
            ?.let { (_, entry) ->
                response.setHeader("Deprecation", "@${entry.deprecationEpoch}")
                response.setHeader("Sunset", entry.sunsetHttpDate)
                response.addHeader("Link", "<${entry.linkUrl}>; rel=\"deprecation\"")
            }
    }

    data class DeprecationEntry(
        val deprecationEpoch: Long,
        val sunsetHttpDate: String,
        val linkUrl: String,
    )
}
```

Register it via `WebMvcConfigurer`:

```kotlin
// shared/infrastructure/http/WebMvcConfig.kt
@Configuration
class WebMvcConfig(
    private val deprecationHeaderInterceptor: DeprecationHeaderInterceptor,
) : WebMvcConfigurer {
    override fun addInterceptors(registry: InterceptorRegistry) {
        registry.addInterceptor(deprecationHeaderInterceptor)
    }
}
```

Adding a new deprecated version requires only one entry in `deprecatedPaths`. A v1 response will carry:

```http
Deprecation: @1751328000
Sunset: Tue, 01 Jul 2027 00:00:00 GMT
Link: <https://api.example.com/docs/migration/v2>; rel="deprecation"
```

## springdoc multi-version groups

### Bean configuration

```kotlin
// shared/infrastructure/openapi/OpenApiGroupConfig.kt
@Configuration
class OpenApiGroupConfig {

    @Bean
    fun v1ApiGroup(): GroupedOpenApi =
        GroupedOpenApi.builder()
            .group("v1")
            .pathsToMatch("/v1/**")
            .addOpenApiCustomizer { api ->
                api.info(Info().title("Example API").version("1.5.0")
                    .description("v1 — deprecated. Sunset: 2027-01-01. Use v2."))
            }
            .build()

    @Bean
    fun v2ApiGroup(): GroupedOpenApi =
        GroupedOpenApi.builder()
            .group("v2")
            .pathsToMatch("/v2/**")
            .addOpenApiCustomizer { api ->
                api.info(Info().title("Example API").version("2.0.0"))
            }
            .build()
}
```

### Endpoints exposed

| URL | Content |
|---|---|
| `/v3/api-docs/v1` | OpenAPI 3.1 JSON for `/v1/**` |
| `/v3/api-docs/v1.yaml` | OpenAPI 3.1 YAML for `/v1/**` |
| `/v3/api-docs/v2` | OpenAPI 3.1 JSON for `/v2/**` |
| `/v3/api-docs/v2.yaml` | OpenAPI 3.1 YAML for `/v2/**` |

### Dependencies and properties

Gradle (`springdoc-openapi 2.x` requires Spring Boot 4 + Java 17+):

```kotlin
implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.8.3")
```

```yaml
# application.yml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    groups-order: asc
  show-actuator: false
```

## Contract drift detection

The `contract-drift-detective` agent (`agents/contract-drift-detective.md`) runs at P7, after `backend-implementer`. Pass the version-specific springdoc URL:

```
springdoc_url: http://localhost:8080/v3/api-docs/v1
contract_path: .webstack/contracts/order-v1.yaml
```

Versioning-specific drift:

| Finding | Severity |
|---|---|
| `deprecated: false` in runtime, `deprecated: true` in contract | Critical — `@Operation(deprecated = true)` missing |
| Endpoint in v1 runtime, absent from v1 contract | Critical — undeclared endpoint (leakage) |
| `info.version` mismatch | Important — contract and runtime diverged |

`Deprecation`/`Sunset` response headers are not OpenAPI schema fields — verify with `curl -I` or an integration test. Full severity table and escalation protocol: `agents/contract-drift-detective.md`. Contract-first authoring workflow: `shared/methodologies/api-first.md`.

## Anti-patterns

**1. Mixing versioning strategies (header + URI).** `X-API-Version: 2` alongside `/v1/orders` creates two independent axes. CDNs cache by URL; the header is invisible. `GroupedOpenApi` cannot reconcile both.

**2. Removing a deprecated endpoint without a sunset window.** Deleting `/v1/` without `Deprecation`/`Sunset` headers breaks consumers silently. Minimum window: 3 months internal, 6 months public. Add headers on day 1 of deprecation.

**3. Labelling breaking changes as minor.** Removing a required field, renaming a path param, or changing a field type must go to `/v2/`. Shipping them under `/v1/` causes silent runtime failures.

**4. Version-less public endpoints.** An unversioned endpoint (e.g., `/orders`) cannot gain a version prefix later without breaking existing callers. Apply `/v1/` from the first deployment.

**5. Hard-coding version strings in business logic.** The version prefix is HTTP transport — it must not appear in domain classes or application services. Version-specific DTO shapes belong in v1/v2 controller/DTO layers; the domain layer is version-agnostic.

**6. Omitting `@Operation(deprecated = true)`.** `Deprecation`/`Sunset` headers inform runtime clients; `@Operation(deprecated = true)` informs tooling (Swagger UI, SDK generators, `contract-drift-detective`). Both are required.

**7. A single catch-all `GroupedOpenApi` bean.** `pathsToMatch("/**")` conflates all versions. No per-version spec, no Swagger UI version selector, `contract-drift-detective` cannot target a specific version.

## Sources

- **RFC 9745 — The Deprecation HTTP Header Field (IETF, 2025):** https://datatracker.ietf.org/doc/html/rfc9745 — _authoritative_
- **RFC 8594 — The Sunset HTTP Header Field (IETF, 2019):** https://datatracker.ietf.org/doc/html/rfc8594 — _authoritative_
- **OpenAPI Specification 3.1.0 — Operation Object § deprecated (OAI):** https://spec.openapis.org/oas/v3.1.0 — _authoritative; community: OpenAPI Initiative_
- **springdoc-openapi — GroupedOpenApi reference:** https://springdoc.org/ — _authoritative_
- **Zalando RESTful API Guidelines — versioning, deprecation, sunset:** https://opensource.zalando.com/restful-api-guidelines/ — _community: Zalando Engineering_

Last verified: 2026-05-04 (Spring Boot 4.0.X / springdoc-openapi 2.X / OpenAPI 3.1 / RFC 9745 + RFC 8594).
