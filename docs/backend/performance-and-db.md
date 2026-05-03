# Backend performance and database tuning

> Reference for build-be SubAgent and backend-implementer.
> Diagnose and resolve common performance bottlenecks in webstack's Spring Boot + JPA + Postgres backend.

## What is webstack performance

Performance in webstack is the observable throughput and latency of a Spring Boot 3.4 + Kotlin application backed by Postgres 16 on a single OCI A1 instance (Ampere ARM, free tier):

- **No horizontal scale.** Every slow query competes directly with application threads.
- **Supabase free tier.** ~60 direct connections / ~200 via pgBouncer. Extensions need `supabase_admin` — provision via the Supabase dashboard.
- **JPA + Hibernate 6.x** is an infrastructure adapter (see `docs/backend/jpa-patterns.md`). Unintended lazy-load queries are the most common latency source.
- **HikariCP pool is finite.** Slow queries hold connections longer, reducing concurrency.

Target budget: ≤ 5 DB queries per request (prefer 1–2), p99 < 200 ms, connection held < 100 ms.

## Why DB is the primary bottleneck

On a free-tier stack the database is almost always the first bottleneck:

1. **Connection exhaustion.** An N+1 loop or long-running transaction exhausts the pool before CPU or memory becomes the limit.
2. **Missing indexes.** A `Seq Scan` over 100 k rows on a 1-vCPU ARM instance can take hundreds of milliseconds; an Index Scan on the same predicate takes microseconds.
3. **Lock contention from migrations.** `ALTER TABLE … SET NOT NULL` on a populated table holds `ACCESS EXCLUSIVE` for the full scan, blocking all reads and writes. See `docs/backend/database-migrations.md` for expand-contract.
4. **N+1 is invisible without SQL logging.** Hibernate's lazy fetch triggers one SELECT per association access in a loop. Only a SQL proxy or statistics counter reveals it.

Diagnosis checklist: enable SQL statistics → detect N+1 → add/refine indexes → run `EXPLAIN ANALYZE` → tune pool.

## Diagnostic tools

### Hibernate `generate_statistics`

```yaml
# application-local.yml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
        session.events.log.LOG_QUERIES_SLOWER_THAN_MS: 50
```

Logs a summary at session close. `collections loaded` ≫ `entities loaded` = N+1. Add `logging.level.org.hibernate.stat=DEBUG` for per-session counts.

### p6spy — dev-only SQL proxy

Logs every statement with interpolated parameter values (unlike `show_sql`, which logs `?`):

```kotlin
runtimeOnly("com.github.gavlyukovskiy:datasource-proxy-spring-boot-starter:1.10.0")
```

```yaml
# application-local.yml
decorator.datasource.p6spy.enable-logging: true
```

Output includes execution time and the repository stack frame. **Never enable in production** — parameter values may contain PII.

### Spring Boot Actuator — HikariCP metrics

HikariCP exports via Micrometer automatically. Key meters:

- `hikaricp.connections.pending > 0` — pool saturation (real-time alert)
- `hikaricp.connections.timeout.total` — acquisitions that timed out

See `docs/backend/observability.md` for Micrometer/Grafana setup.

### `pg_stat_statements` — production

Enable via the Supabase dashboard (Extensions → pg_stat_statements):

```sql
SELECT left(query, 80) AS snippet, calls,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       round(total_exec_time::numeric, 2) AS total_ms
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
```

High `total_exec_time` = optimize first. High `calls` + low `mean_exec_time` = N+1 at aggregate level. Reset: `SELECT pg_stat_statements_reset();`

## N+1 detection and resolution

N+1 is the most common JPA performance defect: load N parent entities, then trigger one SELECT per parent to load a lazy association — N+1 round trips instead of 1. For entity mapping conventions see `docs/backend/jpa-patterns.md`.

### Detection

Symptoms: Hibernate stats show `collections loaded` ≫ `entities loaded`; p6spy logs a burst of `SELECT … WHERE invoice_id = ?` with different IDs; `pg_stat_statements` shows a low-selectivity foreign-key SELECT with high `calls`.

```kotlin
// Triggers N+1 — one SELECT per invoice to load lineItems
val invoices = invoiceRepo.findAllByCustomerId(customerId)
invoices.forEach { it.lineItems.sumOf { li -> li.amountCents } }
```

### Resolution 1 — `@EntityGraph(attributePaths)`

