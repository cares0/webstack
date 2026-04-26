# JPA Patterns

> Reference for build-be SubAgent. Covers JPA + Spring Data conventions in the webstack hexagonal architecture: entity mapping, identity, associations, the N+1 problem, transaction boundaries, the read-vs-write split, and migrations.

## JPA in webstack

JPA is an **infrastructure adapter**, not the domain model. The hexagonal split (see `shared/methodologies/hexagonal.md`) keeps the domain layer pure JVM — no Spring annotations, no `@Entity`, no `jakarta.persistence` imports. The persistence adapter wraps the domain with a JPA representation that knows how to load and save it.

This separation matters because:

1. **Domain rules stay verifiable in pure unit tests.** No Spring context, no in-memory DB.
2. **Schema decisions don't leak into business logic.** A field rename in the database doesn't ripple through the use cases.
3. **Multiple persistence strategies coexist.** A read-heavy projection can use jOOQ (see `docs/backend/jooq-patterns.md`) while writes go through JPA, all behind the same `Repository` port.

The cost is one mapping function per aggregate (`toDomain`, `fromDomain`). That cost is repaid the first time you change the storage layout without touching the domain.

## Entity annotations

A JPA entity is a Kotlin class annotated with `@Entity` and persistent via JPA. webstack convention: JPA entities live at `infrastructure/persistence/<aggregate>/`. Always pair with a domain class.

```kotlin
package com.example.app.billing.internal.persistence

import jakarta.persistence.*
import java.time.Instant
import java.util.UUID

@Entity
@Table(name = "invoice")
class InvoiceJpaEntity(
    @Id
    @Column(name = "id", nullable = false, columnDefinition = "uuid")
    val id: UUID,

    @Column(name = "amount_cents", nullable = false)
    var amountCents: Long,

    @Column(name = "currency", nullable = false, length = 3)
    var currency: String,

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    var status: InvoiceStatus,

    @Column(name = "created_at", nullable = false)
    val createdAt: Instant,

    @Column(name = "finalized_at")
    var finalizedAt: Instant? = null,

    @Version
    @Column(name = "version", nullable = false)
    var version: Long = 0,
)
```

- `@Table(name = ...)` — explicit table name, snake_case by webstack convention.
- `@Column(nullable = false, length = ...)` — explicit nullability and length; lets DDL tools generate accurate constraints.
- `@Enumerated(EnumType.STRING)` — never `EnumType.ORDINAL`; ordinals break when you reorder enum values.
- `@Version` — JPA optimistic locking; prevents lost updates without explicit row locks.

Avoid Lombok-style auto-properties for JPA entities; explicit constructors (and copy constructors via `copy()` at the boundary) are clearer.

## Identity strategy

webstack convention is **application-generated UUIDs** (UUIDv7 preferred for time-ordering, UUIDv4 acceptable). Generate the ID in the domain layer at aggregate construction:

```kotlin
package com.example.app.billing

import java.util.UUID

@JvmInline
value class InvoiceId(val value: UUID) {
    companion object {
        fun new(): InvoiceId = InvoiceId(UUID.randomUUID())
    }
}
```

The JPA entity stores it as a `uuid` column (PostgreSQL native), or `BINARY(16)` on databases without UUID type. This avoids:

- A round-trip to the database to fetch sequence values.
- Coupling new-aggregate creation to a transactional boundary.
- The "I have an Order but no orderId until flush" anti-pattern that breaks event publication ordering.

Sequence-based IDs (`@GeneratedValue(strategy = SEQUENCE)`) and `IDENTITY` columns are acceptable when integrating with legacy schemas, but the domain still wraps them in a value object (`OrderId`) so downstream code never holds raw `Long`.

## Association mapping

JPA's `@OneToMany`, `@ManyToOne`, and `@ManyToMany` define traversable relationships. Default to **lazy** for collections; enable eager only for tiny, always-needed lookups.

```kotlin
@Entity
@Table(name = "invoice")
class InvoiceJpaEntity(
    @Id val id: UUID,
    // ...
    @OneToMany(mappedBy = "invoice", cascade = [CascadeType.ALL], orphanRemoval = true, fetch = FetchType.LAZY)
    val lineItems: MutableList<LineItemJpaEntity> = mutableListOf(),
)

@Entity
@Table(name = "invoice_line_item")
class LineItemJpaEntity(
    @Id val id: UUID,

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "invoice_id", nullable = false)
    val invoice: InvoiceJpaEntity,

    @Column(name = "description", nullable = false)
    val description: String,

    @Column(name = "amount_cents", nullable = false)
    val amountCents: Long,
)
```

