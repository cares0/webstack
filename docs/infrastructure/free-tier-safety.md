# Free-tier safety (OCI Budget + Vercel Hobby + Supabase pause)

> Reference for /webstack:infra slash command and tofu-plan-analyzer SubAgent.
> Stay within free-tier limits: OCI Budget alerts, Vercel Hobby usage monitoring, Supabase pause prevention, OCI A1 reclamation guards.

## What is free-tier safety

Free-tier safety is actively monitoring and defending against conditions that cause free cloud resources to be interrupted, reclaimed, or hard-stopped without advance notice. The three platforms webstack uses each carry a distinct failure mode:

- **Vercel Hobby** enforces hard monthly usage caps (100 GB bandwidth, 1M invocations, 4 CPU-hr). When any cap is reached, the deployment stops serving traffic immediately. There is **no overage option** on Hobby — the only path forward is waiting for the calendar month to roll over or upgrading to Pro.
- **OCI Always Free (Ampere A1)** is subject to **resource reclamation** if the VM is idle for 7 consecutive days. Reclamation deletes the instance and its boot volume. Recovery requires re-running `/webstack:infra` and `/webstack:deploy`.
- **Supabase Free** pauses the entire database project after 7 consecutive days of inactivity. Resume is automatic on the next incoming request but introduces a ~30-second cold-start. Every backend request to Postgres fails during resume.

None of these events are announced in advance. Without explicit safeguards — budget alerts, keepalive crons, and usage dashboards — you discover the problem from a user report, not a platform email.

---

## Why explicit safeguards

**Silent degradation.** OCI A1 reclamation and Supabase pause happen silently at the infrastructure layer. Without health-check monitoring (UptimeRobot / Grafana Synthetics), the first signal is a user report.

**No overage buffer on Hobby.** Vercel Hobby hard-stops — it does not charge for overages. A 100 GB bandwidth hit means error pages for the rest of the month with no grace period.

**Reclamation is irreversible.** OCI deletes the instance and boot volume without snapshotting. The jar + env model is recoverable via `/webstack:deploy`, but local stateful data is gone.

**The 7-day window is shorter than a sprint.** Merging Thursday, taking a long weekend, resuming Wednesday is 6 days. One distraction day triggers reclamation or pause.

Explicit safeguards — two-tier OCI budget alerts, a lightweight keepalive cron, a Supabase health-ping, and Vercel usage monitoring — eliminate all three failure modes at near-zero cost.

---

## OCI Budget alerts

OCI Budgets trigger email notifications when spending crosses configured thresholds. For an Always Free account set a **$1/month** budget — any spend above $0 means an accidental paid resource was provisioned. Use a forecast + actual two-stage alert:

| Alert | Type | Threshold | Purpose |
|---|---|---|---|
| Early warning | Forecast | 50% of $1 | Detect trend before charge materialises |
| Approaching cap | Forecast | 90% of $1 | Check resources immediately |
| Actual charge | Actual | 100% of $1 | Real spend confirmed — terminate charged resource |

### OCI Budget — OpenTofu HCL

```hcl
# infrastructure/budget.tf

resource "oci_budget_budget" "always_free_guard" {
  compartment_id = var.oci_tenancy_ocid
  amount         = 1
  reset_period   = "MONTHLY"
  display_name   = "webstack-always-free-guard"
  budget_processing_period_start_offset = 1
}

resource "oci_budget_alert_rule" "forecast_50pct" {
  budget_id      = oci_budget_budget.always_free_guard.id
  type           = "FORECAST"
  threshold      = 50
  threshold_type = "PERCENTAGE"
  display_name   = "forecast-50pct"
  message        = "WARNING: OCI forecasted spend at 50% of $1 budget. Review https://cloud.oracle.com/usage."
  recipients     = var.oci_budget_email
}

resource "oci_budget_alert_rule" "forecast_90pct" {
  budget_id      = oci_budget_budget.always_free_guard.id
  type           = "FORECAST"
  threshold      = 90
  threshold_type = "PERCENTAGE"
  display_name   = "forecast-90pct"
  message        = "URGENT: OCI forecasted spend at 90% of $1 budget. Check for accidentally provisioned paid resources."
  recipients     = var.oci_budget_email
}

resource "oci_budget_alert_rule" "actual_100pct" {
  budget_id      = oci_budget_budget.always_free_guard.id
  type           = "ACTUAL"
  threshold      = 100
  threshold_type = "PERCENTAGE"
  display_name   = "actual-100pct"
  message        = "CRITICAL: OCI actual spend reached $1. A paid resource is active — investigate immediately."
  recipients     = var.oci_budget_email
}
```

