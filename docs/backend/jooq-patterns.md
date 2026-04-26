# jOOQ Patterns

> Reference for build-be SubAgent. Covers jOOQ conventions in webstack as a complement to JPA: when to reach for it, how to wire codegen, the type-safe DSL, and Spring transaction integration.

## When jOOQ in webstack

JPA (see `docs/backend/jpa-patterns.md`) handles the write model and simple reads. jOOQ steps in when SQL becomes the natural language:

- **Complex reads.** Multi-table joins, window functions (`ROW_NUMBER()`, `LAG()`), CTEs, recursive queries, lateral joins. JPQL chokes on these; jOOQ writes them as SQL.
- **Reporting and analytics.** Dashboard aggregations, period-over-period comparisons, percentile/histogram views. jOOQ's typed DSL keeps these refactor-safe.
- **Bulk operations.** Batch inserts, multi-row upserts, deletes by predicate, bulk updates with subqueries. JPA's `cascade`/`merge` semantics fight you here.
- **Reads that don't fit a JPA aggregate.** A "user feed" combining posts + likes + author info is a query, not an aggregate root.

The split is not "all reads go through jOOQ." Simple reads (`findById`) stay in Spring Data JPA. Reach for jOOQ when SQL clarity wins.

## Setup

In `build.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm")
    id("nu.studer.jooq") version "9.0"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jooq")
    jooqGenerator("org.postgresql:postgresql")
}

jooq {
    version.set("3.19.13")
    configurations {
        create("main") {
            jooqConfiguration.apply {
                jdbc.apply {
                    driver = "org.postgresql.Driver"
                    url = "jdbc:postgresql://localhost:5432/${project.name}"
                    user = "postgres"
                    password = "postgres"
                }
                generator.apply {
                    name = "org.jooq.codegen.KotlinGenerator"
                    database.apply {
                        name = "org.jooq.meta.postgres.PostgresDatabase"
                        inputSchema = "public"
                        excludes = "flyway_schema_history"
                    }
                    target.apply {
                        packageName = "com.example.app.generated.jooq"
                        directory = "build/generated-src/jooq/main"
                    }
                }
            }
        }
    }
}
```

The Spring Boot jOOQ starter wires `DSLContext` as a Spring bean automatically. PostgreSQL is the webstack default; pick the matching dialect class for other databases.

## Code generation

Run `./gradlew generateJooq` to produce typed classes from the schema. webstack convention runs codegen against a Flyway-migrated test database (Testcontainers in CI) so generated classes always match the latest migration:

```kotlin
tasks.named("generateJooq") {
    dependsOn("flywayMigrate") // ensure schema is current first
}
```

Output appears at `build/generated-src/jooq/main/com/example/app/generated/jooq/`:

```text
generated/jooq/
├── tables/                 # one class per table: USER_, INVOICE, etc.
├── tables/records/         # row records: UserRecord, InvoiceRecord
├── tables/pojos/           # plain POJOs (optional, codegen-controlled)
├── DefaultSchema.kt
└── Tables.kt               # static accessors: USER, INVOICE
```

These classes are **generated** — never hand-edit, never review in PR. Add `build/generated-src/` to `.gitignore` and configure the `code-reviewer` SubAgent to skip it.

## Type-safe DSL

Queries compose as fluent calls; the result type is inferred from the SELECT projection.

```kotlin
import com.example.app.generated.jooq.Tables.INVOICE
import com.example.app.generated.jooq.Tables.CUSTOMER
import org.jooq.DSLContext
import org.springframework.stereotype.Component

@Component
class InvoiceQueryAdapter(private val dsl: DSLContext) {

    fun findRecentInvoiceSummaries(customerId: UUID, limit: Int): List<InvoiceSummaryDto> =
        dsl.select(
            INVOICE.ID,
            INVOICE.AMOUNT_CENTS,
            INVOICE.CURRENCY,
            INVOICE.STATUS,
            INVOICE.CREATED_AT,
            CUSTOMER.NAME.`as`("customerName"),
        )
            .from(INVOICE)
            .join(CUSTOMER).on(CUSTOMER.ID.eq(INVOICE.CUSTOMER_ID))
            .where(INVOICE.CUSTOMER_ID.eq(customerId))
              .and(INVOICE.STATUS.notEqual(InvoiceStatus.CANCELLED.name))
            .orderBy(INVOICE.CREATED_AT.desc())
            .limit(limit)
            .fetchInto(InvoiceSummaryDto::class.java)
}
```

