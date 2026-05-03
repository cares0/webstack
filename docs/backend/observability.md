# Backend observability (Micrometer + OpenTelemetry + Logback)

> Reference for build-be SubAgent and backend-implementer.
> ⚙️ **Optional integration** — activated via init's "Observability" question (`manifest.optional_integrations.observability=true`). Until activated, this document is reference-only; setup steps live in `recipes/observability-setup.md`.
> Metrics, traces, and structured logs for Spring Boot 3.4 + Kotlin via Micrometer + OTel Java agent + Grafana OTel Distribution + Logback JSON.

## What is webstack BE observability

webstack backend observability is the unified collection of **metrics**, **traces**, and **structured logs** from a Spring Boot 3.4 + Kotlin application. The three signals answer:

- _Is the system healthy?_ — metrics (rate, error rate, latency)
- _What happened in this specific request?_ — traces (span tree across services)
- _What did the code say?_ — logs (structured JSON lines correlated to traces via `trace_id`)

The infrastructure side (collector, Grafana Cloud data sources, dashboards) lives in `docs/infrastructure/observability-stack.md`. This document covers application-side instrumentation only.

All three signals travel over **OTLP** (OpenTelemetry Protocol) — one protocol, one exporter configuration, any OTLP-capable backend.

```
Spring Boot Actuator           ← health, readiness/liveness probes
Micrometer                     ← metrics abstraction (@Timed, @Counted, @Observed)
  └─ micrometer-registry-otlp  ← OTLP metrics export
OTel Java agent (JAR)          ← auto-instrumentation + trace-log MDC bridge
  OR
Grafana OTel Distribution      ← Spring Boot auto-config wrapper for Grafana Cloud
logstash-logback-encoder       ← JSON log encoding + MDC field output
```

## Why Micrometer + OTel + Logback JSON

**Spring Boot 3 first-class support.** Spring Boot 3.0 adopted Micrometer's Observation API as its core abstraction. HTTP server, JDBC, and messaging produce observations automatically. `@Observed`, `@Timed`, and `@Counted` work via AspectJ. Spring Boot 3.4 ships an `OpenTelemetry` bean that wires `SdkTracerProvider`, `SdkMeterProvider`, and `SdkLoggerProvider` into Micrometer and Logback — no manual `OpenTelemetry.builder()` needed.

**CNCF standard — vendor-neutral.** Switching from Grafana Cloud to Honeycomb or Datadog is an env var change, not a code change.

**Free-tier compatible.** Grafana Cloud Free: Mimir 10 k active series, Tempo 50 GB/month, Loki 50 GB/month. A typical early-stage webstack project stays within these limits.

**LogstashEncoder.** `logstash-logback-encoder` (community: `logfellow` org, v9.x — Java 17 + Logback 1.5+) replaces pattern-layout with structured JSON. MDC entries — including `trace_id`/`span_id` injected by OTel — appear as top-level JSON fields automatically.

## Metrics — Micrometer

### Core meter types

| Meter | Use for |
|---|---|
| `Counter` | Monotonically increasing count (requests, errors) |
| `Gauge` | Instantaneous value (queue depth, active connections) |
| `Timer` | Duration + count + histogram (request latency) |
| `DistributionSummary` | Distribution without time semantics (payload size) |

### Annotation-based instrumentation

Enable in `application.yml` and add `spring-boot-starter-aop`:

```yaml
management:
  observations:
    annotations:
      enabled: true
```

```kotlin
// billing/application/CreateInvoiceService.kt
@Service
@Transactional
class CreateInvoiceService(private val invoiceRepository: InvoiceRepository) : CreateInvoiceUseCase {

    @Timed("billing.invoice.create", description = "Invoice creation latency")
    @Counted("billing.invoice.create.count")
    override fun execute(command: CreateInvoiceCommand): Invoice =
        invoiceRepository.save(Invoice.create(/* ... */))
}
```

`@Observed` records both a metric and a trace span together:

```kotlin
@Observed(name = "billing.payment.process", contextualName = "process-payment")
fun processPayment(invoice: Invoice): PaymentResult { /* ... */ }
```

### Custom `MeterRegistry`

For dynamic tags or conditional recording, inject `MeterRegistry` directly:

```kotlin
@Component
class InvoiceMetrics(registry: MeterRegistry) {
    private val processedCounter = Counter.builder("billing.invoice.processed")
        .description("Total invoices processed").register(registry)
    private val amountSummary = DistributionSummary.builder("billing.invoice.amount.cents")
        .baseUnit("cents").register(registry)

    fun recordProcessed(amountCents: Long) {
        processedCounter.increment()
        amountSummary.record(amountCents.toDouble())
    }
}
```

### Naming convention

Pattern: `<domain>.<verb>.<noun>` with dots. Micrometer normalises to backend convention at export (underscores for Prometheus/Mimir):

```
billing.invoice.created         ← counter
billing.invoice.duration        ← timer (_seconds, _count, _sum suffixes added by Micrometer)
billing.invoice.amount.cents    ← summary
http.server.requests            ← Spring auto-instrumented (do not override)
```

### Tags

**Low-cardinality only.** Unbounded values (user ID, invoice ID) explode time-series count — see Anti-patterns. Apply cross-cutting tags via config:

```yaml
management:
  observations:
    key-values:
      service: "billing-service"
      environment: "${ENVIRONMENT:local}"
```

### OTLP export

```kotlin
implementation("io.micrometer:micrometer-registry-otlp")
```

```yaml
management:
  otlp:
    metrics:
      export:
        url: "${OTEL_EXPORTER_OTLP_METRICS_ENDPOINT:http://localhost:4318/v1/metrics}"
        step: 60s
```

## Tracing — OpenTelemetry Java agent

### Auto-instrumentation

Attach `opentelemetry-javaagent.jar` at JVM startup via `JAVA_TOOL_OPTIONS`:

```yaml
# kubernetes/deployment.yaml (env section)
- name: JAVA_TOOL_OPTIONS
  value: "-javaagent:/opt/otel/opentelemetry-javaagent.jar"
- name: OTEL_SERVICE_NAME
  value: "billing-service"
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://otel-collector:4317"
- name: OTEL_EXPORTER_OTLP_PROTOCOL
  value: "grpc"
- name: OTEL_LOGS_EXPORTER
  value: "otlp"
```

The agent instruments Spring MVC, JDBC, `RestTemplate`/`WebClient`, Kafka, `@Async`, and `@Scheduled` automatically.

### Manual spans

`opentelemetry-api` is `compileOnly` — the agent provides it at runtime:

```kotlin
compileOnly("io.opentelemetry:opentelemetry-api")
```

```kotlin
@Service
class InvoicePdfService {
    private val tracer = GlobalOpenTelemetry.getTracer("billing")

    fun generatePdf(invoice: Invoice): ByteArray {
        val span = tracer.spanBuilder("billing.invoice.pdf.generate")
            .setAttribute("invoice.id", invoice.id.value).startSpan()
        return try { span.makeCurrent().use { generatePdfBytes(invoice) } }
        finally { span.end() }
    }
}
```

### Context propagation

The agent propagates context via `@Async`, `CompletableFuture`, and Reactor automatically. For manual thread pools:

```kotlin
@Bean
fun taskExecutor(): TaskExecutor =
    ThreadPoolTaskExecutor().apply {
        taskDecorator = ContextPropagatingTaskDecorator()
        initialize()
    }
```

### Sampling

Default: 100% (ParentBased + AlwaysOn). For production, use env vars — no code change:

```bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1    # 10% head-based
```

Tail-based sampling (collector-side) is covered in `docs/infrastructure/observability-stack.md`.

## Grafana OTLP starter (alternative)

The raw OTel Java agent requires manual OTLP endpoint, auth header, and resource attribute configuration per environment. The **Grafana OpenTelemetry Distribution for Java** (`grafana-opentelemetry-java`) is the webstack first pick for Grafana Cloud Free — it pre-configures Loki/Tempo/Mimir endpoints and auth headers from a single `grafana.otlp.cloud.*` block.

> **Note:** `com.grafana:grafana-opentelemetry-starter` (v1.4.0) was **archived June 2024**. Use `grafana-opentelemetry-java` (the Distribution) for new projects.

```kotlin
// build.gradle.kts
implementation("com.grafana:grafana-opentelemetry-java:2.x")
```

