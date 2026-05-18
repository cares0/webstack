# Observability stack (Grafana Cloud + Sentry + UptimeRobot)

> Reference for /webstack:infra and /webstack:deploy slash commands.
> ⚙️ **Optional integration** — activated via init's "Observability" question (`manifest.optional_integrations.observability=true`). Until activated, this document is reference-only; setup steps live in `recipes/observability-setup.md`.
> Free-tier observability stack: Grafana Cloud LGTM (Loki + Grafana + Tempo + Mimir) + Sentry + UptimeRobot for webstack's 3-repo Vercel + OCI + Supabase deployment.

## What is webstack observability stack

webstack observability is a coordinated set of free-tier SaaS tools that covers the three golden signals — **metrics**, **logs**, and **traces** — across all three deployment targets simultaneously.

| Layer | Signal | Tool |
|---|---|---|
| Backend (OCI VM / Spring Boot) | Metrics + Traces + Logs | Grafana Cloud LGTM via OTLP |
| Frontend (Vercel) | Page views + Web Vitals | Vercel Web Analytics + Speed Insights |
| Frontend (Vercel) | JS errors | Sentry Browser SDK |
| Backend (Spring Boot) | Java exceptions | Sentry Java SDK |
| All | Uptime / latency | UptimeRobot Free |

The stack is deliberately **opt-in** (Tier 3): a greenfield project does not need observability until it has traffic. The `manifest.optional_integrations.observability` flag gates all three tools at once; activating it triggers the setup recipe in `recipes/observability-setup.md`, which provisions Grafana Cloud stacks, Sentry projects, and UptimeRobot monitors in sequence.

Paired documents:

- `docs/backend/observability.md` — application-side instrumentation (Micrometer, OTel Java agent, Logback JSON). Read this for Spring Boot code; the present document covers the infrastructure side (collector, data sources, dashboards, alert routing).
- `docs/frontend/error-monitoring.md` — `@sentry/nextjs` SDK setup, Error Boundary placement, Session Replay, Sentry MCP integration.

---

## Why this stack

**Free tier coverage is complete.** Grafana Cloud Free, Sentry Developer, and UptimeRobot Free each cover an early-stage webstack project with zero credit card requirement. All three tools scale to paid tiers with a single click when limits are reached.

**OTel is the standard transport.** Spring Boot 4 + Micrometer + the OTel Java agent (or Grafana OTel Distribution) emit metrics, traces, and logs over OTLP — one protocol, one auth token, one endpoint. Switching backends later is an environment variable change, not a code rewrite.

**Vercel-native analytics add zero overhead.** Vercel Web Analytics and Speed Insights are injected by the platform — no SDK bundle, no cookie consent, no extra deploy step.

**Sentry bridges FE and BE error context.** The same Sentry organisation receives browser exceptions and JVM exceptions. `error.digest` on the FE side correlates with the server-side `onRequestError` event for RSC failures.

**UptimeRobot closes the external availability gap.** Internal metrics show the service is healthy from inside the VM; UptimeRobot confirms it is reachable by real users from the public internet.

---

## Grafana Cloud Free LGTM (Loki/Tempo/Mimir)

### Free tier limits (verified 2026-05)

| Signal | Ingest limit | Retention |
|---|---|---|
| Metrics (Mimir) | 10,000 active series/month | 14 days |
| Logs (Loki) | 50 GB ingested/month | 14 days |
| Traces (Tempo) | 50 GB ingested/month | 14 days |
| Profiles (Pyroscope) | 50 GB ingested/month | 14 days |
| Grafana users | 3 active users/month | — |
| Synthetics | 100k API test executions + 10k browser test executions/month | — |

A typical early-stage webstack project emits well under these limits: ~200–500 active metric series, a few gigabytes of logs, and trace volume proportional to request rate. The 10k series limit is the first constraint a growing project hits — see Anti-patterns for the main cause (high-cardinality tags).

### Sign-up and stack creation