Add to `variables.tf`:

```hcl
variable "oci_budget_email" {
  description = "Email address(es) for OCI budget alerts"
  type        = list(string)
}
```

### Cost Anomaly Detection

OCI offers **Cost Anomaly Detection** (Console → Billing → Cost Analysis → Anomaly Detection). Enable it manually (no IaC support as of 2026) and configure the same notification email. It catches mid-month trends below the $1 threshold. Budget alerts evaluate every **24 hours** — acceptable for $1-scale risk.

---

## OCI Always Free reclamation prevention (Ampere A1)

OCI reclaims an Always Free Ampere A1 instance when **all three** of the following conditions are true over a **7-day sliding window**:

| Metric | Reclamation threshold |
|---|---|
| CPU utilization (95th percentile) | < 20% |
| Network utilization | < 20% |
| Memory utilization (A1 shapes only) | < 20% |

To prevent reclamation, keep **one** metric above its threshold. A self-curl to `/actuator/health/readiness` every 30 minutes (336 requests/week, 2–10 ms CPU each) is enough to exceed the 20% P95 threshold. No stress tool is needed.

### Keepalive cron — GitHub Actions

A scheduled GitHub Actions workflow running every 6 hours is simpler than a crontab on the VM — no SSH required, visible in CI history, pausable from the GitHub UI:

```yaml
# .github/workflows/keepalive.yml
name: keepalive
on:
  schedule:
    - cron: '0 */6 * * *'   # 00:00, 06:00, 12:00, 18:00 UTC
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping OCI backend
        run: |
          curl -fsS --max-time 10 --retry 3 \
            "https://${{ secrets.API_DOMAIN }}/actuator/health/readiness" \
            | grep -q '"status":"UP"'
      - name: Ping Supabase
        run: |
          curl -fsS --max-time 10 --retry 3 \
            "https://${{ secrets.SUPABASE_PROJECT_REF }}.supabase.co/rest/v1/" \
            -H "apikey: ${{ secrets.SUPABASE_ANON_KEY }}" -o /dev/null
```

Add `API_DOMAIN`, `SUPABASE_PROJECT_REF`, and `SUPABASE_ANON_KEY` as repository secrets under **Settings → Secrets and variables → Actions**.

### Keepalive cron — crontab fallback

```bash
# crontab -e on the OCI VM (ubuntu user) — every 30 minutes
*/30 * * * * curl -fsS --max-time 10 https://localhost:8080/actuator/health/readiness > /dev/null 2>&1
```

Requests to `localhost` do not leave the VM, so no egress billing applies.

To verify keepalive is working: OCI Console → **Observability → Metrics Explorer**, query `CpuUtilization` with `namespace=oci_computeagent`, `aggregation=P95`. A 7-day P95 below 20% means the keepalive is failing.

---

## Vercel Hobby usage monitoring

Vercel Hobby enforces hard monthly caps. When any cap is reached, the deployment stops serving traffic immediately — **no overage option, no grace period**.

### Hobby plan limits (verified 2026-03)

| Resource | Monthly limit | At limit |
|---|---|---|
| Fast Data Transfer (bandwidth) | 100 GB | Hard stop — all requests fail |
| Function Invocations | 1,000,000 | Hard stop — functions error |
| Active CPU | 4 CPU-hours | Hard stop — execution blocked |
| Provisioned Memory | 360 GB-hours | Hard stop — execution blocked |
| Build Execution | 6,000 minutes | Build pipeline stops |
| Image Optimization Sources | 1,000 images/month | Images stop being optimized |

