# Database Migrations

> Reference for build-be SubAgent and backend-implementer.

Flyway conventions (BOM-managed: Flyway 11.x with Spring Boot 4), expand-contract zero-downtime migrations, batch backfill, Testcontainers PR dry-runs, and rollback policy for webstack's Spring Boot + Supabase Postgres stack.

## What is Flyway in webstack

Flyway is a **database migration tool** that versions schema changes as plain SQL scripts committed alongside application code. Spring Boot auto-applies pending migrations at startup. On Spring Boot 4 this requires the **`spring-boot-starter-flyway`** starter (classpath presence of `flyway-core` alone no longer triggers auto-configuration), plus `flyway-database-postgresql` for the Postgres dialect — no explicit bean definition required.

### Auto-configuration

Spring Boot's `FlywayAutoConfiguration` activates when the `spring-boot-starter-flyway` starter is present (Spring Boot 4 requires the starter, not just `flyway-core` on the classpath), a `DataSource` bean is available, and `spring.flyway.enabled` is `true` (default). At startup, Spring calls `Flyway.migrate()` before application logic runs. Set `spring.jpa.hibernate.ddl-auto=validate` so Hibernate confirms the live schema matches the entity model — not `create` or `create-drop`, which bypasses Flyway.

For Postgres specifically, add the dialect artifact:

```kotlin
// build.gradle.kts — Boot 4 needs the starter; both BOM-managed (no version)
implementation("org.springframework.boot:spring-boot-starter-flyway")
implementation("org.flywaydb:flyway-database-postgresql")
```

### Script naming: V, R, U

Flyway recognises three prefixes out of the box:

| Prefix | Meaning | When it runs |
|--------|---------|-------------|
| `V<version>__<description>.sql` | **Versioned** — applied exactly once, in version order | Every new deployment if not yet applied |
| `R__<description>.sql` | **Repeatable** — re-applied whenever the checksum changes | Whenever the file content changes |
| `U<version>__<description>.sql` | **Undo** — reverses a versioned migration (Teams/Enterprise edition only) | Manually triggered, emergency use |

The double underscore (`__`) between version and description is mandatory. The description uses underscores or hyphens; Flyway converts them to spaces in the history table.

Version numbers can be integers (`V1`, `V2`) or dot-separated (`V1.1`, `V2.3.1`). webstack uses **integer versions only** for simplicity.

Default script location (classpath): `db/migration/`.

### Flyway schema history

Flyway writes `flyway_schema_history` on first run. Every applied migration gets a row: version, description, checksum, execution time, success flag. Never modify this table manually.

## Why expand-contract

A rolling deployment runs version N and N+1 simultaneously against the same database. If a migration drops a column, renames a table, or adds `NOT NULL` to a populated column, every in-flight request from the old binary fails the moment it runs.

**Expand-contract** (parallel-change) splits any breaking change into backward-compatible steps: the schema is always a superset of what both N and N+1 need. N ignores new columns; N+1 writes to both old and new until N is fully retired.

## webstack convention

### Naming

```text
src/main/resources/db/migration/
├── V1__init.sql
├── V2__billing_invoice_table.sql
├── V3__billing_invoice_add_tax_amount.sql   ← expand step
├── V4__billing_invoice_backfill_tax.sql     ← backfill step
└── V5__billing_invoice_enforce_not_null.sql ← contract step
```

Naming rules:

- **Integer version**, no gaps.
- **Module prefix**: `billing_invoice`, `order_orderline`, `identity_user` — ownership is visible in the history table; collisions across bounded contexts are prevented.
- **Lowercase, underscores** in the description.
- **One concern per file** — create-table and add-index are separate migrations. Atomic, reviewable, revertible.

### Supabase Postgres context

- **No superuser**: `CREATE EXTENSION` requires the `supabase_admin` role — provision extensions via the Supabase dashboard, not in Flyway scripts.
- **`public` schema**: Flyway defaults to `public`. Do not change `spring.flyway.schemas` — altering the schema search path breaks Supabase's PostgREST layer.
- **RLS policies**: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and `CREATE POLICY ...` are DDL; they belong in Flyway migrations alongside the `CREATE TABLE`.
- **Free-tier connection limits**: CI test suites should use ephemeral Testcontainers instances (not the shared Supabase instance). Set `maximum-pool-size=5` in local/dev profiles.