1. Go to https://grafana.com/auth/sign-up/create-user and create a free account.
2. After confirming your email, Grafana prompts you to create your first **Cloud stack**. A stack bundles one Grafana instance, one Mimir (metrics), one Loki (logs), and one Tempo (traces) data source together under a regional zone (e.g., `prod-us-east-0`, `prod-eu-west-0`).
3. Choose the zone nearest your OCI region. Note the **stack slug** (e.g., `myproject`) — it appears in all endpoint URLs.
4. In the Grafana Cloud Portal → **My Account → Access Policies**, create an access policy named `webstack-ingest` with scopes `metrics:write`, `logs:write`, `traces:write`, `profiles:write`. Generate a token and store it as `GRAFANA_OTLP_TOKEN` in your shell environment and as a GitHub Secret.
5. Note your **Instance ID** (numeric, shown in the portal) as `GRAFANA_INSTANCE_ID`.

### OTLP endpoint URL and authentication

Grafana Cloud exposes a single OTLP gateway per stack:

```
https://otlp-gateway-<zone>.grafana.net/otlp
```

Example for `prod-us-east-0`:

```
https://otlp-gateway-prod-us-east-0.grafana.net/otlp
```

Authentication uses HTTP Basic with the instance ID as the username and the access policy token as the password, encoded in `Authorization: Basic <base64(instanceId:token)>`.

The Grafana OTel Distribution for Java (`grafana-opentelemetry-java`) abstracts this: provide `grafana.otlp.cloud.zone`, `grafana.otlp.cloud.instanceId`, and `grafana.otlp.cloud.apiKey` in `application.yml` and the library constructs the endpoint and header automatically. See `docs/backend/observability.md` §Grafana OTLP starter for the full YAML block.

For the raw OTel Java agent or any non-Java client, set these environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp-gateway-<zone>.grafana.net/otlp"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic $(echo -n '<instanceId>:<token>' | base64)"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
```

### Traffic fit assessment

An OCI Always Free VM running a single Spring Boot service under typical early-stage load (< 100 RPS, one deployment per day) generates approximately:

| Signal | Estimated monthly volume |
|---|---|
| Metrics | 300–800 active series (Spring auto-instrumentation + 5–10 custom meters) |
| Logs | 1–5 GB (INFO + WARN, structured JSON via Logback) |
| Traces | 2–10 GB (10% head-based sampling on 100 RPS) |

All three estimates fall well within the 10k / 50 GB / 50 GB free limits. Sampling at 10% for traces is the default webstack recommendation (see `backend/observability.md` §Sampling); switch to 1% if trace volume approaches the limit.

---

## BE integration

The Spring Boot 4 + Kotlin backend sends all three signals (metrics, traces, logs) over OTLP to Grafana Cloud using one of two paths:

**Path A — Grafana OTel Distribution (recommended for Grafana Cloud):**

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

This path is zero-config: the library resolves the OTLP endpoint, constructs the Basic auth header, and wires Micrometer + Logback automatically.

**Path B — Raw OTel Java agent (for non-Grafana backends or when Grafana OTel Distribution is unavailable):**

```yaml
# kubernetes/deployment.yaml or systemd unit environment
JAVA_TOOL_OPTIONS: "-javaagent:/opt/otel/opentelemetry-javaagent.jar"
OTEL_SERVICE_NAME: "myproject-backend"
OTEL_EXPORTER_OTLP_ENDPOINT: "https://otlp-gateway-<zone>.grafana.net/otlp"
OTEL_EXPORTER_OTLP_HEADERS: "Authorization=Basic <base64(instanceId:token)>"
OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
OTEL_LOGS_EXPORTER: "otlp"
```

For full instrumentation code — `@Timed`, `@Observed`, manual spans, Logback JSON encoder, MDC trace correlation, `RequestIdFilter`, health probes — see `docs/backend/observability.md`. The present document covers the infrastructure plumbing only.

### Loki derived field for trace-log navigation

After logs arrive in Loki, configure the Loki data source in Grafana to derive a trace link from the `trace_id` field:

1. Grafana → **Connections → Data sources → Loki → Derived fields**.
2. Add: Name `Trace ID`, Regex `"trace_id":"([^"]+)"`, URL `${__value.raw}`, Internal link → Tempo data source.

