# Supabase Setup

> Reference for the infra skill, build-be SubAgent, and terraform-plan-analyzer. Covers Supabase project provisioning, connection strings, API keys, schema management, Row Level Security (RLS), JWT integration with Spring, and `terraform-provider-supabase`.

## Why Supabase for DB + Auth

Supabase wraps Postgres with adjacent services in one provider:

- **Postgres** — full Postgres 15+ instance with extensions (pgvector, pg_cron, postgis), exposed via JDBC and via PostgREST.
- **Auth** — email/password, magic link, social OAuth (Google, GitHub, etc.), JWT issuance, all stored in the same Postgres.
- **Storage** — S3-compatible file storage with RLS-aware access control.
- **Edge Functions** — Deno runtime functions deployable per-project.
- **Realtime** — WebSocket subscriptions to row changes.

For early-stage products, owning a full Postgres without operational overhead is the main value. webstack uses Supabase for the database and Auth; the backend (on Oracle Cloud Compute) connects to Supabase Postgres over JDBC and verifies Supabase-issued JWTs.

Self-hosted Supabase is also possible but offsets the operational simplicity that motivates the choice. Stick with hosted unless data residency or air-gap requirements force the issue.

## Free tier limits

The free tier as of 2025:

- **2 free projects** per organization. Additional projects require Pro ($25/mo/project).
- **500 MB database** per project (Postgres data, indexes, WAL).
- **1 GB file storage** per project.
- **5 GB egress per month** combined across services.
- **50,000 monthly active users (MAU)** for Auth.
- **2 GB bandwidth** for Realtime.
- **Project pauses after 7 consecutive days of inactivity.** Auto-resumes on next request (cold-start latency ~30 seconds).
- **Daily backups** (point-in-time recovery is Pro-only).

Pause behavior matters for webstack: a hobby project with no traffic will pause; the next user request triggers resume but takes time. For staging environments with regular activity this is rarely an issue.

Verify current tier numbers at https://supabase.com/pricing — limits change quarterly.

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

Format:

```text
postgresql://postgres.<project_ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

In webstack:

- **Spring** uses the **transaction-mode pooled URL** (`?pgbouncer=true&prepareThreshold=0` if Spring's `prepareThreshold` causes prepared-statement issues with PgBouncer).
- **Flyway migrations** run via the **direct connection** because they need DDL — PgBouncer's transaction-mode pool would break multi-statement migrations.

Set both as separate env vars: `DATABASE_URL` (pooled) and `DATABASE_DIRECT_URL` (direct). Spring app reads `DATABASE_URL`; the Flyway CLI / Gradle task reads `DATABASE_DIRECT_URL`.

## API keys

Each Supabase project has two API keys:

- **`anon` key** — safe to ship in the client bundle. Calls go through PostgREST and **must be authorized by Row Level Security policies**. A leaked anon key is no worse than the RLS policies allow.
- **`service_role` key** — bypasses RLS entirely. Full admin access to the database. **Server-only.** Never include in any frontend bundle or commit to a repo.

Find both at **Project Settings** → **API**.

webstack convention:

- **Backend (Spring on Oracle Cloud)** uses neither anon nor service_role for normal app traffic — it uses the **direct database credentials** (the Postgres password from project provisioning). The service_role key is only for Supabase-specific admin operations (e.g., creating users via Auth admin API).
- **Frontend (Next.js)** ships `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` for the rare cases where the FE needs direct Supabase access (most webstack apps go FE → Spring → Supabase, not FE → Supabase).

## Schema in webstack

Two paths for owning the schema:

1. **Spring Flyway** (webstack default) — `src/main/resources/db/migration/V*.sql` files run on app start in dev or via CI in prod. The Spring app is the source of truth; Supabase's SQL editor is read-only for schema in prod.
2. **Supabase migrations** (`supabase/migrations/*.sql`) — managed via `supabase migration new` CLI. Useful when the FE/edge functions need their own schema changes independent of Spring.

webstack v1 picks (1) for simplicity: one schema source. If both apps own pieces of the schema, switch to (2) and remove Flyway from Spring (or scope Flyway to Spring-only tables).

Direct edits in the Supabase SQL editor should be reserved for ad-hoc inspection. Any schema change written there must be exported as a Flyway migration and deleted from the editor before merging.

## Row Level Security

RLS is Supabase's first-class authorization model. Every table accessed via the **anon** key (or any authenticated user's JWT-derived role) must have RLS policies; tables without policies are inaccessible by default once RLS is enabled. The **service_role** key bypasses all policies.

```sql
-- Enable RLS on a table
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Policy: users can read their own projects
CREATE POLICY "owner can read"
  ON projects FOR SELECT
  USING (auth.uid() = owner_id);

CREATE POLICY "owner can insert"
  ON projects FOR INSERT
  WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "owner can update"
  ON projects FOR UPDATE
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);
```

`auth.uid()` returns the user UUID embedded in the JWT. `auth.role()` returns `authenticated` or `anon`.

**Critically for webstack**: when Spring connects with the direct database password (not via Supabase's API gateway), it uses the **postgres** superuser-equivalent role and **bypasses RLS**. RLS only kicks in when calls go through PostgREST (Supabase's API layer) or via the JWT-aware Postgres roles `authenticated` and `anon`.

webstack's recommended split:

- **Backend operations** (Spring) — authorize at the application layer (Spring Security + your domain rules). RLS is not the primary defense for backend-routed traffic.
- **Frontend-direct operations** (rare) — when the FE talks to Supabase directly (e.g., realtime subscriptions, Storage uploads), RLS **is** the primary defense. Always enable RLS on tables the anon key can reach.
- **Shared tables** (auth.users, profiles) — enable RLS even if Spring is the primary writer; the policies prevent accidental anon-key reads.

## Auth integration with Spring

Supabase Auth issues JWTs signed with the project's JWT secret (HS256) or asymmetric keys (RS256, ES256 — newer projects). Spring decodes them via `spring-boot-starter-oauth2-resource-server`.

`application.yaml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://<project_ref>.supabase.co/auth/v1
          jwk-set-uri: https://<project_ref>.supabase.co/auth/v1/.well-known/jwks.json
```

For older HS256-signed projects:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri:
          # HS256 path: provide the shared secret instead
          # secret: ${SUPABASE_JWT_SECRET}
```

(Spring Security's HS256 path requires a custom `JwtDecoder` bean; RS256 with JWKS is preferred and is the default for new Supabase projects.)

The frontend calls `supabase.auth.signIn(...)` to obtain a JWT, then sends it as `Authorization: Bearer <token>` to the Spring backend. Spring extracts the user UUID from the JWT's `sub` claim and treats it as the `userId` in domain code.

## terraform-provider-supabase

A community provider (`supabase/supabase`) covers project provisioning. As of 2025 it is younger than `vercel/vercel` or `oracle/oci` — coverage is project-level, not full Postgres schema management.

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
  region            = "ap-northeast-2"
}

resource "supabase_branch" "preview" {
  parent_project_ref = supabase_project.main.id
  branch_name        = "preview"
  region             = "ap-northeast-2"
}
```

**Branches** (Pro feature) provision separate Postgres instances for preview deployments. Free tier projects use a single branch.

The Terraform provider does **not** manage schema, RLS policies, or Auth settings. Those go via Flyway (schema), SQL files (RLS — included in the same Flyway migration), and Supabase Console UI (Auth providers — one-time setup).

## supabase CLI

For local Supabase emulation and for projects choosing path (2) above:

```bash
brew install supabase/tap/supabase
supabase init                           # creates supabase/ folder
supabase start                          # launches local Supabase (Postgres + Studio + Auth)
supabase migration new add_projects     # scaffold a new migration
supabase db push                        # apply migrations to linked remote project
supabase functions deploy <name>         # deploy Edge Function
```

webstack v1 uses Spring + Flyway for schema management and skips `supabase db push`. The CLI is still useful for `supabase start` (local development against an emulated Supabase).

## webstack convention

- **Provider config:** `infrastructure/main.tf` pins `supabase/supabase ~> 1.0`. Auth via `var.supabase_access_token` (sensitive).
- **Project resource:** `infrastructure/supabase.tf` creates one `supabase_project` per environment. Outputs:
  - `supabase_url` (for `NEXT_PUBLIC_SUPABASE_URL`).
  - `supabase_anon_key` (for `NEXT_PUBLIC_SUPABASE_ANON_KEY`, sensitive).
  - `supabase_service_role_key` (for backend `SUPABASE_SERVICE_ROLE_KEY`, sensitive).
  - `database_url` (the pooled URL, sensitive).
  - `database_direct_url` (for Flyway, sensitive).
- **Schema source of truth:** Spring Flyway under `src/main/resources/db/migration/`. RLS policies are SQL files in the same folder.
- **Backend ↔ Postgres:** direct credentials (Postgres password). RLS is supplementary for tables the FE may reach.
- **Frontend ↔ Supabase:** anon key only. service_role NEVER ships to the browser.
- **JWT validation:** Spring Boot Resource Server with the project's JWKS URL.
- **Free tier monitoring:** infra skill flags when project count exceeds 2 free projects per org.

## Sources

- Supabase docs: https://supabase.com/docs
- Supabase pricing & limits: https://supabase.com/pricing
- terraform-provider-supabase: https://registry.terraform.io/providers/supabase/supabase/latest/docs
- Connection pooling: https://supabase.com/docs/guides/database/connecting-to-postgres
- Row Level Security: https://supabase.com/docs/guides/auth/row-level-security
- Supabase Auth + JWT: https://supabase.com/docs/guides/auth/jwts
- Supabase CLI: https://supabase.com/docs/guides/cli