Adds a left outer join on the specific repository method. Does not affect other load sites:

```kotlin
interface InvoiceJpaRepository : JpaRepository<InvoiceJpaEntity, UUID> {
    @EntityGraph(attributePaths = ["lineItems"])
    fun findAllByCustomerId(customerId: UUID): List<InvoiceJpaEntity>
}
```

### Resolution 2 — `JOIN FETCH` in JPQL

```kotlin
@Query("""
    SELECT DISTINCT i FROM InvoiceJpaEntity i LEFT JOIN FETCH i.lineItems li
    WHERE i.customerId = :customerId ORDER BY i.createdAt DESC
""")
fun findAllWithLineItemsByCustomer(@Param("customerId") customerId: UUID): List<InvoiceJpaEntity>
```

`DISTINCT` prevents duplicate parent rows. With pagination, `JOIN FETCH` forces an in-memory count — prefer `@BatchSize` or DTO projections.

### Resolution 3 — `@BatchSize`

Batches lazy loads into `IN (?, …)` queries — avoids the cartesian product of fetching two collections with `JOIN FETCH`:

```kotlin
@OneToMany(mappedBy = "invoice", fetch = FetchType.LAZY)
@BatchSize(size = 25)
val lineItems: MutableList<LineItemJpaEntity> = mutableListOf()
```

100 invoices with `@BatchSize(25)` → 4 queries instead of 100. Global default: `hibernate.default_batch_fetch_size: 25`.

### Resolution 4 — DTO projection

Bypasses the persistence context; safe for `@Transactional(readOnly = true)`:

```kotlin
data class InvoiceSummary(val id: UUID, val amountCents: Long, val currency: String, val lineItemCount: Long)

@Query("""
    SELECT new com.example.app.billing.dto.InvoiceSummary(i.id, i.amountCents, i.currency, COUNT(li))
    FROM InvoiceJpaEntity i LEFT JOIN i.lineItems li
    WHERE i.customerId = :customerId
    GROUP BY i.id, i.amountCents, i.currency ORDER BY i.createdAt DESC
""")
fun findSummariesByCustomer(@Param("customerId") customerId: UUID): List<InvoiceSummary>
```

For window functions or complex joins, jOOQ is more readable — see `docs/backend/jooq-patterns.md`.

## Index strategy

Choose the index type by the data shape and query operator. Always create indexes via Flyway migrations (see `docs/backend/database-migrations.md`).

### B-tree (equality, range, sort)

The default. Covers `=`, `<`, `>`, `BETWEEN`, `ORDER BY`, and `IN` with small sets:

```sql
-- V10__billing_invoice_indexes.sql
CREATE INDEX idx_invoice_customer_id ON billing_invoice (customer_id);
CREATE INDEX idx_invoice_status      ON billing_invoice (status);
```

### GIN (JSONB and arrays)

Required for JSONB containment (`@>`) and array membership (`@>` / `?`). A B-tree on a JSONB column is useless for these operators:

```sql
CREATE INDEX idx_invoice_metadata_gin ON billing_invoice USING gin(metadata);
-- Query: WHERE metadata @> '{"channel": "stripe"}'
```

### Composite indexes — left-prefix rule

`(customer_id, created_at DESC)` supports `WHERE customer_id = ?` (prefix) and `WHERE customer_id = ? AND created_at > ?` (both columns). It does **not** accelerate `WHERE created_at > ?` alone — the leading column is absent.

Rule: equality columns first (highest selectivity), then range/sort columns:

```sql
CREATE INDEX idx_invoice_customer_created ON billing_invoice (customer_id, created_at DESC);
```

### Partial indexes

Index only rows matching a predicate — smaller, faster to update, more cache-friendly:

```sql
-- Only active invoices (small fraction of total rows)
CREATE INDEX idx_invoice_active
    ON billing_invoice (customer_id, created_at DESC)
    WHERE status IN ('PENDING', 'PROCESSING');
```

### Expression indexes

```sql
-- WHERE lower(email) = lower(?) — predicate must match the index expression exactly
CREATE INDEX idx_user_email_lower ON identity_user (lower(email));
```

### Covering indexes (`INCLUDE`)

Postgres 11+ `INCLUDE` enables index-only scans, avoiding a heap fetch:

```sql
CREATE INDEX idx_invoice_customer_covering
    ON billing_invoice (customer_id, created_at DESC)
    INCLUDE (status, amount_cents);
```