This enables one-click navigation from a Loki log line to the Tempo span tree for the same trace.

---

## FE integration

### Vercel Web Analytics

Vercel Web Analytics is available on all Vercel plans including Hobby. It is privacy-preserving (no cookies, no cross-site tracking), injected by the Vercel platform, and zero-configuration for Next.js projects.

Enable in your Next.js app:

```tsx
// app/layout.tsx
import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/next'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        {children}
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  )
}
```

```bash
pnpm add @vercel/analytics @vercel/speed-insights
```

Enable in the Vercel dashboard: **Project → Analytics** (toggle on). Speed Insights measures Core Web Vitals (LCP, FID/INP, CLS) from real user sessions.

**Hobby tier limits:** Vercel's Web Analytics data is available for the last 30 days of traffic on the Hobby plan. Custom events via `track()` are supported. There is no hard events-per-month limit shown in the public docs; the 30-day rolling window applies. Speed Insights is available on all plans with no explicit monthly cap for basic vitals.

### Sentry Browser SDK

For JavaScript error monitoring, see `docs/frontend/error-monitoring.md` for the full `@sentry/nextjs` setup: `instrumentation-client.ts`, `sentry.server.config.ts`, `sentry.edge.config.ts`, `withSentryConfig`, Error Boundary placement, Session Replay sampling, and source map upload. The infrastructure side (Sentry project creation, DSN, Vercel integration) is covered in §Sentry Cloud Free below.

---

## Sentry Cloud Free

### Plan limits (Developer plan, verified 2026-05)

| Quota | Developer (Free) |
|---|---|
| Errors | 5,000 events/month |
| Source map upload | Included |
| Session Replay | Included (limited quota) |
| Team members | 1 (solo) |
| Projects | Unlimited |
| Data retention | 30 days |
| Sentry MCP access | Included (OAuth) |

The 5k errors/month limit is sufficient for early-stage projects. The critical upgrade trigger is error volume, not feature gates — source maps, replay, and MCP are free on the Developer plan.

### Project setup

1. Create an account at https://sentry.io/signup/ (Developer plan, no credit card).
2. Create two projects: one `javascript-nextjs` (FE) and one `java` or `java-spring` (BE), both in the same Sentry organisation.
3. Copy each project's DSN: `NEXT_PUBLIC_SENTRY_DSN` (FE) and `SENTRY_DSN` (BE).
4. Install the Sentry Vercel integration (Sentry marketplace → Vercel → Connect). This injects `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` into Vercel build environments automatically.
5. Add `SENTRY_DSN` to the OCI VM systemd unit environment for the Spring Boot service.

### Alert rules

Sentry alerts are configured per-project under **Alerts → Create Alert Rule**. Recommended starter rules:

```yaml
# Alert rule: error spike (FE project)
name: FE error spike
condition: event count > 50 in 1 hour
filter: level = error
action: notify via email / Slack webhook

# Alert rule: first seen (BE project)
name: New BE exception type
condition: first seen
filter: level = error
action: notify via email / Slack webhook
```

For Slack notification, add a Slack integration under **Settings → Integrations → Slack** and configure the alert action to send to your `#alerts` channel.

### FE + BE unified view

Both FE and BE projects are visible in the same Sentry organisation. Cross-project search allows querying errors across runtimes simultaneously. The `error.digest` mechanism in Next.js 16 correlates a client-side boundary with the corresponding server-side `onRequestError` capture — both events share a digest value, enabling one-click navigation from the FE issue to the BE stack trace.

---

## UptimeRobot Free

### Plan limits (Free plan, verified 2026-05)

