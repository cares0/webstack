# Logging strategy

> Reference for build-fe SubAgent and build-be SubAgent and security-auditor SubAgent.
> Structured logs with PII redaction and correlation_id propagation across FE Sentry, BE Logback JSON, and Vercel edge logs.

---

## What is webstack logging

webstack logging is a three-layer system that produces structured, correlated output across the entire request path.

```
Browser (Next.js / React)
  └─ Sentry SDK 9.x breadcrumbs + captureException
       └─ X-Request-Id header ──────────────────┐
                                                 ↓
                                       BE (Spring Boot 4.0 / Kotlin)
                                         └─ RequestIdFilter → MDC
                                              └─ Logback JSON (LogstashEncoder 9.x)
                                                   └─ trace_id / span_id (OTel MDC bridge)
                                                        └─ X-Request-Id response header

Vercel Edge / CDN
  └─ Vercel runtime logs (JSON, request-level)
       └─ correlation_id surfaces in x-request-id field
```

**Layer 1 — FE Sentry breadcrumbs.** The Sentry SDK records every navigation, fetch call, and console warning as a breadcrumb before an error event fires. Each breadcrumb is tagged with the `correlation_id` so the breadcrumb trail links to backend logs.

**Layer 2 — BE Logback JSON.** Spring Boot emits newline-delimited JSON via `LogstashEncoder`. Every line carries `trace_id`, `span_id` (OTel bridge), `request_id` (MDC), service name, level, logger, and structured message fields.

**Layer 3 — Vercel Edge logs.** Vercel captures per-invocation entries: method, path, status code, duration, region. Retention is short on Hobby (hours); drain to Grafana Cloud Loki to extend to 14 days.

Cross-references: `docs/backend/observability.md` (OTel trace-log correlation), `docs/frontend/error-monitoring.md` (Sentry setup), `docs/cross-cutting/owasp-top10-cheatsheet.md` §A09.

---

## Why structured + correlated

**Structured logs are filterable.** Every field is a typed JSON key. `{service="billing"} | json | level="ERROR" | request_id="abc-123"` returns exactly the matching lines. Unstructured text requires regex — slow and fragile.

**Correlation bridges FE and BE.** Without a shared `correlation_id`, finding the backend log for a frontend error requires guessing a time window. With one, the query is deterministic: copy `correlation_id` from the Sentry breadcrumb, search Loki by `request_id`.

**OTel `trace_id` is additive.** `trace_id`/`span_id` (OTel MDC bridge) point to Grafana Tempo traces; `request_id` (FE-generated) links Sentry breadcrumbs to BE logs. Both coexist in every log line.

**Operational impact.** Structured logs + alerting rules on `WARN`/`ERROR` reduce MTTD. Correlated IDs reduce MTTR. OWASP A09 requires audit-quality security event logging — see `docs/cross-cutting/owasp-top10-cheatsheet.md` §A09.

---

## Log levels

| Level | Meaning | Production default |
|---|---|---|
| `ERROR` | Unrecoverable — operator action required | 100% emitted |
| `WARN` | Recoverable but abnormal — investigate | 100% emitted |
| `INFO` | Normal operational milestones | 100% emitted |
| `DEBUG` | Diagnostic detail | 10% sampled (see §Sampling) |
| `TRACE` | Framework internals | Off in all non-local envs |

**Rules:**

- Root level: `INFO` in all non-local environments.
- Security events (`LoginResult.Invalid`, `AccessDeniedException`, JWT failure) always at `WARN`+.
- `TRACE` must not appear in committed code outside of `src/test/`.

**Environment overrides** via `logback-spring.xml` `<springProfile>`:

```xml
<springProfile name="local">
  <root level="DEBUG"><appender-ref ref="CONSOLE_PATTERN"/></root>
  <logger name="com.example.billing" level="TRACE"/>
</springProfile>

<springProfile name="!local">
  <root level="INFO"><appender-ref ref="JSON_CONSOLE"/></root>
</springProfile>
```

Or at runtime without redeployment via `application-{profile}.yml`:

```yaml
# application-staging.yml
logging:
  level:
    root: INFO
    com.example.billing: DEBUG
```

---

## Structured logging

Structured logging keeps the message template stable and passes dynamic values as named fields. This allows log aggregators to group identical events regardless of parameter values.

### BE — Logback `LogstashEncoder`

```kotlin
// build.gradle.kts
implementation("net.logstash.logback:logstash-logback-encoder:9.0")
```