### application.yml configuration

```yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
    out-of-order: false
    baseline-on-migrate: false   # only true for brownfield DBs — never touch in greenfield
    clean-disabled: true         # CRITICAL: prevents flyway:clean from wiping prod
    table: flyway_schema_history
    schemas: public
  jpa:
    hibernate:
      ddl-auto: validate         # let Flyway own DDL; Hibernate only validates
```

`clean-disabled: true` is non-negotiable for production profiles. Flyway clean drops every object in the schema; leaving it enabled is a footgun.

## Expand-contract walk

Three-step checklist for any breaking change. Example: adding a `NOT NULL` column `tax_amount_cents` to `billing_invoice`.

### Step 1 — Expand: add column nullable

Deploy this migration while version N is running. The nullable column is invisible to N — no INSERT from N breaks.

```sql
-- V3__billing_invoice_add_tax_amount.sql
ALTER TABLE billing_invoice
    ADD COLUMN tax_amount_cents BIGINT;
```

Deploy version N+1 alongside version N. Version N+1 **reads and writes** `tax_amount_cents`; version N ignores the new column.

Version N+1's JPA entity adds:

```kotlin
// in: <module>/infrastructure/persistence/<aggregate>/<Aggregate>JpaEntity.kt — JPA mapping, NOT a domain entity
@Column(name = "tax_amount_cents")
var taxAmountCents: Long? = null,
```

### Step 2 — Backfill + dual-write