| Feature | Free |
|---|---|
| Monitors | 50 |
| Check interval | 5 minutes |
| Monitor types | HTTP, port, ping, keyword, API, UDP, DNS, SSL |
| Alert contacts | 5 integrations |
| Status pages | Basic |
| Data retention | 3 months |

The 5-minute interval means a 5-minute-long outage may be detected anywhere between 0 and 5 minutes after onset. For stricter SLAs, upgrade to a paid plan (60-second interval) or complement with Grafana Cloud Synthetics (free tier: 100k API test executions/month).

### Monitor setup for webstack

Create these monitors in UptimeRobot:

| Monitor | URL | Type |
|---|---|---|
| FE production | `https://<project>.vercel.app` | HTTP(S) |
| BE health | `https://<oci-vm-ip-or-domain>/actuator/health/readiness` | HTTP(S) — keyword: `"status":"UP"` |
| Supabase REST | `https://<project-ref>.supabase.co/rest/v1/` | HTTP(S) |

Set **Keyword monitors** for the BE health endpoint — a 200 response with a wrong body (e.g., `"status":"DOWN"`) otherwise passes silently.

### Status page

UptimeRobot's free status page is shareable at `https://status.uptimerobot.com/<unique-slug>`. Link it from your product's footer or README so users can self-diagnose before filing support tickets.

### BetterStack complement

UptimeRobot Free's 5-minute interval and basic status page are sufficient for solo projects. BetterStack Uptime (free tier: 3-minute interval, unlimited monitors) is a drop-in alternative with a more polished status page. Both tools are free; the webstack default is UptimeRobot because it offers 50 monitors (vs. BetterStack Uptime's 10 on the free tier).

---

## RED/USE dashboards

### Importing the standard BE dashboard

Import the Grafana Labs community dashboard **Spring Boot 2.1 / 3.x Statistics** (ID: `11378`) into your Grafana Cloud stack:

1. Grafana → **Dashboards → Import → Import via grafana.com** → enter `11378`.
2. Select your Mimir data source for the Prometheus data source field.
3. Save.

This dashboard provides HTTP request rate, error rate, p50/p95/p99 latency, JVM heap, GC pauses, thread pools, and HikariCP connection pool metrics out of the box — no custom configuration needed beyond the standard Spring Boot Actuator + Micrometer OTLP setup.

### Custom RED dashboard JSON snippet

For a minimal 3-panel RED dashboard targeting a single domain service (e.g., `billing`), import this JSON via **Dashboards → Import → Paste JSON**:

```json
{
  "title": "billing — RED",
  "panels": [
    {
      "title": "Request Rate (req/s)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "rate(billing_invoice_create_seconds_count[5m])",
          "legendFormat": "rate"
        }
      ]
    },
    {
      "title": "Error Rate (%)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "rate(billing_invoice_create_seconds_count{exception!='none'}[5m]) / rate(billing_invoice_create_seconds_count[5m]) * 100",
          "legendFormat": "error %"
        }
      ]
    },
    {
      "title": "p95 Latency (s)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(billing_invoice_create_seconds_bucket[5m])) by (le))",
          "legendFormat": "p95"
        }
      ]
    }
  ],
  "schemaVersion": 38,
  "version": 1
}
```

Replace `billing_invoice_create` with your domain's meter name. The `exception!='none'` tag filter counts only failed invocations — Spring Boot adds the `exception` tag automatically when `@Timed` records an exception.

### USE dashboard for JVM resources

Standard USE panels for the OCI VM backend:

| Panel | PromQL expression |
|---|---|
| Heap utilization | `jvm_memory_used_bytes{area="heap"} / jvm_memory_max_bytes{area="heap"}` |
| Thread saturation | `jvm_threads_states_threads{state="blocked"} / jvm_threads_live_threads` |
| DB connection errors | `rate(hikaricp_connections_timeout_total[5m])` |
| GC pause rate | `rate(jvm_gc_pause_seconds_count[5m])` |

---

## Alerting channels

### Grafana → Slack / Discord webhook