Effective when the query returns only the indexed + included columns (common for list endpoints).

## EXPLAIN ANALYZE workflow

Identify slow queries via `pg_stat_statements` in production or `LOG_QUERIES_SLOWER_THAN_MS: 25` in dev. Replace `?` placeholders with literal values, then:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.id, i.amount_cents, i.status
FROM billing_invoice i
WHERE i.customer_id = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
  AND i.status = 'PENDING'
ORDER BY i.created_at DESC LIMIT 20;
```

Read plans bottom-up. Key red flags:

| Signal | Likely cause | Action |
|---|---|---|
| `Seq Scan` on large table | Missing index | Add index on predicate column |
| Estimated rows ≪ actual rows | Stale statistics | `ANALYZE billing_invoice` |
| `Buffers: shared read` high | Cache miss | Add covering index |
| `loops=N` on expensive inner node | N+1 pattern | Rewrite or add index |
| `Sort Method: external merge Disk` | Sort spills to disk | Index with matching sort order |

After adding an index in a Flyway migration, re-run `EXPLAIN ANALYZE` to confirm `Index Scan` or `Bitmap Index Scan`. Record the before/after plan in the PR description.

## Cursor pagination

### Why offset pagination degrades

`OFFSET N LIMIT M` forces Postgres to scan and discard N rows on every request — O(offset). Page 1 000 with `LIMIT 20` processes 20 000 rows to return 20. Results also drift when rows are inserted or deleted between pages.

### Keyset (stable cursor) pagination

Keyset pagination replaces the offset with a `WHERE` predicate on the last-seen row's sort key, making deep pages O(1):

```sql
SELECT id, created_at, amount_cents
FROM billing_invoice
WHERE customer_id = ?
  AND (created_at, id) < (?, ?)   -- stable cursor: last seen values
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The row comparison `(created_at, id) < (?, ?)` maps directly to a B-tree range scan. Required index:

```sql
CREATE INDEX idx_invoice_cursor_pagination
    ON billing_invoice (customer_id, created_at DESC, id DESC);
```

### Kotlin implementation

```kotlin
// JPQL row-comparison equivalent: (createdAt, id) < (cursorCreatedAt, cursorId)
@Query("""
    SELECT new com.example.app.billing.dto.InvoiceListItem(
        i.id, i.createdAt, i.amountCents, i.currency, CAST(i.status AS string)
    )
    FROM InvoiceJpaEntity i
    WHERE i.customerId = :customerId
      AND (i.createdAt < :cursorCreatedAt
           OR (i.createdAt = :cursorCreatedAt AND i.id < :cursorId))
    ORDER BY i.createdAt DESC, i.id DESC
""")
fun findPageByCustomer(
    @Param("customerId") customerId: UUID,
    @Param("cursorCreatedAt") cursorCreatedAt: Instant,
    @Param("cursorId") cursorId: UUID,
    pageable: Pageable,
): List<InvoiceListItem>
```

The service encodes the last item's `(createdAt, id)` as a Base64 cursor, returned in the response envelope. For the first page, call a separate method without the `WHERE` cursor clause.

REST API design (cursor shape, response envelope, error codes) lives in `docs/cross-cutting/rest-api-design.md`. For multi-join queries, jOOQ's `seek(field1, field2)` is more readable — see `docs/backend/jooq-patterns.md`.

## Bulk insert/update

### `JdbcTemplate.batchUpdate`

JPA `saveAll()` issues one `INSERT` per entity. Bypass JPA for bulk imports (chunk to 500 rows):

```kotlin
jdbc.batchUpdate(
    "INSERT INTO billing_invoice (id, customer_id, amount_cents, status, created_at, version) VALUES (?, ?, ?, ?, ?, 0)",
    invoices.chunked(500).flatMap { batch ->
        batch.map { arrayOf(it.id, it.customerId, it.amountCents, it.status.name, it.createdAt) }
    }
)
```

### `INSERT … ON CONFLICT` (upsert)

For idempotent writes in event-driven flows:

```kotlin
jdbc.update(
    "INSERT INTO billing_invoice (id, amount_cents, status) VALUES (?, ?, ?) " +
    "ON CONFLICT (id) DO UPDATE SET amount_cents = EXCLUDED.amount_cents, status = EXCLUDED.status",
    invoice.id, invoice.amountCents, invoice.status.name,
)
```

### JPA flush tuning

