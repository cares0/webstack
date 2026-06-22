# Supabase Setup

> Reference for the infra skill, build-be SubAgent, and tofu-plan-analyzer. Covers Supabase project provisioning, connection strings, schema management with Flyway, and the `supabase/supabase` IaC provider. **webstack uses Supabase strictly as a managed Postgres host** — Auth, Storage, Realtime, Edge Functions are not used.

## Why Supabase (managed Postgres)

webstack's Supabase dependency is **Postgres only**. Supabase happens to bundle Auth, Storage, Realtime, and Edge Functions on top of a Postgres instance, but webstack does not adopt those layers — the backend (Spring on Oracle Cloud) connects to Postgres over JDBC and treats the database as a plain relational store. Authorization lives in Spring; file uploads (if needed) belong to a future feature decision; realtime updates use whatever channel the feature picks.

The choice of Supabase as the Postgres host is driven by:

- **Free tier**: 500 MB database, no card surprises. Sufficient for development, MVP, and early production traffic. (Note: the Free tier has **no managed/automatic backups** — see [Free tier limits](#free-tier-limits); webstack's own daily `pg_dump` cron is the only backup mechanism, documented in `docs/infrastructure/backup-and-recovery.md`.)
- **Operational simplicity**: zero-ops Postgres with a UI for SQL inspection, no `pg_upgrade` to run.
- **Standard Postgres**: extensions (pgvector, pg_cron, postgis) available; everything that works in Postgres 15+ works here. No proprietary lock-in at the SQL level — the data and migrations are portable.

The Supabase-specific layer used by webstack is small: project provisioning via the IaC provider and the connection strings exposed by the dashboard. Backups are not a managed Supabase feature on Free — webstack supplies its own daily `pg_dump` cron (see `docs/infrastructure/backup-and-recovery.md`). Everything else is plain Postgres.

## Free tier limits

The free tier as of 2026:

- **2 free projects** per organization. Additional projects require Pro ($25/mo/project).
- **500 MB database** per project (Postgres data, indexes, WAL — usable space is closer to 300 MB once indexes and WAL are accounted for).
- **5 GB egress per month**.
- **Project pauses after 7 consecutive days of inactivity.** Auto-resumes on next request (cold-start latency ~30 seconds).
- **No managed/automatic backups.** Managed daily backups and point-in-time recovery are **Pro+ only**. On Free, the only backup mechanism is webstack's own daily `pg_dump` cron → OCI Object Storage (see `docs/infrastructure/backup-and-recovery.md`).

Verify current tier numbers at https://supabase.com/pricing — limits change quarterly.

> **Pause behavior gotcha:**
>
> A free Supabase project that receives no requests for 7 days is **paused**. The next request after pause triggers a resume that takes **~30 seconds** before the API returns. For a staging environment that's hit regularly this is invisible; for a public landing page with sporadic traffic, the first user of the day waits half a minute. Two mitigations:
>
> 1. **Health-check cron** from any always-on host every 6 hours — a periodic JDBC `SELECT 1` (or a Spring `/actuator/health` ping that touches the DB) keeps the project active.
> 2. **Upgrade to Pro** ($25/month) — Pro projects never pause and gain point-in-time recovery, an extra 5 GB egress, and more compute headroom.
>
> webstack's free-tier flow assumes you accept the pause behavior in dev/staging and upgrade for prod once user traffic justifies it.

A second free-tier gotcha worth tracking:

> **DB size gotcha:**
>
> The 500 MB cap counts indexes, WAL, and bloat in addition to row data. A project with ~10 average tables typically reaches the cap at 100k–250k rows of business data. Monitor on Supabase Console → Project Settings → Usage. Plan for migration to Pro when usage crosses 350 MB.

## Sign-up & project

1. Visit https://supabase.com → **Start your project**.
2. Sign in with GitHub (recommended for the Vercel parity).
3. Create an **organization** (free, holds the 2-project allowance).
4. **New project** form:
   - **Name**: `<project>-<env>` (e.g., `webstack-myapp-prod`).
   - **Database password**: strong, save in a password manager. Used for direct Postgres logins.
   - **Region**: closest to backend hosting. For an Oracle Cloud `ap-seoul-1` backend, choose `ap-northeast-2` (Seoul). For US backends, `us-east-1` or `us-west-1`.
   - **Pricing plan**: Free.
5. Provisioning takes 1-3 minutes.

webstack creates one Supabase project per environment (dev/staging/prod). Free tier's 2-project limit forces the choice; typically dev shares with staging on the free tier and prod is paid.

## Connection strings

The **Database** settings page exposes multiple connection strings:

- **Direct connection** (port 5432) — full Postgres protocol. Use for migrations, DDL, admin tools (psql, DataGrip).
- **Pooled connection** (port 6543, PgBouncer transaction mode) — recommended for application traffic, especially with serverless / many short connections. **Use this for the Spring Boot app.**
- **Pooled connection** (port 6543, PgBouncer session mode) — when you need session-level features (prepared statements, advisory locks).

**Copy these strings verbatim from the dashboard (Settings → Database) — do not construct the host yourself.** The pooler hostname has a dynamic prefix (e.g., `aws-0-`, `aws-1-`, … varies by project/region/provider) and must not be string-built. The shape is roughly:

```text
postgresql://postgres.<project_ref>:<password>@<pooler-host-from-dashboard>:6543/postgres
```

where `<pooler-host-from-dashboard>` is the exact `…​.pooler.supabase.com` host shown for your project. The direct connection (port 5432) is likewise copied from the dashboard.

In webstack:

- **Spring** uses the **transaction-mode pooled URL** (`?pgbouncer=true&prepareThreshold=0` if Spring's `prepareThreshold` causes prepared-statement issues with PgBouncer).
- **Flyway migrations** run via the **direct connection** because they need DDL — PgBouncer's transaction-mode pool would break multi-statement migrations.

Set both as separate env vars: `DATABASE_URL` (pooled) and `DATABASE_DIRECT_URL` (direct). Spring app reads `DATABASE_URL`; the Flyway CLI / Gradle task reads `DATABASE_DIRECT_URL`.

These two connection strings + the database password are the **only** things webstack needs from Supabase at runtime. There are no anon keys, no service-role keys, no JWT secrets — those belong to the Auth/PostgREST layer that webstack does not use.

## Schema management

**Spring Flyway** is the sole schema source of truth. `src/main/resources/db/migration/V*.sql` files run on app start in dev or via CI in prod. The Spring app owns DDL; Supabase's SQL editor is read-only for schema in production.

```text
src/main/resources/db/migration/
├── V1__init.sql
├── V2__add_invoice_table.sql
└── V3__add_finalized_at.sql
```

webstack does **not** use the Supabase migration CLI (`supabase migration new`, `supabase db push`). One schema source — Flyway — is enough. Direct edits in the Supabase SQL editor should be reserved for ad-hoc inspection; any schema change written there must be exported as a Flyway migration before merging.

For integration testing, Flyway runs against a Testcontainers `PostgreSQLContainer` — see `docs/backend/jpa-patterns.md` "Verifying migrations with TestContainers".

## supabase/supabase provider

A community provider (`supabase/supabase`) covers project provisioning. As of 2026 it is younger than `vercel/vercel` or `oracle/oci` — coverage is project-level. The HCL is identical for OpenTofu and Terraform; the `terraform { ... }` block name is preserved by OpenTofu for portability.

```hcl
terraform {
  required_providers {
    supabase = {
      source  = "supabase/supabase"
      version = "~> 1.0"
    }
  }
}

provider "supabase" {
  access_token = var.supabase_access_token
}

resource "supabase_project" "main" {
  organization_id   = var.supabase_organization_id
  name              = "webstack-myapp"
  database_password = var.supabase_db_password
  region            = "ap-northeast-2" # (verify the accepted region enum value against the supabase/supabase provider — accepted values are provider-defined and have changed)
}

resource "supabase_branch" "preview" {
  parent_project_ref = supabase_project.main.id
  branch_name        = "preview"
  region             = "ap-northeast-2"
}
```

> **(verify against the provider):** confirm the `region` enum accepts the value you set, and that the `supabase_branch` resource name/arguments still match the current `supabase/supabase` provider schema — both are younger surfaces that have shifted between releases.

**Branches** (Pro feature) provision separate Postgres instances for preview deployments. Free tier projects use a single branch.

The IaC provider does **not** manage schema. Schema goes via Flyway only.

## webstack convention

- **Provider config:** `infrastructure/main.tf` pins `supabase/supabase ~> 1.0`. Auth via `var.supabase_access_token` (sensitive).
- **Project resource:** `infrastructure/supabase.tf` creates one `supabase_project` per environment. Outputs:
  - `database_url` (the pooled Postgres URL, sensitive).
  - `database_direct_url` (the direct Postgres URL for Flyway, sensitive).
- **Schema source of truth:** Spring Flyway under `src/main/resources/db/migration/`. No `supabase/migrations/` folder.
- **Backend ↔ Postgres:** Postgres direct credentials only. The backend reads `DATABASE_URL` (pooled) for app traffic and `DATABASE_DIRECT_URL` (direct) for Flyway.
- **Frontend ↔ Postgres:** none. The frontend never talks to Postgres directly. All data flows `FE → Spring → Postgres`.
- **No Auth, Storage, Realtime, Edge Functions.** Authorization is implemented in Spring (see the `auth` recipe at `docs/recipes/spring-security-auth.md` if the project enabled the auth option during init). File uploads, realtime, and edge functions are out of scope; if a feature needs them, the user picks a provider per feature.
- **Free tier monitoring:** infra skill flags when project count exceeds 2 free projects per org.

## Sources

- Supabase docs: https://supabase.com/docs
- Supabase pricing & limits: https://supabase.com/pricing
- supabase/supabase provider (OpenTofu Registry): https://search.opentofu.org/provider/supabase/supabase/latest
- Connection pooling: https://supabase.com/docs/guides/database/connecting-to-postgres

Last verified: 2026-06-22 (Supabase Free 2026 policy — no managed backups; pooler host read from dashboard).
