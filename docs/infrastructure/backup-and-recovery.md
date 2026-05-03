# Backup and recovery

> Reference for /webstack:infra and /webstack:deploy slash commands and security-auditor SubAgent.
> Describes the three-layer backup strategy (DB / IaC state / app artifact) and step-by-step recovery runbooks for the webstack free-tier stack (Supabase + OCI + Vercel).

---

## What is webstack backup

webstack runs three independently deployable systems. Each carries its own failure mode and its own backup layer:

| Layer | What can be lost | Backup mechanism |
|---|---|---|
| **Layer 1 — Database** | Supabase Postgres data, schema | `supabase db dump` via GitHub Actions cron → OCI Object Storage |
| **Layer 2 — IaC state** | OpenTofu state file (infrastructure topology) | S3 backend on OCI Object Storage with versioning + native locking |
| **Layer 3 — App artifact** | Runnable JAR | GitHub Releases + last-N copies on OCI VM `/opt/app/releases/` |

The three layers are independent — a lost database does not affect the IaC state, and vice versa. Recovery procedures are therefore also independent. See [Recovery runbooks](#recovery-runbooks) for step-by-step checklists.

Vercel (frontend) is excluded from backup: Vercel keeps full deployment history internally and can roll back to any prior build via the dashboard or CLI. The source of truth for frontend code is the git repository.

---

## Why this approach (free tier reality)

Supabase Free does **not** include automatic backups, PITR, or a backup API. The only mechanism is `supabase db dump` via CLI against the live DB URL. Projects **pause after 7 days of inactivity** — an active backup cron prevents this. Dumps do **not** include Supabase Storage API objects; back those up separately if they contain user data.

webstack's backend is a single Ampere A1 VM (Always Free) with no standby. VM termination requires re-running `/webstack:infra` + `/webstack:deploy`. Keeping last-N JARs on-disk provides an offline artifact when GitHub is unreachable.

### RTO / RPO

| Layer | RPO | RTO |
|---|---|---|
| Database (daily dump) | Up to 24 h | 15–30 min |
| Database (weekly fallback) | Up to 7 days | 15–30 min |
| IaC state | Zero (versioned) | 5–10 min |
| App artifact (on-VM) | Zero | 2–5 min |
| App artifact (GitHub Release) | Matches last release | 5–15 min |

For database RPO under 1 hour, see [Pro upgrade trigger](#pro-upgrade-trigger).

---

## Layer 1 — Database (Supabase)

A GitHub Actions `schedule` workflow runs `supabase db dump --db-url` daily at 03:00 UTC, gzip-compresses the output, and uploads it to OCI Object Storage. Daily dumps are kept for 7 days; Sunday dumps go to a `weekly/` prefix and are kept for 4 weeks. OCI Object Storage encrypts at rest by default — no extra key management required.

### GitHub Actions workflow

```yaml
# *-infrastructure/.github/workflows/db-backup.yml
name: DB Backup
on:
  schedule:
    - cron: '0 3 * * *'   # 03:00 UTC daily
  workflow_dispatch:
permissions:
  contents: read
jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      - name: Install Supabase CLI
        run: |
          curl -fsSL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz \
            | tar -xz -C /usr/local/bin supabase

      - name: Dump and upload
        env:
          AWS_ACCESS_KEY_ID:     ${{ secrets.OCI_S3_ACCESS_KEY }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.OCI_S3_SECRET_KEY }}
          AWS_DEFAULT_REGION:    ${{ secrets.OCI_REGION }}
        run: |
          TS=$(date -u +%Y%m%dT%H%M%SZ)
          FILE="backup-${TS}.sql"
          supabase db dump --db-url "${{ secrets.SUPABASE_DB_URL }}" --file "$FILE"
          gzip "$FILE"
          # Sunday (DOW=7) goes to weekly/, all others to daily/
          DOW=$(date -u +%u)
          PREFIX=$( [ "$DOW" = "7" ] && echo weekly || echo daily )
          ENDPOINT="https://${{ secrets.OCI_NAMESPACE }}.compat.objectstorage.${{ secrets.OCI_REGION }}.oci.customer-oci.com"
          aws s3 cp "${FILE}.gz" "s3://${{ secrets.OCI_BACKUP_BUCKET }}/${PREFIX}/${FILE}.gz" \
            --endpoint-url "$ENDPOINT" --no-progress
          # Prune daily: keep newest 7
          aws s3 ls "s3://${{ secrets.OCI_BACKUP_BUCKET }}/daily/" --endpoint-url "$ENDPOINT" \
            | sort | head -n -7 | awk '{print $4}' \
            | xargs -I{} aws s3 rm "s3://${{ secrets.OCI_BACKUP_BUCKET }}/daily/{}" \
                --endpoint-url "$ENDPOINT" || true
          # Prune weekly on Sundays: keep newest 4
          if [ "$DOW" = "7" ]; then
            aws s3 ls "s3://${{ secrets.OCI_BACKUP_BUCKET }}/weekly/" --endpoint-url "$ENDPOINT" \
              | sort | head -n -4 | awk '{print $4}' \
              | xargs -I{} aws s3 rm "s3://${{ secrets.OCI_BACKUP_BUCKET }}/weekly/{}" \
                  --endpoint-url "$ENDPOINT" || true
          fi
```

### Setup

Create the OCI bucket (run once):

```bash
oci os bucket create --compartment-id <compartment-ocid> \
  --name webstack-db-backups --versioning Enabled --region ap-seoul-1
```

Add these GitHub Secrets: `SUPABASE_DB_URL` (direct DB URL, not pooler), `OCI_S3_ACCESS_KEY`, `OCI_S3_SECRET_KEY` (OCI Customer Secret Key pair — see OCI Console → User → Customer Secret Keys), `OCI_NAMESPACE` (tenancy namespace), `OCI_REGION`, `OCI_BACKUP_BUCKET`.

The default dump captures schema + data — always use this for disaster recovery. `--data-only` omits schema; use only for seeding. The output is a standard `pg_dump` logical dump restorable with `psql`.

---

## Layer 2 — IaC state (OpenTofu)

### S3 backend on OCI Object Storage

OpenTofu state is stored in OCI Object Storage via the S3-compatible API. The backend configuration lives in `*-infrastructure/backend.tf`:

```hcl
terraform {
  backend "s3" {
    bucket = "webstack-tofu-state"
    key    = "prod/terraform.tfstate"
    region = "ap-seoul-1"   # or us-east-1 if your S3 client doesn't resolve OCI region names

    endpoints = {
      s3 = "https://<namespace>.compat.objectstorage.ap-seoul-1.oci.customer-oci.com"
    }

    # Native S3 conditional-write locking (OpenTofu 1.10+) — no DynamoDB required
    use_lockfile = true

    # OCI Object Storage always encrypts at rest; skip AWS-specific checksum
    skip_s3_checksum            = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true

    access_key = "<oci-s3-access-key>"
    secret_key = "<oci-s3-secret-key>"
  }
}
```

Replace `<namespace>` with your OCI tenancy namespace. `access_key` / `secret_key` are an OCI Customer Secret Key pair, not AWS credentials.

`use_lockfile = true` enables native conditional-write locking via `If-None-Match` — OpenTofu writes `.tflock` with a conditional PUT, replacing the legacy DynamoDB requirement. Verify it works: `tofu init && tofu plan` should create a `.tflock` object in the bucket.

Enable versioning on the state bucket so every `tofu apply` leaves a recoverable prior version:

```bash
oci os bucket update --bucket-name webstack-tofu-state --versioning Enabled
```

Prune versions older than 90 days via OCI Console → bucket → Version History to stay within the 20 GB Always Free quota. For full restore steps see [Runbook 2](#runbook-2--iac-state-rollback).

---

## Layer 3 — Application (jar)

### GitHub Releases

Every `/webstack:deploy` publishes the Spring Boot JAR as a GitHub Release asset under a `vYYYY-MM-DD-HHMMSS` tag, providing an auditable artifact history independent of the VM:

```yaml
- name: Create GitHub Release
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    TAG="v$(date -u +%Y-%m-%d-%H%M%S)"
    gh release create "$TAG" build/libs/app.jar --title "Backend $TAG" \
      --notes "Deployed from ${{ github.sha }}"
```

### On-VM artifact store

The OCI VM keeps the last 5 JARs in `/opt/app/releases/`. The active JAR is referenced via a `current` symlink. The deploy workflow manages this:

```bash
ARTIFACT="app-$(date -u +%Y%m%d-%H%M%S).jar"
scp build/libs/app.jar opc@"$OCI_VM_IP":/opt/app/releases/"$ARTIFACT"
ssh opc@"$OCI_VM_IP" "ln -sfn /opt/app/releases/$ARTIFACT /opt/app/current"
ssh opc@"$OCI_VM_IP" "ls -t /opt/app/releases/app-*.jar | tail -n +6 | xargs -r rm --"
```

The systemd unit reads `current` at start:

```ini
[Service]
ExecStart=/usr/bin/java -jar /opt/app/current
Restart=on-failure
RestartSec=5s
```

`RestartSec=5s` recovers from transient OOM/exception. A rollback is `ln -sfn <old-jar> /opt/app/current && systemctl restart app`.

---

## Supabase MCP integration

### Setup

Add to `.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "supabase": {
      "type": "http",
      "url": "https://mcp.supabase.com/mcp?project_ref=<your-project-ref>&read_only=true"
    }
  }
}
```

Replace `<your-project-ref>` with your Supabase project reference ID (found in **Project Settings → General**).

Authentication is handled via OAuth 2.1 — the MCP client will prompt for login on first use. No static `SUPABASE_ACCESS_TOKEN` env var is required for the HTTP transport.

**Permission scope:** `read_only=true` is recommended for backup workflows. This prevents any accidental writes to the Supabase project during monitoring tasks. Never point this at a production project from a shared or untrusted Claude session.

### What the agent can do

The Supabase MCP server gives the security-auditor SubAgent access to Supabase project metadata without exposing raw connection strings in prompts. Relevant capabilities:

- **Backup age check**: list the 10 most recent objects under `daily/` in the OCI backup bucket; parse the timestamp from `backup-YYYYMMDDTHHMMSSZ.sql.gz`; alert if older than 26 hours (missed daily run).
- **Manual trigger**: invoke `workflow_dispatch` on `db-backup.yml` via the GitHub CLI if the backup is stale.
- **Pause detection**: surface a warning in the `/webstack:deploy` pre-flight check if the Supabase project is paused.

The backup age check runs during `/webstack:infra` as an advisory check. A stale backup emits a warning in the plan output but does not block `tofu apply`.

---

## Recovery runbooks

### Runbook 1 — Database restore

**RTO:** 15–30 minutes. **RPO:** Up to 24 hours (daily), up to 7 days (weekly fallback).

**When to use:** Accidental `DROP TABLE`, data corruption, seeding a fresh project.

1. List available backups and identify the target:

   ```bash
   ENDPOINT="https://<namespace>.compat.objectstorage.<region>.oci.customer-oci.com"
   aws s3 ls s3://<OCI_BACKUP_BUCKET>/daily/ --endpoint-url "$ENDPOINT" | sort | tail -10
   ```

2. Download and decompress:

   ```bash
   aws s3 cp "s3://<OCI_BACKUP_BUCKET>/daily/backup-<TIMESTAMP>.sql.gz" ./restore.sql.gz \
     --endpoint-url "$ENDPOINT"
   gunzip restore.sql.gz
   ```

3. Restore to the Supabase project (use the direct DB URL, not the pooler):

   ```bash
   psql "$SUPABASE_DB_URL" < restore.sql
   ```

   For a new project: create it in the dashboard, substitute the new DB URL, then update `SUPABASE_DB_URL` in GitHub Secrets and re-run `/webstack:infra`.

4. Validate row counts on critical tables and run the application smoke test (health endpoint + one authenticated API call).
5. Record the restore in your incident log: timestamp, dump file used, row counts verified.

### Runbook 2 — IaC state rollback

**RTO:** 5–10 minutes. **RPO:** Zero (every `apply` creates a new version).

**When to use:** Partial/unexpected `tofu apply`, corrupt state, or drift after manual OCI Console changes.

1. Find the prior version in OCI Console → Object Storage → `webstack-tofu-state` → object `prod/terraform.tfstate` → Version History.

2. Restore it (versioning means the overwrite itself creates a new version):

   ```bash
   oci os object copy \
     --source-bucket-name webstack-tofu-state \
     --source-object-name prod/terraform.tfstate \
     --source-version-id  <version-id> \
     --destination-bucket webstack-tofu-state \
     --destination-object prod/terraform.tfstate
   ```

3. Reinitialize and verify:

   ```bash
   cd <project>-infrastructure && tofu init
   tofu plan -refresh-only   # expect zero changes
   ```

4. If resources are missing, run `tofu apply` (plan must show creation only, no deletions).
5. Force-unlock a stale `.tflock` only when no other `apply` is running: `tofu force-unlock <lock-id>`.
6. Re-run `/webstack:deploy` after state is stable.

### Runbook 3 — Application rollback

**RTO:** 2–5 minutes (from on-VM copy), 5–15 minutes (from GitHub Release). **RPO:** Matches previous deployment.

**When to use:** New JAR is crashing (OOM, startup failure, regression).

1. SSH into the OCI VM and list available releases:

   ```bash
   ssh opc@<vm-public-ip>
   ls -lt /opt/app/releases/
   ```

2. Roll back the symlink and restart:

   ```bash
   sudo ln -sfn /opt/app/releases/app-<previous-timestamp>.jar /opt/app/current
   sudo systemctl restart app
   ```

3. Verify the service started cleanly:

   ```bash
   sudo systemctl status app
   sudo journalctl -u app -n 50 --no-pager
   curl -fsS http://localhost:8080/actuator/health
   ```

4. If all on-VM copies are broken, download from GitHub Releases:

   ```bash
   gh release download <tag> --pattern "app.jar" --dir /opt/app/releases/
   mv /opt/app/releases/app.jar /opt/app/releases/app-<tag>.jar
   sudo ln -sfn /opt/app/releases/app-<tag>.jar /opt/app/current
   sudo systemctl restart app
   ```

5. Record the bad deployment SHA and rollback target in a GitHub issue for post-mortem.

---

## Pro upgrade trigger

The free-tier backup strategy (daily dump, self-managed) is sufficient for most early-stage projects. Upgrade to Supabase Pro when any of the following apply:

| Condition | What Pro provides |
|---|---|
| RPO requirement < 1 hour | PITR with second-granularity recovery |
| Dump restoration takes > 30 min (large data volume) | Physical backup restore is faster than logical |
| Compliance requirement for automated audit trail | Dashboard backup history, downloadable for audit |
| Team size > 3 engineers sharing the same project | Per-environment branching, backup isolation |
| Revenue-generating production traffic on the DB | PITR eliminates the 24-hour data-loss window |

**Cost reference (as of 2026):** Supabase Pro is $25/month per project. PITR add-on is $100/month (7-day window) or $200/month (30-day window). Add a Small compute add-on ($10/month) as a minimum prerequisite for PITR.

When upgrading, disable the GitHub Actions backup cron (`db-backup.yml`) to avoid redundant dump storage costs. Keep the OCI bucket and its contents for 30 days as a transitional safety net.

---

## Anti-patterns

**Skipping backup validation.** An untested dump creates false confidence. Add a weekly check that downloads the latest backup, restores it to a local Postgres container, and asserts row counts on 2–3 critical tables. Emit a GitHub Actions warning annotation on failure.

**No IaC state backup.** A local state file means a lost laptop destroys all knowledge of provisioned infrastructure. Configure the S3 backend before the first `tofu apply`. If you bootstrapped with a local file, migrate immediately: `tofu init -migrate-state`.

**Keeping only one JAR copy on the VM.** `systemd` will loop-restart a crashing JAR with nothing to fall back to. A regression then requires a GitHub download during an outage window. Keep at least 3 copies; default is 5.

**Using `--data-only` for all dumps.** Data-only dumps omit schema. If schema changed between backup and restore, the restore fails on type or column mismatches. Use the default full dump for disaster recovery.

**Storing OCI Customer Secret Keys in plaintext.** Store access key and secret key as GitHub Secrets, never committed to the repo. Rotate annually or after suspected exposure.

---

## Sources

- **Supabase platform backups:** https://supabase.com/docs/guides/platform/backups — _authoritative_
- **Supabase CLI db dump reference:** https://supabase.com/docs/reference/cli/supabase-db-dump — _authoritative_
- **Supabase agent-skills (Claude Code plugin):** https://github.com/supabase/agent-skills — _community: Supabase-affiliated, MIT licensed_
- **OpenTofu S3 backend documentation:** https://opentofu.org/docs/language/settings/backends/s3/ — _authoritative_
- **OCI Object Storage S3 Compatibility API:** https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm — _authoritative_

Last verified: 2026-05-04 (Supabase Free 2026 policy / OpenTofu 1.10.X / OCI Object Storage S3-compat).
