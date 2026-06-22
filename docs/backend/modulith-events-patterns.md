# Modulith events patterns (idempotent + retry + Saga)

> Reference for build-be SubAgent and backend-implementer and feature-architect SubAgent.
> Cross-module collaboration via Spring Modulith published events: idempotent listeners, retry policy, Saga, outbox monitoring.

## What is Modulith event publication

Spring Modulith's **event publication registry** implements the transactional outbox pattern inside a single Spring Boot application, with no external message broker. When a `@Transactional` service publishes a domain event via `ApplicationEventPublisher`, Modulith atomically writes one log entry per registered `@ApplicationModuleListener` into the `event_publication` table as part of the **same database transaction**. After commit, each listener is invoked asynchronously. On success the entry is marked complete; on failure the entry remains for retry.

### `@ApplicationModuleListener`

`@ApplicationModuleListener` is Modulith's cross-module listener annotation. It is equivalent to:

```kotlin
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
```

- `AFTER_COMMIT` — never fires if the publisher rolls back.
- `@Async` — runs on a separate thread, decoupled from the publisher's HTTP thread.
- `REQUIRES_NEW` — own transaction; listener failure does not roll back the publisher's committed state.

```kotlin
// order/OrderInvoicePaidHandler.kt
@Component
class OrderInvoicePaidHandler(private val orderService: OrderService) {

    @ApplicationModuleListener
    fun on(event: InvoicePaid) {
        orderService.recordPayment(event.invoiceId, event.amount)
    }
}
```

### `event_publication` table

Modulith creates this table via its bundled Flyway migration when `spring-modulith-starter-jpa` is on the classpath.

| Column | Purpose |
|---|---|
| `id` (UUID PK) | Unique publication identifier |
| `listener_id` | Qualified listener method name |
| `serialized_event` | JSON payload |
| `publication_date` | When published |
| `completion_date` | NULL = incomplete; set on success |
| `status` | `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RESUBMITTED` (Modulith 2.0+) |

### Build dependencies (Spring Boot 4.0)

```kotlin
// build.gradle.kts
implementation(platform("org.springframework.modulith:spring-modulith-bom:2.0.6"))
implementation("org.springframework.modulith:spring-modulith-starter-jpa")
```

Verify the latest 2.x release at https://github.com/spring-projects/spring-modulith/releases.

---

## Why durable async events

**Module decoupling.** Direct service calls between Modulith modules are forbidden by the boundary verifier (see `docs/backend/spring-modulith.md`). Events are the designed channel. The registry makes them durable: JVM crashes between publication and listener invocation do not lose events — the `event_publication` row survives and is available for replay.

**Transactional outbox inside the monolith.** The outbox entries and the business tables share the same `DataSource` and the same JDBC transaction. There is no separate polling process and no message broker. This gives webstack outbox-pattern reliability at monolith operational simplicity.

**Avoiding distributed transactions.** Cross-module state changes would require 2PC if the modules were separate services. Inside a Modulith, the publication registry provides at-least-once delivery with eventual consistency — no 2PC, no Saga coordinator. Failure is localized: the publisher's committed state is not undone by a listener failure.

---

## webstack convention

### Event class placement

| Event type | Location |
|---|---|
| Public (cross-module) | Module root: `com.example.app.<module>/` |
| Internal (intra-module) | `com.example.app.<module>/domain/<aggregate>/` |

Public events are the module's published API — any module may subscribe. Internal events may not be imported from outside; the verifier enforces this.

### Naming

Pattern: `<Aggregate><PastTense>`. Examples: `OrderPlaced`, `InvoicePaid`, `PaymentFailed`, `InventoryReserved`.

Anti-pattern: `OrderEvent`, `PaymentMessage` — no aggregate, no verb.

### Event class structure

Events are immutable data classes carrying only identifiers and scalar values, never aggregate root references. Include a stable `eventId: UUID` field for idempotency:

```kotlin
// order/OrderPlaced.kt
data class OrderPlaced(
    val eventId: UUID = UUID.randomUUID(),
    val orderId: OrderId,
    val customerId: CustomerId,
    val totalCents: Long,
    val placedAt: Instant = Instant.now(),
)
```

---

## Idempotency

`@ApplicationModuleListener` has at-least-once delivery. A partial success followed by a throw causes the same listener to re-run on retry, potentially producing duplicate side effects (double charges, duplicate rows).

### `processed_events` table

Create a deduplication table in the module that owns the listener:

```sql
-- V2__create_processed_events.sql
CREATE TABLE processed_events (
    event_id     UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The `PRIMARY KEY` constraint is the deduplication gate. A duplicate insert throws a constraint violation, which short-circuits duplicate processing.

### Idempotent listener pattern

```kotlin
@Component
class PaymentOrderPlacedHandler(
    private val processedEvents: ProcessedEventRepository,
    private val paymentService: PaymentService,
) {

    @ApplicationModuleListener
    fun on(event: OrderPlaced) {
        if (processedEvents.existsByEventId(event.eventId)) return
        paymentService.initiatePayment(event.orderId, event.customerId, event.totalCents)
        processedEvents.save(ProcessedEvent(eventId = event.eventId))
    }
}
```

For higher throughput, replace the existence-check with a single `INSERT … ON CONFLICT DO NOTHING`:

```kotlin
fun tryInsert(eventId: UUID): Boolean =
    jdbc.update(
        "INSERT INTO processed_events (event_id) VALUES (?) ON CONFLICT DO NOTHING",
        eventId,
    ) == 1  // false = duplicate, skip business logic
```

The listener's `REQUIRES_NEW` transaction commits the business state change and the `processed_events` row atomically on success.

---

## Retry policy

### Restart resubmission

Enable automatic replay of outstanding publications on application start:

```yaml
spring:
  modulith:
    events:
      republish-outstanding-events-on-restart: true
```

This is the minimum retry policy for webstack. It recovers from JVM crashes without operator intervention.

### Staleness monitor (production)

In long-running deployments a publication can get stuck in `PROCESSING` (JVM killed mid-listener). Configure the staleness monitor to mark stale entries as `FAILED`:

```yaml
spring:
  modulith:
    events:
      staleness:
        published: 3600    # seconds before marking PUBLISHED as FAILED
        processing: 1800
        resubmitted: 1800
```

All three default to 0 (disabled). Enable in production.

### Programmatic replay

```kotlin
@Component
class EventReplayScheduler(
    private val incomplete: IncompleteEventPublications,
    private val failed: FailedEventPublications,
) {
    // Replay incomplete every 5 minutes
    @Scheduled(fixedDelay = 300_000)
    fun replayIncomplete() {
        incomplete.resubmitIncompletePublications(
            ResubmissionOptions.defaults()
                .withBatchSize(50)
                .withMinAge(Duration.ofMinutes(5)),
        )
    }

    // Replay failed every 15 minutes, up to 5 attempts
    @Scheduled(cron = "0 */15 * * * *")
    fun replayFailed() {
        failed.resubmit(
            ResubmissionOptions.defaults()
                .withBatchSize(20)
                .withFilter { pub -> pub.completionAttempts < 5 },
        )
    }
}
```

Publications exceeding the attempt threshold stay `FAILED` and require manual resolution.

---

## Saga pattern

### Choreography-based Sagas

webstack implements multi-step business transactions as **choreography-based Sagas**: each module reacts to events from the previous step and publishes the next event. There is no central Saga orchestrator and no Saga library dependency. Durability comes from the event publication registry.

### Order placement example

**Happy path:** `OrderPlaced` → `PaymentSucceeded` → `OrderConfirmed`

**Failure path:** `OrderPlaced` → `PaymentFailed` → `OrderCancelled`

```kotlin
// payment/PaymentOrderPlacedHandler.kt — Step 2
@Component
class PaymentOrderPlacedHandler(
    private val paymentService: PaymentService,
    private val publisher: ApplicationEventPublisher,
) {
    @ApplicationModuleListener
    fun on(event: OrderPlaced) {
        try {
            paymentService.chargeCustomer(event.customerId, event.totalCents)
            publisher.publishEvent(PaymentSucceeded(orderId = event.orderId))
        } catch (ex: PaymentDeclinedException) {
            publisher.publishEvent(PaymentFailed(orderId = event.orderId, reason = ex.message ?: "DECLINED"))
        }
    }
}