- `select(...)` arguments are typed columns; the compiler rejects misspelled or wrong-table references.
- `.where(...).and(...)` chains predicates; `.or()` is also available, parenthesized via `DSL.condition(...)` when grouping is needed.
- `.fetchInto(<Class>)` maps result rows to a DTO by name match. `.fetchOneInto(...)`, `.fetchSingleInto(...)`, `.fetchOptionalInto(...)` for cardinality variants.

For aggregates and window functions:

```kotlin
import org.jooq.impl.DSL.*

dsl.select(
    INVOICE.STATUS,
    count().`as`("total"),
    sum(INVOICE.AMOUNT_CENTS).`as`("amountCentsTotal"),
)
    .from(INVOICE)
    .where(INVOICE.CREATED_AT.greaterOrEqual(LocalDate.now().minusDays(30).atStartOfDay().toInstant(ZoneOffset.UTC)))
    .groupBy(INVOICE.STATUS)
    .fetchInto(InvoiceStatusBucket::class.java)
```

For CTEs and window functions, `with(...).as(...)` and `over(partitionBy(...).orderBy(...))` mirror SQL syntax.

## Records vs DTOs

jOOQ generates two row representations:

- **Records** (`InvoiceRecord`) — table-shaped, mutable, with built-in `store()` / `update()` / `delete()` methods if you want active-record style. webstack avoids these in domain code; they bind your code to schema column order.
- **POJOs** (optional codegen mode) — immutable, table-shaped data classes. Acceptable as DTOs but still schema-shaped.
- **Custom DTOs** — your own data classes, projected via `.fetchInto(MyDto::class.java)`. webstack convention: **always use custom DTOs at the boundary**, like the JPA mapping pattern.

```kotlin
data class InvoiceSummaryDto(
    val id: UUID,
    val amountCents: Long,
    val currency: String,
    val status: String,
    val createdAt: Instant,
    val customerName: String,
)
```

Domain code consumes `InvoiceSummaryDto`; jOOQ-generated `InvoiceRecord` stays in the adapter. Mapping is automatic via `fetchInto` (snake_case column → camelCase property), which is one reason jOOQ pairs well with hexagonal: the boundary is naturally enforced.

## Transactions

`@Transactional` on the application service still owns the transaction boundary. The Spring Boot jOOQ starter wires `DSLContext` to Spring's `DataSourceTransactionManager` automatically — jOOQ calls participate in the same transaction as JPA calls.

```kotlin
@Service
class GenerateMonthlyReportUseCase(
    private val queryAdapter: InvoiceQueryAdapter,
    private val reportRepo: ReportRepository,
) {
    @Transactional
    fun run(month: YearMonth): Report {
        val rows = queryAdapter.findInvoicesForMonth(month) // jOOQ
        val report = Report.from(rows)
        return reportRepo.save(report) // JPA — same transaction
    }
}
```

Mixed JPA + jOOQ within a single transaction is supported and routine. Both eventually commit through the same `Connection`. Caveats:

- **JPA's first-level cache is invisible to jOOQ.** A jOOQ select after a JPA save sees the most recent flush. Use `entityManager.flush()` if jOOQ must see uncommitted JPA writes (rare; usually a sign you should split the operation).
- **Bulk `UPDATE` / `DELETE` via jOOQ** bypasses JPA's `@PreUpdate` / `@PreRemove` callbacks. Use jOOQ for true bulk operations only.

## webstack convention

- **Location.** jOOQ adapters live at `infrastructure/persistence/<feature>/<Use>QueryAdapter.kt`. They expose query methods returning DTOs to the application layer.
- **Codegen artifacts excluded from review.** `build/generated-src/jooq/` is gitignored; the code-reviewer SubAgent treats it as generated.
- **DTO boundary always.** Domain code never imports `*Record` types. `fetchInto(<MyDto>::class.java)` is the only return shape leaving the adapter.
- **Codegen runs on a Flyway-migrated test DB.** Schema drift between migrations and the generated classes shows up as a build failure on the next jOOQ task.
- **No SQL strings.** `.fetch(sql("SELECT * FROM..."))` exists but defeats type safety. Reserve for true bulk migrations and document the "why" inline.
- **Choose JPA or jOOQ per query, not per repository.** It is normal for one feature to expose a JPA-backed `InvoiceRepository.save` and a jOOQ-backed `InvoiceQueryAdapter.findRecentSummaries`.

## Sources

- jOOQ manual: https://www.jooq.org/doc/latest/manual/
- gradle-jooq-plugin: https://github.com/etiennestuder/gradle-jooq-plugin
- Spring Boot jOOQ starter: https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jooq