- **`fetch = LAZY` is the default for `@*ToMany`** in JPA, but explicit beats implicit. Always declare.
- **`@*ToOne` defaults to EAGER**, which causes surprising joins. Override to LAZY unless the related row is genuinely always needed.
- **`cascade = [ALL]` and `orphanRemoval = true`** make the parent the lifecycle owner. Removing a line item from `lineItems` deletes its row on flush.
- **Bidirectional associations** require explicit ownership — only one side has `@JoinColumn`. The other side has `mappedBy`.

In practice webstack avoids deep object graphs at the persistence boundary. The aggregate root maps to one entity; deeply related sub-aggregates have their own repositories. Cross-aggregate links are by ID (a `customerId: UUID` column, not a `@ManyToOne Customer`).

## N+1 problem

The N+1 anti-pattern: load N parents, then issue one query per parent to fetch its lazy collection — N+1 round trips. Detect via SQL log; mitigate by:

1. **`JOIN FETCH` in JPQL:**

   ```kotlin
   @Query("SELECT i FROM InvoiceJpaEntity i LEFT JOIN FETCH i.lineItems WHERE i.id = :id")
   fun findByIdWithLineItems(id: UUID): InvoiceJpaEntity?
   ```

2. **`@EntityGraph` annotation on Spring Data methods:**

   ```kotlin
   interface InvoiceJpaRepository : JpaRepository<InvoiceJpaEntity, UUID> {
       @EntityGraph(attributePaths = ["lineItems"])
       fun findById(id: UUID): InvoiceJpaEntity?
   }
   ```

3. **Programmatic `EntityGraph`** for dynamic shapes:

   ```kotlin
   val graph = entityManager.createEntityGraph(InvoiceJpaEntity::class.java)
   graph.addAttributeNodes("lineItems")
   entityManager.find(InvoiceJpaEntity::class.java, id, mapOf("jakarta.persistence.fetchgraph" to graph))
   ```

`JOIN FETCH` and `@EntityGraph` are equivalent in effect; pick one per repository for consistency. Never solve N+1 with eager fetch on the entity — it converts every load into an over-fetch even when the collection isn't needed.

For complex aggregations or projections, drop down to jOOQ or a JPQL `SELECT new` projection (see "Read vs write models" below).

## Repository pattern in webstack

The hexagonal repository is a **domain interface** in the domain layer; the adapter implements it in infrastructure. Spring Data is wrapped, not exposed.

```kotlin
// domain layer
package com.example.app.billing

interface InvoiceRepository {
    fun save(invoice: Invoice): Invoice
    fun findById(id: InvoiceId): Invoice?
    fun findByCustomer(customerId: CustomerId): List<Invoice>
}

// infrastructure layer
package com.example.app.billing.internal.persistence

import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Component

interface InvoiceJpaRepository : JpaRepository<InvoiceJpaEntity, UUID> {
    fun findAllByCustomerId(customerId: UUID): List<InvoiceJpaEntity>
}

@Component
class InvoiceRepositoryImpl(
    private val jpa: InvoiceJpaRepository,
) : InvoiceRepository {
    override fun save(invoice: Invoice): Invoice =
        jpa.save(invoice.toJpaEntity()).toDomain()

    override fun findById(id: InvoiceId): Invoice? =
        jpa.findById(id.value).orElse(null)?.toDomain()

    override fun findByCustomer(customerId: CustomerId): List<Invoice> =
        jpa.findAllByCustomerId(customerId.value).map { it.toDomain() }
}
```

The domain code only sees `InvoiceRepository`. Application services depend on the domain interface, never on Spring Data. Replacing Spring Data with jOOQ or a different ORM is a single-class swap.

Mapping functions `toDomain()` / `toJpaEntity()` live alongside the JPA entity, not inside the domain class — the domain must not know JPA exists.

## Transaction boundary

`@Transactional` belongs at the **application service** layer (use cases). Not on controllers (transaction lifetime exceeds the HTTP request). Not on repositories (each call would be its own transaction; multi-step flows would lose atomicity).