```yaml
# application.yml
grafana:
  otlp:
    cloud:
      zone: prod-us-east-0
      instanceId: "${GRAFANA_INSTANCE_ID}"
      apiKey: "${GRAFANA_OTLP_TOKEN}"
    global-attributes:
      service.version: "${APP_VERSION:dev}"
      deployment.environment: "${ENVIRONMENT:local}"
```

**Selection guide:**

| | OTel Java agent | Grafana OTel Distribution |
|---|---|---|
| Backend target | Any OTLP | Grafana Cloud / self-hosted Grafana |
| Auth wiring | Manual env vars | `grafana.otlp.cloud.*` block |
| Auto-instrumentation | Full (bytecode) | OTel Spring Boot Starter (reflection) |
| **webstack 1st pick (Grafana Cloud Free)** | No | **Yes** |

Use the OTel Java agent for non-Grafana backends (Honeycomb, Datadog, custom Tempo).

## Logs — Logback JSON encoder

### Dependency and configuration

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
      <!-- trace_id / span_id are populated automatically by OTel Logback bridge -->
      <includeMdcKeyName>trace_id</includeMdcKeyName>
      <includeMdcKeyName>span_id</includeMdcKeyName>
      <includeMdcKeyName>request_id</includeMdcKeyName>
    </encoder>
  </appender>

  <springProfile name="local">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
      <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level [%X{trace_id:-no-trace}] %logger{36} - %msg%n</pattern>
      </encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
  </springProfile>

  <springProfile name="!local">
    <root level="INFO"><appender-ref ref="JSON_CONSOLE"/></root>
  </springProfile>
</configuration>
```

### PII redaction hook

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
  <jsonGeneratorDecorator class="net.logstash.logback.mask.MaskingJsonGeneratorDecorator">
    <valueMask>
      <path>password</path><path>token</path><path>secret</path>
      <mask>****</mask>
    </valueMask>
  </jsonGeneratorDecorator>
</encoder>
```

The decorator masks structured field values. It does not catch PII embedded in message strings — see Anti-patterns §4.

### Injecting `request_id` via MDC

```kotlin
// shared/infrastructure/http/RequestIdFilter.kt
@Component
class RequestIdFilter : OncePerRequestFilter() {
    override fun doFilterInternal(req: HttpServletRequest, res: HttpServletResponse, chain: FilterChain) {
        val requestId = req.getHeader("X-Request-ID") ?: UUID.randomUUID().toString()
        MDC.put("request_id", requestId)
        res.setHeader("X-Request-ID", requestId)
        try { chain.doFilter(req, res) } finally { MDC.clear() }
    }
}
```

`trace_id` and `span_id` are set by the OTel SDK Logback bridge — no manual `MDC.put` needed.

## Trace-log correlation

The OTel Java agent installs a Logback `MDCHook` that injects `trace_id` and `span_id` into MDC for the duration of every span. `LogstashEncoder` includes all MDC entries as top-level JSON fields — no `%X{trace_id}` pattern variable required.

When Loki receives JSON logs with a `trace_id` field and Tempo holds traces with the same ID, Grafana navigates from a log line directly to the trace view. Enable the derived field in Loki's data source config (see `docs/infrastructure/observability-stack.md`).

```
HTTP request → OTel agent creates span (trace_id=abc123)
→ MDC.trace_id = "abc123"
→ log.info("Invoice created") → {"trace_id":"abc123", "message":"Invoice created"}
→ Downstream call carries W3C traceparent header
→ Grafana: click trace_id in Loki → Tempo span tree
```

## RED/USE metrics

### RED — request-scoped services

| Metric | Micrometer meter | webstack name pattern |
|---|---|---|
| **Rate** | `Counter` / `Timer.count` | `<domain>.<resource>.requests` |
| **Errors** | `Counter` + `status=error` tag | `<domain>.<resource>.errors` |
| **Duration** | `Timer` with percentile histogram | `<domain>.<resource>.duration` |

Spring auto-instruments `http.server.requests`. Apply the same pattern on custom boundaries:

```kotlin
@Timed(value = "billing.invoice.create", percentiles = [0.5, 0.95, 0.99], histogram = true)
override fun execute(command: CreateInvoiceCommand): Invoice { /* ... */ }
```