A typical webstack Next.js frontend uses ~100–500 KB per page visit. At 500 KB average, the 100 GB cap supports ~200,000 monthly visits — a single viral spike can exhaust it in hours.

### Monitoring Hobby usage

Vercel does not expose Hobby usage via API. Recommended monitoring path:

1. **Vercel Dashboard → Project → Usage** — current-month bandwidth, invocations, and function CPU vs. caps.
2. **UptimeRobot** on the Vercel deployment URL — a 4xx/5xx spike indicates a limit hit.
3. **Grafana Synthetics** (100k API executions/month free) — 5-minute availability check; a failure warrants a dashboard review.
4. **Weekly review** — 2-minute Project → Usage check every Monday when visits approach 50,000.

Cross-reference: `infrastructure/observability-stack.md` §UptimeRobot and §Alerting channels.

---

## Supabase Free pause prevention

Supabase Free projects pause after **7 consecutive days of inactivity**. The first incoming request triggers auto-resume (~30 seconds) during which all Postgres operations fail — a P1 incident in production.

### Pause prevention — GitHub Actions health check cron

Ping the backend health endpoint every 6 hours. A single `/actuator/health/readiness` call (which touches Postgres) resets the 7-day inactivity clock. The combined keepalive workflow in the OCI section above already includes this step.

For a standalone Supabase ping independent of the backend:

```yaml
# .github/workflows/supabase-keepalive.yml
name: supabase-keepalive
on:
  schedule:
    - cron: '30 */6 * * *'   # offset from OCI ping
  workflow_dispatch:
jobs:
  ping-supabase:
    runs-on: ubuntu-latest
    steps:
      - name: Ping Supabase REST API
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
            "https://${{ secrets.SUPABASE_PROJECT_REF }}.supabase.co/rest/v1/" \
            -H "apikey: ${{ secrets.SUPABASE_ANON_KEY }}")
          echo "Supabase REST status: $STATUS"
          [ "$STATUS" = "200" ] || { echo "::warning::HTTP $STATUS — project may be paused"; exit 1; }
```

> **Note on the anon key:** The `anon` key here makes an authenticated REST request to PostgREST to confirm the project is active. No data is read or written. The key is safe to store as a GitHub Actions secret.

### External uptime monitor as fallback

Configure UptimeRobot to monitor the Supabase REST endpoint as a belt-and-suspenders fallback:

| Monitor | URL | Type |
|---|---|---|
| Supabase project | `https://<project-ref>.supabase.co/rest/v1/` | HTTP(S) — expect 200 |

Set a **timeout threshold of 10 seconds** — a resume-in-progress spike to 25–35 seconds fires as a timeout alert before the backend health check catches it.

---

## Threshold alarms (Grafana)

Alert at 80% of each free-tier cap — this leaves a 20% runway to optimize or upgrade before the hard stop. If Grafana Cloud is active (see `infrastructure/observability-stack.md` §Grafana Cloud Free LGTM), add these rules under **Alerting → Alert rules**:

```yaml
# Grafana Cloud metric series — 80% of 10k free limit
name: Metric series 80% of free limit
condition: avg_over_time(grafanacloud_instance_active_series[1d]) > 8000
for: 1h
labels: { severity: warning, component: observability }
annotations:
  summary: "Active series > 8,000 (80% of 10k). Check high-cardinality sources."

# Loki log ingest — 80% of 50 GB free limit
name: Loki ingest 80% of monthly free limit
condition: sum(increase(grafanacloud_logs_ingested_bytes_total[30d])) > 42949672960
for: 6h
labels: { severity: warning, component: observability }
annotations:
  summary: "Log ingest > 40 GB/month (80% of 50 GB free limit)"
```

### Vercel Hobby bandwidth alert

Vercel does not expose bandwidth metrics to Grafana. Use UptimeRobot + Vercel dashboard. If you enable Vercel's OTEL drain, export invocation counts to Grafana Cloud and alert at 800,000 invocations/month (80% of the 1M cap).

### Supabase database size alert

Export DB size from a Spring `@Scheduled` task (`SELECT pg_database_size('postgres')`) via Micrometer to Grafana Cloud:

```yaml
name: Supabase DB size 80% of free limit
condition: db_size_bytes > 419430400   # 400 MB (80% of 500 MB)
for: 30m
labels: { severity: warning, component: database }
annotations:
  summary: "Supabase DB > 400 MB — review bloat, plan Pro upgrade"
```

Cross-reference: `infrastructure/observability-stack.md` §Alerting channels for Slack/Discord routing.

---

## Pro upgrade decision matrix

The trigger column defines the _earliest_ point at which an upgrade should be planned — not the point at which service has already failed.

| Platform | Free limit | Upgrade trigger | Pro cost (2026) | Urgency |
|---|---|---|---|---|
| Vercel Hobby | 100 GB BW / 1M inv / 4 CPU-hr / month | BW > 60 GB _or_ inv > 700k _or_ any cap hit in prior month | $20/month/member | High — no overage on Hobby |
| Supabase Free | 500 MB DB / 5 GB egress / 2 projects | DB > 350 MB _or_ egress > 4 GB _or_ pause caused a prod incident | $25/month/project | Medium — pause is auto but disruptive |
| OCI Always Free | 4 OCPU + 24 GB RAM (A1) | Consistently needs > 2 OCPU or > 12 GB RAM | Pay As You Go: ~$0.01/OCPU-hr | Low — keepalive avoids reclamation |
| Grafana Cloud Free | 10k metric series / 50 GB logs+traces / 14-day retention | Series > 8k _or_ need > 14-day retention | Metered ~$8–30/month | Low — optimize cardinality first |
| Sentry Developer | 5,000 errors/month | Errors > 4k _or_ second team member | $26/month (50k errors) | Low solo; medium with team |
| UptimeRobot Free | 50 monitors, 5-min interval | SLA needs sub-5-min detection | $7/month (1-min interval) | Low dev/staging; medium prod |

When the product generates revenue: **Vercel Pro** ($20) + **Supabase Pro** ($25) + **Sentry Team + UptimeRobot Solo** (~$33) = ~$78/month. Grafana Cloud and OCI remain free until metric volume or compute sizing is the actual bottleneck.

---

## Anti-patterns

**No budget alert on OCI.** An accidental paid resource runs until the month-end billing email. The $1 budget + two-tier alert costs nothing and catches every charge.

**Relying on OCI's reclamation grace period.** OCI sends no warning before reclamation. Without a keepalive cron, any sprint break risks losing the instance and boot volume.

**No Supabase keepalive.** Auto-resume is automatic but a 30-second cold-start is a visible failure for the first user after a 7-day gap. A cron that runs for < 1 second eliminates it.

**Monitoring Hobby only after a limit is hit.** Hobby is up until the moment it hard-stops — no partial degradation. Checking usage weekly costs 2 minutes; discovering a limit hit from users costs a full month wait.

**Free tiers for revenue-generating production without Pro.** The ~$78/month compound upgrade (see decision matrix) costs less than one hour of incident response.

**Assuming free-tier limits are stable.** OCI, Vercel, and Supabase each revise their free-tier definitions quarterly. Re-verify at sources before provisioning decisions.

**Keepalive cron without failure alerting.** A silently failing workflow provides no protection. Always `exit 1` on unexpected responses and enable GitHub Actions email notifications for workflow failures under **Settings → Notifications**.

---

## Sources

- **OCI Budgets overview:** https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm — _authoritative_
- **OCI Always Free resources and reclamation policy:** https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm — _authoritative_
- **Vercel Hobby limits:** https://vercel.com/docs/limits — _authoritative_
- **Supabase pricing and pause policy:** https://supabase.com/pricing — _authoritative_
- **OCI Always Free FAQ (reclamation conditions):** https://www.oracle.com/cloud/free/faq/ — _authoritative_
- **Vercel community — Hobby bandwidth tracking patterns:** https://github.com/orgs/vercel/discussions — _community: Vercel GitHub Discussions_

Last verified: 2026-05-04 (OCI Always Free / Vercel Hobby / Supabase Free 2026 policy).