// order/OrderPaymentFailedHandler.kt — compensating step
@Component
class OrderPaymentFailedHandler(
    private val orderService: OrderService,
    private val publisher: ApplicationEventPublisher,
) {
    @ApplicationModuleListener
    fun on(event: PaymentFailed) {
        orderService.cancelOrder(event.orderId, event.reason)
        publisher.publishEvent(OrderCancelled(orderId = event.orderId, reason = event.reason))
    }
}
```

### Compensating events

`OrderCancelled` is the compensation for `OrderPlaced`. The compensating listener must explicitly reverse the state change — the original transaction is already committed. Name compensating events clearly; they are first-class domain events with their own idempotency requirements.

### Saga state tracking

Each module tracks its own state only (`order.status`, `payment.status`). To query overall Saga progress, project it from a read-side query across the participating modules' state tables, not via a shared mutable Saga entity.

---

## Outbox monitoring

### Pending publications as a health signal

A growing count of rows with `completion_date IS NULL` indicates listeners are failing. Expose this as a Micrometer gauge:

```kotlin
// shared/infrastructure/events/EventPublicationMetrics.kt
@Component
class EventPublicationMetrics(jdbc: JdbcTemplate, registry: MeterRegistry) {
    init {
        Gauge.builder("modulith.event_publication.pending") {
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM event_publication WHERE completion_date IS NULL",
                Long::class.java,
            ) ?: 0L
        }
            .description("Incomplete event publications awaiting retry")
            .register(registry)
    }
}
```

The gauge is exported via OTLP to Grafana (see `docs/backend/observability.md` for Micrometer naming conventions and OTLP exporter configuration).

### Alert thresholds

| Condition | Severity |
|---|---|
| `pending > 0` for > 10 min | Warning — check listener logs |
| `pending > 10` for > 30 min | Critical — persistent failure loop |
| `pending` growing monotonically | Critical — resubmission scheduler disabled |

### Debugging query

```sql
SELECT id, listener_id, publication_date, status
FROM event_publication
WHERE completion_date IS NULL
  AND publication_date < NOW() - INTERVAL '5 minutes'
ORDER BY publication_date ASC;
```

---

## Cross-aggregate consistency

### BASE, not ACID

Cross-module interactions are **eventually consistent**. The publishing module commits its state; the subscribing module's listener commits in a separate transaction. Between publisher commit and listener commit the system is in an intermediate state. This is correct: distributed ACID across module boundaries requires 2PC, which webstack avoids by design.

### UI fallback messages

The API response returns as soon as the primary aggregate's transaction commits. Downstream effects have not yet completed. Guidelines:

- Return the primary aggregate's ID and status immediately (e.g., `order.status = PENDING`).
- Expose a separate read endpoint for downstream state (e.g., payment status) that queries the downstream module's own table.
- Show an in-progress message: "Your order has been placed. Payment is being processed."

### Cross-module references by ID only

Events carry only identifier value objects. The receiving module looks up its own aggregate by ID if richer data is needed.

```kotlin
// CORRECT
data class OrderPlaced(val orderId: OrderId, val customerId: CustomerId, val totalCents: Long)

// WRONG — aggregate references across module boundary
data class OrderPlaced(val order: Order, val customer: Customer)
```

---

## Performance considerations

### `@Async` thread pool

`@ApplicationModuleListener` delegates to `@Async`, which uses Spring Boot's default `applicationTaskExecutor`. Under high event throughput, configure a dedicated executor:

```kotlin
@Configuration
@EnableAsync
class AsyncConfig {