`FlushModeType.AUTO` flushes before every query that may be affected by pending writes. For bulk imports, defer to commit and evict the first-level cache between chunks:

```kotlin
@Transactional
fun importInvoices(commands: List<ImportInvoiceCommand>) {
    entityManager.flushMode = FlushModeType.COMMIT
    commands.chunked(200).forEach { batch ->
        batch.forEach { jpaRepo.save(it.toEntity()) }
        entityManager.flush()
        entityManager.clear()  // prevents first-level cache memory growth
    }
}
```

## Connection pool

### HikariCP defaults

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10       # ≤ 10 for Supabase free tier (~60 direct connections total)
      minimum-idle: 2
      connection-timeout: 30000   # ms
      idle-timeout: 600000        # ms — 10 min
      max-lifetime: 1800000       # ms — 30 min; must be < Supabase session timeout
      keepalive-time: 60000       # ms
      leak-detection-threshold: 5000  # ms — log stack trace for connections held > 5 s (dev)
```

### Supabase pgBouncer — transaction mode and prepared statements

pgBouncer on port 6543 runs in **transaction mode**: connections return to the pool after each transaction, greatly increasing concurrency. The catch: **prepared statements are session-scoped** at Postgres but pgBouncer routes transactions to different backend connections. The prepared statement is invisible on the next connection.

Disable prepared statements when using pgBouncer:

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://<host>:6543/<db>?prepareThreshold=0"
    hikari:
      data-source-properties:
        prepareThreshold: "0"
```

For workloads that need prepared statements (jOOQ named params), use the direct connection URL (port 5432) for that data source and pgBouncer for the main pool.

## Anti-patterns

**1. `@OneToMany(fetch = EAGER)`** — loads the collection for every entity load, even when unused. Use `LAZY` + `@EntityGraph` / `JOIN FETCH` on the specific repository method that needs the association.

**2. `findAll()` without projection** — loads every column. A JSONB column on a 4-field list view transfers megabytes unnecessarily. Use JPQL constructor expressions or Spring Data interface projections.

**3. Unindexed `ORDER BY` and foreign keys** — `ORDER BY created_at` without an index shows as `Sort Method: external merge Disk` in `EXPLAIN ANALYZE`. Every FK column (`customer_id`, `invoice_id`) needs a B-tree index.

**4. `JOIN FETCH` on two `@OneToMany` collections** — produces a cartesian product:

```kotlin
// 100 invoices × 10 line items × 5 attachments = 5 000 rows
@Query("SELECT i FROM InvoiceJpaEntity i JOIN FETCH i.lineItems JOIN FETCH i.attachments")
fun findAll(): List<InvoiceJpaEntity>
```

Fix: `@BatchSize` on the second collection, or load each association in separate queries.

**5. Deep offset pagination** — `PageRequest.of(page, 20)` emits `LIMIT 20 OFFSET (page × 20)`. Page 5 000 scans 100 000 rows. Use keyset pagination for lists that can grow deep.

**6. `ALTER TABLE … NOT NULL` without expand-contract** — holds `ACCESS EXCLUSIVE` for the full backfill scan. See `docs/backend/database-migrations.md`.

**7. Long-running transactions holding connections** — a use case calling an external API inside `@Transactional` holds a connection for the full call duration. Split: DB write → publish outbox event → commit → handle the external call in `@TransactionalEventListener(phase = AFTER_COMMIT)`.

## Sources

- **Spring Data JPA Reference:** https://docs.spring.io/spring-data/jpa/reference/ — _authoritative_
- **Hibernate ORM 6.6 User Guide — Fetching:** https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html — _authoritative_
- **PostgreSQL 16 — Using EXPLAIN:** https://www.postgresql.org/docs/16/using-explain.html — _authoritative_
- **PostgreSQL 16 — Indexes:** https://www.postgresql.org/docs/16/indexes.html — _authoritative_
- **Vlad Mihalcea — N+1 Query Problem:** https://vladmihalcea.com/n-plus-1-query-problem/ — _community: Vlad Mihalcea, Hibernate committer_
- **datasource-proxy-spring-boot-starter (p6spy / datasource-proxy):** https://github.com/gavlyukovskiy/spring-boot-data-source-decorator — _community: Gavlyukovskiy_

Last verified: 2026-05-04 (Spring Boot 3.4.X / Hibernate 6.X / Postgres 16.X / Kotlin 2.X).