```xml
<!-- src/main/resources/logback-spring.xml -->
<configuration>
  <springProperty scope="context" name="appName" source="spring.application.name"/>

  <appender name="JSON_CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <customFields>{"service":"${appName}"}</customFields>
      <includeMdcKeyName>trace_id</includeMdcKeyName>
      <includeMdcKeyName>span_id</includeMdcKeyName>
      <includeMdcKeyName>request_id</includeMdcKeyName>
      <!-- PII masking — see §PII redaction for full decorator config -->
    </encoder>
  </appender>

  <appender name="CONSOLE_PATTERN" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss} %-5level [%X{trace_id:-no-trace}] %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <springProfile name="local">
    <root level="DEBUG"><appender-ref ref="CONSOLE_PATTERN"/></root>
  </springProfile>
  <springProfile name="!local">
    <root level="INFO"><appender-ref ref="JSON_CONSOLE"/></root>
  </springProfile>
</configuration>
```

**Stable message templates in Kotlin** — use `StructuredArguments`:

```kotlin
import net.logstash.logback.argument.StructuredArguments.keyValue

// BAD — unique message per user, unfilterable in Loki
log.info("Invoice ${invoice.id} created for ${user.id}")

// GOOD — stable template + structured fields
log.info("Invoice created",
    keyValue("invoiceId", invoice.id.value),
    keyValue("userId", user.id.value),
    keyValue("amountCents", amount.cents))
```

Sample JSON output: `@timestamp`, `level`, `message`, `service`, `logger_name`, `trace_id`, `span_id`, `request_id`, and all `keyValue` fields appear as top-level JSON keys.

### FE — Sentry breadcrumb format

```ts
// src/shared/lib/logger.ts
import * as Sentry from '@/shared/lib/sentry'
import { getCorrelationId } from '@/shared/lib/correlationId'

export function logInfo(message: string, data?: Record<string, unknown>) {
  Sentry.addBreadcrumb({
    message,
    level: 'info',
    data: { ...data, correlation_id: getCorrelationId() },
    timestamp: Date.now() / 1000,
  })
}
```

### Edge — Vercel log drain

Vercel edge logs are JSON. To drain to Loki beyond Hobby's short retention:

```
Vercel Dashboard → Project → Settings → Log Drains → Add drain
  Destination: https://logs.grafana.net/loki/api/v1/push
  Format: JSON
  Sources: Edge, Serverless
```

---

## MDC correlation_id propagation

`correlation_id` (stored in MDC as `request_id`) is a UUID generated by the FE and propagated through the full request chain.

```
1. FE: crypto.randomUUID() → stored module-scope
2. FE: X-Request-Id header set on every fetch call
3. BE RequestIdFilter: reads header (or generates UUID if absent)
      → MDC.put("request_id", value)
      → res.setHeader("X-Request-Id", value)
4. All Logback JSON lines carry request_id (MDC thread-local)
5. FE reads X-Request-Id from response → tags Sentry breadcrumbs
```

**FE — correlation ID module and fetch wrapper:**

```ts
// src/shared/lib/correlationId.ts
let _id: string | null = null
export const getCorrelationId = (): string => (_id ??= crypto.randomUUID())
export const refreshCorrelationId = (): string => (_id = crypto.randomUUID())

// src/shared/api/fetchWithCorrelation.ts
export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  headers.set('X-Request-Id', getCorrelationId())
  return fetch(input, { ...init, headers })
}
```

**BE — `RequestIdFilter`:**

```kotlin
// shared/infrastructure/http/RequestIdFilter.kt
@Component
class RequestIdFilter : OncePerRequestFilter() {
    override fun doFilterInternal(
        req: HttpServletRequest, res: HttpServletResponse, chain: FilterChain,
    ) {
        val id = req.getHeader("X-Request-Id")?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString()
        MDC.put("request_id", id)
        res.setHeader("X-Request-Id", id)
        try { chain.doFilter(req, res) } finally { MDC.remove("request_id") }
    }
}
```

The filter runs before Spring Security so that failed-auth log lines also carry `request_id`. Attach `correlation_id` to every auto-captured Sentry breadcrumb via the `beforeBreadcrumb` hook shown in §Trace-log linkage.

---

## Trace-log linkage

`request_id` and OTel `trace_id` are additive — they answer different questions:

| Field | Generated by | Links to |
|---|---|---|
| `request_id` | FE (`crypto.randomUUID()`) | Sentry breadcrumb ↔ BE log line |
| `trace_id` | OTel Java agent (Logback MDC bridge) | BE log line ↔ Grafana Tempo span tree |
| `span_id` | OTel Java agent | Specific span within a trace |