1. In Grafana Cloud → **Alerting → Contact points → New contact point**.
2. Choose **Slack** (or **Webhook** for Discord). Paste your webhook URL.
3. Save and set as the default contact point under **Notification policies**.

Recommended alert rules (under **Alerting → Alert rules → New alert rule**):

```yaml
# High error rate
name: BE high error rate
condition: rate(http_server_requests_seconds_count{status=~"5.."}[5m]) / rate(http_server_requests_seconds_count[5m]) > 0.05
for: 5m
labels: { severity: warning }
annotations:
  summary: "BE error rate > 5% for 5 minutes"

# Heap pressure
name: JVM heap > 85%
condition: jvm_memory_used_bytes{area="heap"} / jvm_memory_max_bytes{area="heap"} > 0.85
for: 10m
labels: { severity: warning }

# Loki log-based alert (error spike)
name: Log error spike
datasource: Loki
condition: count_over_time({service="myproject-backend"} |= "ERROR" [5m]) > 50
for: 0s
labels: { severity: critical }
```

### Threshold definitions

| Metric | Warning threshold | Critical threshold |
|---|---|---|
| HTTP 5xx rate | > 1% for 5 min | > 5% for 5 min |
| p95 latency | > 1 s | > 3 s |
| JVM heap | > 75% for 10 min | > 90% for 5 min |
| Active metric series | > 8,000 | > 9,500 (approaching free limit) |
| Grafana logs ingest | > 40 GB/month | > 48 GB/month |

Alert at **warning** in Slack `#alerts`; alert at **critical** in Slack `#incidents` with `@here` mention.

---

## Sentry MCP integration

The Sentry MCP server (`https://mcp.sentry.dev/mcp`) is available to all Sentry users (cloud, including free) via OAuth. It exposes 19 tools for issue triage, event inspection, release management, and Seer AI root cause analysis.

### Adding to Claude Code

```bash
claude mcp add --transport http sentry https://mcp.sentry.dev/mcp
```

Or add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "sentry": {
      "type": "http",
      "url": "https://mcp.sentry.dev/mcp"
    }
  }
}
```

Scope to a specific organisation and project to reduce noise:

```bash
claude mcp add --transport http sentry "https://mcp.sentry.dev/mcp?org=myorg&project=myproject-fe"
```

### Automated issue triage (G1 capability)

The Sentry MCP integration enables automated issue classification during `/webstack:feature` and `/webstack:deploy` flows:

**Release sync:** `withSentryConfig` in `next.config.ts` reads `VERCEL_GIT_COMMIT_SHA` automatically on Vercel and tags every error event with the commit SHA. The BE deploy workflow sets `SENTRY_RELEASE=$(git rev-parse --short HEAD)` before `gradle build`. Both pipelines create matching Sentry releases, allowing error volume comparisons between releases.

**Automatic triage workflow:**

```
/webstack:deploy → Vercel + OCI deploy completes
→ Sentry MCP: search_issues(project=myproject-fe, query="is:unresolved firstSeen:>5m ago")
→ If new issues found: search_events(issue_id=<id>) → read stack trace
→ Cross-link to git commit → open relevant file → propose fix
→ Re-deploy → confirm error rate dropped on new release
```

The entire loop runs without leaving Claude Code.

---

## Pro upgrade trigger

webstack free-tier observability is designed to carry a project from launch to first revenue. The following table defines decision points for upgrading each component:

| Tool | Free limit | Upgrade trigger | Paid tier cost (2026) |
|---|---|---|---|
| Grafana Cloud | 10k metric series, 50 GB logs, 50 GB traces, 14-day retention | Series consistently > 8k, or alert retention gap > 14 days | Grafana Cloud Pro: $0 to ~$10–30/month (pay-per-use) |
| Sentry | 5,000 errors/month | Monthly errors consistently > 4k, or team size > 1 | Sentry Team: $26/month (50k errors) |
| UptimeRobot | 5-minute interval | SLA requires < 5-minute detection, or > 50 monitors | UptimeRobot Solo: $7/month (1-minute interval) |
| Vercel Analytics | 30-day rolling window | Historical trend analysis beyond 30 days required | Vercel Pro: $20/month/member |

**Decision matrix:**

```
Metric series > 8k/month AND growing?
  → Identify high-cardinality metric sources (see Anti-patterns) first.
  → If already optimised, upgrade Grafana Cloud (metered billing starts at series count).