```kotlin
@Service
class PayInvoiceUseCase(
    private val invoices: InvoiceRepository,
    private val gateway: PaymentGateway,
    private val publisher: ApplicationEventPublisher,
) {
    @Transactional
    fun pay(id: InvoiceId, cardToken: String): PayInvoiceResult {
        val invoice = invoices.findById(id) ?: return PayInvoiceResult.NotFound
        val charge = gateway.charge(invoice.amount, cardToken)
        invoice.markPaid(charge.transactionId)
        invoices.save(invoice)
        publisher.publishEvent(InvoicePaid(invoice.id, invoice.amount))
        return PayInvoiceResult.Paid(charge.transactionId)
    }
}
```

For read-only operations: `@Transactional(readOnly = true)`. For nested calls that should join the existing transaction (default) vs require a new one (REQUIRES_NEW for outbox writes), set propagation explicitly. Avoid `Propagation.NEVER` and `Propagation.NESTED` unless you understand the savepoint semantics they imply.

Long-running transactions are an anti-pattern. If a use case spans external API calls plus DB writes, split it: write-then-publish-event, with the side effect handled in an `@TransactionalEventListener` after commit.

## Read vs write models

Single entity-graph for both read and write becomes painful as the read shape diverges from the write shape (UI lists need joined names; the write model needs only IDs). Apply **CQRS-lite**: keep the JPA aggregate for writes; add JPQL projections or jOOQ queries for reads.

JPQL projection to a DTO interface:

```kotlin
interface InvoiceListItem {
    val id: UUID
    val amountCents: Long
    val currency: String
    val status: InvoiceStatus
    val customerName: String
}

@Query("""
    SELECT i.id AS id, i.amountCents AS amountCents, i.currency AS currency,
           i.status AS status, c.name AS customerName
    FROM InvoiceJpaEntity i
    JOIN CustomerJpaEntity c ON c.id = i.customerId
    WHERE i.customerId = :customerId
    ORDER BY i.createdAt DESC
""")
fun findInvoiceListByCustomer(customerId: UUID): List<InvoiceListItem>
```

Spring Data implements the interface as an immutable proxy. Alternatively project to a `record` / data class via constructor expression.

For more complex reads (joins, window functions, aggregates), jOOQ is more readable than JPQL — see `docs/backend/jooq-patterns.md`.

## Migration

Spring Boot defaults to **Flyway** if `flyway-core` is on the classpath, or **Liquibase** if `liquibase-core` is. webstack default is Flyway for its plain-SQL approach.

```text
src/main/resources/db/migration/
├── V1__init.sql                  # initial schema
├── V2__add_invoice_table.sql
└── V3__add_finalized_at.sql
```

Naming: `V<version>__<description>.sql` (double underscore, lowercase description). Migrations run in order on app start. Never edit a committed migration; add a new V N+1 instead.

For test database setup, the same Flyway runs against the test DB (Testcontainers PostgreSQL preferred for integration). Domain tests stay pure JVM — no migrations needed.

Schema-managed-by-Spring (`spring.jpa.hibernate.ddl-auto=create`) is acceptable in throwaway tests but **never** in dev/staging/prod. Set `ddl-auto=validate` so the app refuses to start on schema drift; let Flyway own DDL.

## webstack convention

- **JPA entity location:** `com.example.app.<module>.internal.persistence.<Aggregate>JpaEntity.kt`. Mapping functions in the same file or a sibling `<Aggregate>Mapper.kt`.
- **Domain class location:** `com.example.app.<module>.<Aggregate>.kt` (no JPA annotations, no Spring imports).
- **Repository interface:** in the domain package (e.g., `com.example.app.billing.InvoiceRepository`). Implementation as `<Aggregate>RepositoryImpl` in `internal/persistence/`.
- **Identity:** application-generated UUID (UUIDv7 preferred). `<Aggregate>Id` value object wraps the UUID.
- **Migrations:** Flyway under `src/main/resources/db/migration/`. CI verifies migrations apply cleanly to a fresh test DB before PR merges.
- **Transaction boundary:** `@Transactional` on application service methods (use cases). `readOnly = true` for query handlers.
- **Read models:** JPQL projection or jOOQ for complex reads. Don't deepen the write model to satisfy the read.

## Sources

- Spring Data JPA: https://docs.spring.io/spring-data/jpa/reference/
- Hibernate User Guide: https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html
- Vlad Mihalcea's Hibernate articles: https://vladmihalcea.com
- Flyway: https://flywaydb.org/documentation/