The OTel Java agent installs a Logback `MDCHook` that calls `MDC.put("trace_id", ...)` and `MDC.put("span_id", ...)` for every log statement within an active span. `LogstashEncoder` outputs them as top-level JSON fields automatically — no manual `MDC.put` or `%X{trace_id}` pattern needed. See `docs/backend/observability.md` §Trace-log correlation for Grafana derived-field setup (Loki → Tempo link).

**Sentry breadcrumb carries both IDs:**

```ts
beforeBreadcrumb(breadcrumb) {
  const traceId = Sentry.getActiveSpan()?.spanContext().traceId
  return {
    ...breadcrumb,
    data: {
      ...(breadcrumb.data ?? {}),
      correlation_id: getCorrelationId(),
      ...(traceId ? { trace_id: traceId } : {}),
    },
  }
},
```

**End-to-end lookup:**

```
Sentry event → copy correlation_id
→ Loki: {service="billing"} | json | request_id="<value>"
→ copy trace_id from any line
→ Grafana Tempo → search trace_id → full span tree
```

---

## PII redaction

Two enforcement mechanisms operate at different layers and must both be active.

### BE — `MaskingJsonGeneratorDecorator` (field-level)

`MaskingJsonGeneratorDecorator` intercepts the JSON token stream and replaces matching field values before they reach the appender. Configure it on the `LogstashEncoder` (already shown in §Structured logging). Add regex-based value masking for patterns not caught by exact path names:

```xml
<jsonGeneratorDecorator
    class="net.logstash.logback.mask.MaskingJsonGeneratorDecorator">
  <!-- Path-based: exact JSON key names -->
  <valueMask>
    <path>password</path><path>token</path><path>secret</path>
    <path>authorization</path><path>creditCard</path><path>ssn</path>
    <path>nationalId</path><path>apiKey</path>
    <mask>****</mask>
  </valueMask>
  <!-- Value-based: regex patterns in any field -->
  <valueMask>
    <value>\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b</value><!-- email -->
    <value>\b(?:\d[ -]?){13,19}\b</value><!-- credit card -->
    <value>\b\d{3}-?\d{2}-?\d{4}\b</value><!-- SSN -->
    <mask>[REDACTED]</mask>
  </valueMask>
</jsonGeneratorDecorator>
```

**Limitation.** The decorator only covers structured fields (`StructuredArguments`, MDC). PII embedded directly in message strings bypasses it. Never interpolate emails or IDs into message templates — use `keyValue(...)` and log a non-identifying ID.

### FE — Sentry `beforeSend` hook (event-level)

`beforeSend` fires immediately before an event is transmitted to Sentry. Use it to strip or redact PII from error events:

```ts
// instrumentation-client.ts
const SENSITIVE_KEYS = new Set([
  'password', 'token', 'accessToken', 'refreshToken', 'secret',
  'authorization', 'apiKey', 'creditCard', 'ssn', 'email', 'phone',
])

function redact(obj: unknown): unknown {
  if (typeof obj !== 'object' || obj === null) return obj
  if (Array.isArray(obj)) return obj.map(redact)
  return Object.fromEntries(
    Object.entries(obj as Record<string, unknown>).map(([k, v]) =>
      [k, SENSITIVE_KEYS.has(k.toLowerCase()) ? '[Filtered]' : redact(v)]
    )
  )
}

Sentry.init({
  beforeSend(event) {
    if (event.user?.email) delete event.user.email
    if (event.request?.data) event.request.data = redact(event.request.data)
    if (event.extra) event.extra = redact(event.extra) as Record<string, unknown>
    return event
  },
})
```

**Safe fields** (permitted without redaction): `userId`, `invoiceId`, `orderId`, `requestId`, `traceId`, `spanId`, `statusCode`, `durationMs`, `module`, `feature`, `action`.

OWASP Logging Cheat Sheet prohibits logging: credentials, session IDs, access tokens, encryption keys, payment card data, government identifiers, and health data. See `docs/cross-cutting/owasp-top10-cheatsheet.md` §A09 for webstack-specific controls.

---

## Sampling

| Level | Production | Staging | Local |
|---|---|---|---|
| `ERROR` | 100% | 100% | 100% |
| `WARN` | 100% | 100% | 100% |
| `INFO` | 100% | 100% | 100% |
| `DEBUG` | 10% | 50% | 100% |
| `TRACE` | 0% | 0% | 100% |