Error volume > 4k/month?
  → Check for error storms from a single regression before upgrading.
  → If steady-state volume, upgrade Sentry Team.

Revenue-generating production traffic?
  → Upgrade Sentry + UptimeRobot simultaneously — both are < $35/month combined.
  → Consider Grafana Cloud Pro for 13-month retention (compliance) if applicable.
```

---

## Anti-patterns

**Exporting every metric from Spring Boot.** `management.metrics.enable.all=true` with no filtering emits hundreds of JVM, HTTP, Executor, and Spring internals metrics — easily 2,000–5,000 series per instance. On Grafana Cloud Free (10k series limit), two instances saturate the quota before any custom business metrics. Filter with `management.metrics.enable.<prefix>=false` for namespaces you don't query.

**Unbounded metric tags.** Adding a user ID, invoice ID, or any per-entity value as a Micrometer tag creates one time series per unique tag value. For a service with 1,000 users, a single `tag("userId", id)` meter produces 1,000 series — exhausting the free quota in a few hours. Keep tags low-cardinality: status codes, payment method types, error categories. Correlated entity data belongs in trace span attributes and structured log fields, not metrics.

**Alert thresholds left undefined.** Creating alert rules with `> 0` thresholds (fire on any error) generates alert fatigue within days of launch. Every alert rule must have a human-reviewed threshold; use the table in §Alerting channels as a starting point. Review and tune after the first month of production traffic.

**Using Sentry as a log aggregator.** Sentry's 5k events/month quota is consumed by error events, not logs. Calling `Sentry.captureMessage` for INFO-level operational logs, user actions, or expected validation failures burns the quota on non-actionable noise. All structured logs flow to Loki; Sentry receives only unexpected exceptions. See `docs/frontend/error-monitoring.md` §Anti-patterns for the full list.

**Skipping trace sampling.** At 100 RPS with 100% sampling and a 5 KB average trace size, a single instance generates ~43 GB of traces per day — 25× the monthly free limit in one day. Set head-based sampling to 10% at minimum via `OTEL_TRACES_SAMPLER_ARG=0.1`. Tune downward if Tempo ingest approaches 50 GB/month.

**Monitoring only the BE health endpoint with UptimeRobot.** The `/actuator/health/readiness` endpoint runs on the OCI VM's internal port. A firewall rule change, OCI security list update, or Vercel DNS misconfiguration can leave the FE unreachable while the BE endpoint stays green. Monitor both the FE Vercel URL and the BE public endpoint independently.

**Grafana alert rules without a notification policy.** Alert rules fire silently unless a notification policy routes them to a contact point. After creating any alert rule, verify it appears in **Alerting → Notification policies** under the correct matcher. Send a test notification before considering the setup complete.

---

## Sources

- **Grafana Cloud pricing:** https://grafana.com/pricing/ — _authoritative_
- **Grafana Cloud OTLP endpoint — send-data-otlp:** https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/ — _authoritative_
- **Sentry pricing — Developer plan:** https://docs.sentry.io/product/pricing/ — _authoritative_
- **UptimeRobot pricing:** https://uptimerobot.com/pricing/ — _authoritative_
- **Vercel Web Analytics docs:** https://vercel.com/docs/analytics — _community: Vercel-affiliated_
- **Grafana Labs community dashboard — Spring Boot 3.x Statistics (ID 11378):** https://grafana.com/grafana/dashboards/11378 — _community: Grafana Labs dashboard repo_

Last verified: 2026-05-04 (Grafana Cloud Free 2026 / Sentry Free / UptimeRobot Free / OpenTelemetry Java 2.X).