Example Grafana PromQL:

- Rate: `rate(billing_invoice_create_seconds_count[5m])`
- p95: `histogram_quantile(0.95, sum(rate(billing_invoice_create_seconds_bucket[5m])) by (le))`

### USE — resource-scoped infrastructure

| Metric | Source |
|---|---|
| **Utilization** — JVM heap, thread pool active/max | `management.metrics.enable.jvm=true` (auto) |
| **Saturation** — connection pool queue depth | HikariCP Micrometer integration (auto) |
| **Errors** — circuit breaker open, DB timeout | Custom counter / Resilience4j Micrometer |

## Health & readiness probes

```yaml
# application.yml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  health:
    livenessstate:
      enabled: true
    readinessstate:
      enabled: true
```

Spring Boot exposes `/actuator/health/liveness` (JVM alive) and `/actuator/health/readiness` (all dependencies ready) as separate paths.

**Do not** include database checks in the liveness probe — a transient DB timeout should drain traffic (readiness), not restart the pod (liveness). Register external checks as `HealthIndicator` beans; Spring Boot wires them into `/readiness` automatically.

Kubernetes probe configuration:

```yaml
livenessProbe:
  httpGet: { path: /actuator/health/liveness, port: 8080 }
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet: { path: /actuator/health/readiness, port: 8080 }
  initialDelaySeconds: 10
  periodSeconds: 5
```

Restrict management endpoints: expose `/actuator/health/liveness` and `/actuator/health/readiness` publicly; require an `ACTUATOR_ADMIN` role for all other paths (metrics, env, heapdump).

## Anti-patterns

**1. High-cardinality labels.** `tag("user_id", userId)` creates one time series per user, exhausting Grafana Cloud Free's 10 k active series limit. Only low-cardinality tags (status codes, payment methods, error types) belong on metrics. User-scoped correlation belongs in trace span attributes and MDC log fields.

**2. Tracing every method.** `@Observed` on every private domain method multiplies span count 10–100×. Trace at service boundaries: controllers, application services, outbound HTTP calls, DB queries, message producers/consumers. Skip domain methods, value object constructors, and utility functions.

**3. Unstructured log messages.** Embedding dynamic values in the message string prevents Loki from grouping identical events. Use `StructuredArguments.keyValue(...)` from `logstash-logback-encoder` to pass values as structured fields, keeping the message template stable.

```kotlin
// BAD  — unique message per user, unfilterable in Loki
log.info("User ${user.email} created invoice for ${amount.cents} cents")
// GOOD — stable template + structured field
log.info("Invoice created", StructuredArguments.keyValue("invoiceId", invoice.id.value))
```

**4. Logging PII directly.** `MaskingJsonGeneratorDecorator` only masks structured fields — it cannot redact PII in message strings. Never interpolate emails, phone numbers, or national IDs into log messages. Log a non-identifying ID instead (see `docs/backend/error-handling.md`).

**5. Exposing sensitive Actuator endpoints.** `/actuator/env`, `/actuator/beans`, and `/actuator/heapdump` expose internals. Limit `endpoints.web.exposure.include` to `health` for external traffic; require an authenticated role for everything else.

**6. Single `/health` for both K8s probe types.** A DB outage should drain traffic (readiness not-ready), not restart the pod (liveness kill). Always configure separate probes at the liveness and readiness paths.

## Sources

- **Micrometer — Concepts:** https://docs.micrometer.io/micrometer/reference/concepts.html — _authoritative_
- **OpenTelemetry — Zero-code Java agent:** https://opentelemetry.io/docs/zero-code/java/agent/ — _authoritative_
- **Grafana OpenTelemetry Distribution for Java:** https://github.com/grafana/grafana-opentelemetry-java — _authoritative_
- **logstash-logback-encoder (logfellow):** https://github.com/logfellow/logstash-logback-encoder — _community: logfellow org_
- **Spring Boot Reference — Observability:** https://docs.spring.io/spring-boot/reference/actuator/observability.html — _authoritative_

Last verified: 2026-05-04 (Spring Boot 3.4.X / Micrometer 1.13.X / OpenTelemetry Java 2.X / Grafana OpenTelemetry Distribution 2.X / Logback 1.5.X).