    @Bean(name = ["modulithTaskExecutor"])
    fun modulithTaskExecutor(): TaskExecutor =
        ThreadPoolTaskExecutor().apply {
            corePoolSize = 4
            maxPoolSize = 16
            queueCapacity = 500
            threadNamePrefix = "modulith-async-"
            setTaskDecorator(ContextPropagatingTaskDecorator()) // propagates OTel trace context
            initialize()
        }
}
```

`ContextPropagatingTaskDecorator` is required for trace context propagation (see `docs/backend/observability.md`). Without it, listener spans appear as root spans with no connection to the originating request.

### Transaction phase is always `AFTER_COMMIT`

The listener fires **after** the publisher's transaction commits, never during it. This means:

- The publisher's HTTP response returns as soon as its transaction commits; listener latency is outside that window.
- A slow listener does not hold the publisher's database connection.
- A listener failure does not roll back the publisher's committed state.

For intra-module events that must execute **within** the publisher's transaction, use a plain `@EventListener` instead of `@ApplicationModuleListener`. A plain `@EventListener` is invoked **synchronously and inline** on the publishing thread at the point `publishEvent(...)` is called, so it simply runs inside whatever transaction is already active on that thread (it does not start or guarantee one of its own) — a listener exception propagates back to the publisher and rolls the shared transaction back. When you instead need to bind to a transaction phase (e.g. run only `AFTER_COMMIT`), `@TransactionalEventListener` is the phase-bound tool.

### Payload size

The `serialized_event` column stores the event as JSON. Large payloads bloat the table and increase deserialization cost. Keep payloads minimal: identifiers + scalar values. Listeners fetch the full aggregate from their own repository if needed.

---

## Anti-patterns

**1. Synchronous call bypass.** Replacing `publisher.publishEvent(...)` with a direct `otherModuleService.doSomething(...)` call violates the Modulith boundary, disables registry durability, and makes the interaction synchronous. Tune the listener's thread pool if it is slow; do not abandon the event model.

**2. Retry without idempotency.** Enabling `republish-outstanding-events-on-restart` or a replay scheduler without an idempotency guard will process events multiple times on retry. Retry and idempotency are a coupled pair — implement `processed_events` before enabling retry.

**3. Large payloads.** Serializing full JPA entities or nested object graphs into event payloads bloats the `event_publication` table, tightly couples the event schema to aggregate internals, and breaks listeners when the aggregate changes. Events carry IDs and scalar values only.

**4. Domain object references in events.** Carrying an aggregate instance from another module in an event payload creates a hidden cross-module dependency (via the event type's classpath) that the verifier may not catch. Use value objects and primitive types; put shared identifier types in a `shared/` module.

**5. `PROPAGATION_REQUIRES_NEW` overuse.** `@ApplicationModuleListener` already applies `REQUIRES_NEW`. Adding more nested `REQUIRES_NEW` transactions inside a listener creates unpredictable rollback boundaries and potential deadlocks. Keep all database operations inside the listener's single transaction.

**6. Dual write (event + direct call).** Publishing an event **and** making a direct service call for "immediate consistency" creates two codepaths that must stay synchronized. The listener will process an event the direct call already handled, causing duplication. The event is the single write.

---

## Sources

- **Spring Modulith — Working with Application Events:** https://docs.spring.io/spring-modulith/reference/events.html — _authoritative_
- **Spring Modulith — Reference Documentation:** https://docs.spring.io/spring-modulith/reference/ — _authoritative_
- **Spring Modulith GitHub — spring-projects/spring-modulith:** https://github.com/spring-projects/spring-modulith — _authoritative_
- **Chris Richardson — Transactional Outbox Pattern:** https://microservices.io/patterns/data/transactional-outbox.html — _community: microservices.io_
- **Chris Richardson — Saga Pattern:** https://microservices.io/patterns/data/saga.html — _community: microservices.io_

Last verified: 2026-06-22 (Spring Modulith 2.X / Spring Boot 4.0.X / Kotlin 2.X).