**BE — Kotlin `TurboFilter` for DEBUG sampling:**

```kotlin
// shared/infrastructure/logging/DebugSamplingFilter.kt
class DebugSamplingFilter(private val sampleRate: Double = 0.10) : TurboFilter() {
    override fun decide(marker: Marker?, logger: Logger, level: Level,
                        format: String?, params: Array<out Any>?, t: Throwable?): FilterReply {
        if (level.levelInt >= Level.INFO.levelInt) return FilterReply.NEUTRAL
        return if (Random.nextDouble() < sampleRate) FilterReply.NEUTRAL else FilterReply.DENY
    }
}
```

Register in `logback-spring.xml` under `<springProfile name="!local">` as `<turboFilter class="...DebugSamplingFilter"><sampleRate>0.10</sampleRate></turboFilter>`.

**Large payloads** — gate explicitly:

```kotlin
if (log.isDebugEnabled && payload.length < 4096) {
    log.debug("Request body", keyValue("body", payload))
}
```

**FE breadcrumb** — drop high-volume noise via `beforeBreadcrumb`:

```ts
beforeBreadcrumb(breadcrumb) {
  if (breadcrumb.type === 'http' && (breadcrumb.data?.url as string)?.includes('/actuator/health')) {
    return null
  }
  return breadcrumb
},
```

---

## Retention

| Layer | Tool | Retention |
|---|---|---|
| FE errors + breadcrumbs | Sentry Cloud Free | 90 days / 5,000 errors per month |
| BE structured logs | Grafana Cloud Free (Loki) | 14 days / 50 GB per month |
| BE traces | Grafana Cloud Free (Tempo) | 14 days / 50 GB per month |
| Edge / function logs | Vercel Hobby (without drain) | ~1 hour runtime, ~1 day build |
| Edge / function logs | Vercel → Loki drain | 14 days (via Grafana Free) |

**Vercel Hobby action:** add a Loki log drain immediately after project creation. Without it, edge logs vanish within hours and incident investigation is impossible.

A typical early-stage project (< 100 req/min, INFO level, 10% DEBUG sampling) ingests well under 1 GB/month into Loki — comfortably within the 50 GB/month free quota.

---

## Anti-patterns

**1. `println` / `System.out.print`.** Bypasses Logback entirely — no level, no MDC, no JSON. Replace with `LoggerFactory.getLogger(javaClass)` and SLF4J calls.

**2. `e.printStackTrace()`.** Writes to `System.err` as unstructured multiline text with no log level or MDC context. Use `log.error("description", e)` — `LogstashEncoder` serializes the stack trace into the `stack_trace` JSON field.

**3. Logging passwords, tokens, or full JWTs.** Even for auth debugging. The credential becomes durable in Loki, Vercel logs, and potentially Sentry. Log a token prefix or a hash, never the full value.

**4. Unstructured dynamic values in message strings.** `log.info("User ${user.email} submitted order ${order.id}")` — unique message per user, not groupable in Loki, and may expose PII. Use `keyValue(...)` and keep the message template static.

**5. Distributed logs without a shared ID.** FE and BE logging independently with no `X-Request-Id` / MDC `request_id` correlation makes cross-layer debugging a guessing game. The `RequestIdFilter` + `apiFetch` wrapper from §MDC correlation_id propagation must be in place from day one.

**6. Catching exceptions and logging only the message.** `log.error("Save failed: ${e.message}")` loses the stack trace. Always pass `Throwable` as the second SLF4J argument: `log.error("Invoice save failed", e)` — `LogstashEncoder` serializes it into the `stack_trace` JSON field.

---

## Sources

- **Logback configuration manual:** https://logback.qos.ch/manual/configuration.html — _authoritative: QOS.ch_
- **logstash-logback-encoder (logfellow org):** https://github.com/logfellow/logstash-logback-encoder — _community: logfellow_
- **Sentry — Using beforeSend:** https://docs.sentry.io/platforms/javascript/configuration/filtering/#using-beforesend — _authoritative: Sentry_
- **OWASP Logging Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html — _community: OWASP_
- **OpenTelemetry — Zero-code Java agent (Logback MDC bridge):** https://opentelemetry.io/docs/zero-code/java/agent/ — _authoritative: OpenTelemetry_

Last verified: 2026-06-22 (Logback 1.5.X / LogstashEncoder 9.X / Sentry SDK 9.x / OpenTelemetry Java 2.X).