Before enforcing `NOT NULL`, every existing row must have a value. Backfill is a separate migration (see [Backfill patterns](#backfill-patterns) for large tables):

```sql
-- V4__billing_invoice_backfill_tax.sql
-- Idempotent: only fills rows not yet set.
UPDATE billing_invoice
SET    tax_amount_cents = 0
WHERE  tax_amount_cents IS NULL;
```

For non-trivial derived values, a Kotlin `JavaMigration` class is more readable than inline SQL arithmetic. Once V4 is applied and version N is fully retired, every row has a value — historical rows from backfill, new rows from dual-write.

### Step 3 — Contract: enforce constraint + optional cleanup

Once N is fully retired and every row has a value:

```sql
-- V5__billing_invoice_enforce_not_null.sql
ALTER TABLE billing_invoice
    ALTER COLUMN tax_amount_cents SET NOT NULL;
```

Update the Kotlin entity to reflect the enforced nullability:

```kotlin
// in: <module>/infrastructure/persistence/<aggregate>/<Aggregate>JpaEntity.kt — JPA mapping, NOT a domain entity
@Column(name = "tax_amount_cents", nullable = false)
var taxAmountCents: Long = 0,
```

If the change was a rename (not add), the contract step drops the old column after version N is fully retired:

```sql
-- contract step for a rename: old_column → new_column
ALTER TABLE billing_invoice DROP COLUMN old_column_name;
```

**Never combine expand and contract in a single migration.** Each step must be deployable independently so a rollback of N+1 leaves the schema in a state that N can still use.

## Backfill patterns

Backfilling large tables (millions of rows) inside a single migration transaction holds a lock for the duration of the UPDATE, blocking concurrent reads and writes. Use chunked backfill instead.

### Batch UPDATE with checkpoint

Process large tables in small chunks to avoid long-held locks:

```sql
-- V4__billing_invoice_backfill_tax.sql
DO $$
DECLARE
    batch_size   INT := 5000;
    rows_updated INT;
BEGIN
    LOOP
        UPDATE billing_invoice
        SET    tax_amount_cents = 0
        WHERE  id IN (
            SELECT id FROM billing_invoice
            WHERE  tax_amount_cents IS NULL
            LIMIT  batch_size
        );
        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        EXIT WHEN rows_updated = 0;
        PERFORM pg_sleep(0.05);
    END LOOP;
END $$;
```

Each iteration commits a short transaction, releasing row locks between batches. `pg_sleep(0.05)` yields to concurrent writers — adjust or remove during planned maintenance windows.

### Idempotent backfill

Always write backfill as `WHERE column IS NULL` (or equivalent condition). If the migration is interrupted and re-run after a `flyway repair`, it picks up from where it left off rather than double-processing rows.

For insert-based backfill (copying data into a new table):

```sql
-- Idempotent insert: skip rows already present
INSERT INTO billing_invoice_tax (invoice_id, tax_amount_cents)
SELECT id, 0
FROM   billing_invoice
WHERE  tax_amount_cents IS NULL
ON CONFLICT (invoice_id) DO NOTHING;
```

`ON CONFLICT DO NOTHING` makes the migration re-runnable if it was partially applied.

### Transaction splitting for very large tables

For tens of millions of rows, options:

1. **`spring.flyway.mixed=true`** — allows mixing DDL and DML statements in the same migration script. Use carefully; partial failure leaves an intermediate state.
2. **Kotlin `JavaMigration`** with `isTransactional() = false` — full control over commit cadence.
3. **Separate offline script** — run the backfill manually before the enforcement migration, then the V script asserts `WHERE column IS NULL; -- should be zero rows`.

## Testcontainers PR dry-run

Every pull request that touches `db/migration/` should validate that migrations apply cleanly against a real Postgres 16 instance. Use the `@SpringBootTest` + `@ServiceConnection` pattern from `jpa-patterns.md`, extended with a production schema dump for brownfield projects.

### Basic PR migration test

```kotlin
// src/test/kotlin/com/example/app/MigrationIntegrityTest.kt
@Testcontainers
@SpringBootTest
class MigrationIntegrityTest {

    @Test
    fun `all migrations apply cleanly`() {
        // Context startup runs Flyway migrate() automatically.
        // A green test proves clean application — no explicit assertions needed.
    }

    companion object {
        @Container
        @ServiceConnection
        @JvmStatic
        val postgres = PostgreSQLContainer<Nothing>("postgres:16-alpine")
    }
}
```

`@ServiceConnection` (introduced in Spring Boot 3.1, standard in 4.0) wires the container's JDBC URL into the Spring context. A migration syntax error or constraint violation fails the context load, which fails the test.

### Production schema dump (brownfield adoption)

For projects adopting Flyway on an existing database: `pg_dump --schema-only -d <db> -f baseline.sql`, place it as `V1__baseline.sql`, keep `baseline-on-migrate=false`. The Testcontainers test then validates the full migration history from an empty container.

### CI configuration

Run on every PR that touches `src/main/resources/db/migration/**`:

```yaml
- name: Run migration integrity test
  run: ./gradlew test --tests "*.MigrationIntegrityTest"
```

Pin the Postgres image to match Supabase: `postgres:16-alpine`. Dependencies (versions from `spring-boot-dependencies` BOM):

```kotlin
testImplementation("org.testcontainers:postgresql")
testImplementation("org.testcontainers:junit-jupiter")
```

## Rollback policy

webstack follows a **forward-only** policy: committed migrations are never edited or deleted. Mistakes are fixed by a new `V(N+1)` migration.

### Why forward-only

1. Flyway validates checksums on startup: editing an applied migration raises `FlywayValidateException`.
2. Rolling back a column drop means recreating it — data written by N+1 is already gone.
3. Expand-contract keeps each step low-risk; a mistake in step N is isolated and corrected in step N+1.

### Undo scripts (`U` prefix)

Flyway `U` scripts require a paid Teams/Enterprise license. Do not rely on them for routine deployments. If the project has the license, scope undo scripts to non-destructive operations only (e.g., dropping an index). Never write an undo that drops a column — data is destroyed.

### Post-incident forward fix

1. Assess impact. If data is corrupted, restore from backup before proceeding.
2. Write `V(N+1)__fix_<description>.sql` to correct the schema.
3. Run the fix with a maintenance window if needed.
4. Add a `MigrationIntegrityTest` assertion covering the corrected state.

### When `flyway repair` is appropriate

`flyway repair` removes `FAILED` rows from `flyway_schema_history` and realigns checksums. Use it **only** when a migration failed due to a transient infrastructure error (connection drop, OOM) and the DDL was not partially applied. Postgres wraps DDL in transactions, so most failures are atomic. Do not use repair to re-run a migration with a modified checksum — fix forward instead.

## Actuator integration

Spring Boot Actuator exposes migration status at `/actuator/flyway`. Enable it:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,flyway
  endpoint:
    flyway:
      enabled: true
```

Restrict this endpoint to internal/ops networks. The response lists all migrations with `version`, `script`, `state`, `installedOn`, and `executionTime`. States to watch: `SUCCESS`, `FAILED`, `PENDING`, `MISSING_SUCCESS` (script deleted after apply).

### Grafana dashboard (B3 observability pairing)

The B3 stack scrapes Actuator metrics via Micrometer/Prometheus. Recommended alerts (VERIFY the `flyway_migrations_total` / `flyway_migration_seconds` meter names and tags exist in your Boot 4 + Micrometer version at implementation time — Flyway Actuator metric exposure has shifted across versions; otherwise alert on the `/actuator/flyway` endpoint state):

- `flyway_migrations_total{state="pending"} > 0` — the app instance failed to migrate before receiving traffic.
- `flyway_migrations_total{state="failed"} > 0` — partial migration in error state.
- `flyway_migration_seconds > 30` — candidate for batch backfill refactor.

## Anti-patterns

### 1. `flyway repair` in production pipelines

`repair` is a recovery tool, not a deployment step. A checksum mismatch in CI means someone edited a committed migration — fix the process, not the history.

### 2. Forcing `baseline-on-migrate=true` on an existing DB

This skips all migrations up to the baseline version and silently leaves pending migrations unapplied. Use `baseline-on-migrate` only on the first adoption of Flyway onto a pre-existing schema. Keep it `false` thereafter.

### 3. Lock-causing `ALTER TABLE` on large tables

Postgres takes an `ACCESS EXCLUSIVE` lock for most `ALTER TABLE` operations. For type changes on large tables, expand-contract: new column → backfill → swap → drop. For adding `NOT NULL`, use the three-phase approach (Postgres 12+):

```sql
-- Phase 1: add constraint without table scan
ALTER TABLE billing_invoice
    ADD CONSTRAINT billing_invoice_status_not_null
    CHECK (status IS NOT NULL) NOT VALID;

-- Phase 2: validate in background (share-lock only)
ALTER TABLE billing_invoice
    VALIDATE CONSTRAINT billing_invoice_status_not_null;

-- Phase 3: near-instant — constraint already proven
ALTER TABLE billing_invoice
    ALTER COLUMN status SET NOT NULL;
```

### 4. Immediate `ALTER COLUMN ... NOT NULL` without backfill

Adding `NOT NULL` before every row has a value triggers a full table scan and lock. On Supabase free tier this can trip connection timeouts, leaving a `FAILED` row in `flyway_schema_history`. Always follow the expand-contract checklist: add nullable → backfill → enforce.

### 5. `clean-disabled=false` anywhere near production

`flyway clean` drops every object in the schema. Enable it only in `application-local.yml`. The production and staging profiles must always have `clean-disabled=true`.

## Sources

- **Flyway official docs:** https://documentation.red-gate.com/flyway/ — _authoritative_
- **Spring Boot — how-to database initialisation:** https://docs.spring.io/spring-boot/how-to/data-initialization.html — _authoritative_
- **Testcontainers guide — working with jOOQ, Flyway, and Testcontainers:** https://testcontainers.com/guides/working-with-jooq-flyway-using-testcontainers/ — _community: Testcontainers team_
- **Flyway Context7 llms.txt:** https://context7.com/flyway/flyway/llms.txt — _authoritative_
- **Postgres 16 docs — `ALTER TABLE`:** https://www.postgresql.org/docs/16/sql-altertable.html — _authoritative_
- **Brandur Leach, "A Missing Link in Postgres 11: Fast Column Creation with Defaults":** https://brandur.org/postgres-default — _community: Brandur Leach_

Last verified: 2026-06-22 (Flyway 11.X / Spring Boot 4.0.X / Postgres 16.X).
