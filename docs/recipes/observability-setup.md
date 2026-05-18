# Recipe — Observability setup (Sentry + Grafana Cloud + UptimeRobot)

> Setup walkthrough for activating webstack's observability stack. Triggered when init's "Observability" question is answered Yes (`manifest.optional_integrations.observability=true`).
> Reference docs: `docs/frontend/error-monitoring.md`, `docs/backend/observability.md`, `docs/infrastructure/observability-stack.md`.

Step-by-step activation guide — each step produces a concrete artefact (account, DSN, token, config) consumed by the next.

## What this recipe activates

| Tool | Signal | Target |
|---|---|---|
| **Sentry** (SDK 8.X) | JS + JVM exceptions | Vercel FE + OCI BE |
| **Grafana Cloud Free** (LGTM) | Metrics + traces + logs via OTLP | OCI BE |
| **UptimeRobot Free** | External HTTP uptime | FE + BE public URLs |

## Pre-conditions

- `webstack init` complete; FE (Next.js 16.X) and BE (Spring Boot 4.0.X + Kotlin + Gradle) repos exist.
- Shell access to both repos; ability to set Vercel env vars and OCI VM systemd unit env.
- `.webstack/manifest.yaml` present in the parent directory.

## Step 1 — Sentry account + DSN

1. Sign up at https://sentry.io/signup/ (Developer plan, no credit card).
2. Create two projects in the same org: `javascript-nextjs` (`<project>-fe`) and `java` (`<project>-be`).
3. Copy each DSN from **Project Settings → Client Keys**: `NEXT_PUBLIC_SENTRY_DSN` (FE), `SENTRY_DSN` (BE).
4. Note the org slug (`SENTRY_ORG`) and project slugs (`SENTRY_PROJECT`).
5. Install the **Sentry Vercel integration** (Sentry marketplace → Vercel → Connect) — injects `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` into Vercel builds automatically.

## Step 2 — Grafana Cloud Free + OTLP endpoint

1. Sign up at https://grafana.com/auth/sign-up/create-user (Free plan).
2. Create a **Cloud stack** — choose the zone nearest your OCI region (e.g., `prod-us-east-0`).
3. In **My Account → Access Policies**, create policy `webstack-ingest` with scopes `metrics:write`, `logs:write`, `traces:write`, `profiles:write`. Generate a token → `GRAFANA_OTLP_TOKEN`.
4. Note the numeric **Instance ID** from the portal → `GRAFANA_INSTANCE_ID`.
5. OTLP gateway URL: `https://otlp-gateway-<zone>.grafana.net/otlp` → `GRAFANA_OTLP_ENDPOINT`.

## Step 3 — UptimeRobot account

1. Sign up at https://uptimerobot.com/ (Free plan, 50 monitors, 5-minute interval).
2. Create three **HTTP(S) monitors**:

   | Monitor | URL | Extra |
   |---|---|---|
   | `<project>-fe` | `https://<project>.vercel.app` | — |
   | `<project>-be-health` | `https://<oci-domain>/actuator/health/readiness` | Keyword: `"status":"UP"` |
   | `<project>-supabase` | `https://<ref>.supabase.co/rest/v1/` | — |

3. Enable a free **Status Page** — link it from your product footer.

## Step 4 — BE dependencies

In `<backend>/build.gradle.kts`:

```kotlin
dependencies {
    implementation("com.grafana:grafana-opentelemetry-java:2.x")   // OTel + Grafana Cloud wiring
    implementation("io.micrometer:micrometer-registry-otlp")       // metrics OTLP export
    implementation("net.logstash.logback:logstash-logback-encoder:9.0")  // JSON logs
    implementation("io.sentry:sentry-spring-boot-starter-jakarta:8.+")   // Sentry JVM
}
```

Run `./gradlew dependencies` to confirm resolution.

## Step 5 — BE config

In `<backend>/src/main/resources/application.yml`:

```yaml
grafana:
  otlp:
    cloud:
      zone: prod-us-east-0          # replace with your stack zone
      instanceId: "${GRAFANA_INSTANCE_ID}"
      apiKey: "${GRAFANA_OTLP_TOKEN}"
    global-attributes:
      deployment.environment: "${ENVIRONMENT:production}"

sentry:
  dsn: "${SENTRY_DSN}"
  traces-sample-rate: 0.1
  environment: "${ENVIRONMENT:production}"

management:
  otlp.metrics.export:
    url: "${GRAFANA_OTLP_ENDPOINT}/v1/metrics"
    step: 60s
  observations.annotations.enabled: true
```

Create `<backend>/src/main/resources/logback-spring.xml` — JSON appender with `LogstashEncoder` including `trace_id` and `span_id` MDC keys for non-local profiles; plain pattern appender for `local` profile. Full template: see `docs/backend/observability.md` §Logs.

## Step 6 — FE Sentry SDK

```bash
# in <frontend>/
pnpm add @sentry/nextjs
```

`instrumentation-client.ts` (project root, not inside `src/`):

```ts
import * as Sentry from '@sentry/nextjs'
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  replaysSessionSampleRate: 0.001,        // 0.1% of sessions
  replaysOnErrorSampleRate: 1.0,          // 100% on error
  integrations: [Sentry.replayIntegration({ maskAllText: true, maskAllInputs: true })],
})
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart
```

`instrumentation.ts` — exports `register()` that `await import('./sentry.server.config')` on `nodejs` runtime and `./sentry.edge.config` on `edge`; exports `onRequestError = Sentry.captureRequestError`. Create identical `sentry.server.config.ts` and `sentry.edge.config.ts` with a bare `Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN })`. Wrap `next.config.ts` with `withSentryConfig` (org, project, authToken, `tunnelRoute: '/sentry-tunnel'`, `deleteSourcemapsAfterUpload: true`).

## Step 7 — FE Error Boundary

For each App Router route segment, create `src/app/(features)/<route>/error.tsx` — `'use client'`, `useEffect` calling `Sentry.captureException(error, { extra: { digest: error.digest } })`, render a retry button. Also create `app/global-error.tsx` (must render `<html><body>`) with the same `captureException` pattern. Full patterns in `docs/frontend/error-monitoring.md` §Error Boundary patterns.

## Step 8 — Environment variables

**Backend** (`<infra>/.env` + OCI VM `app.env`):

| Variable | Value |
|---|---|
| `GRAFANA_INSTANCE_ID` | Numeric instance ID (Grafana portal) |
| `GRAFANA_OTLP_TOKEN` | Access policy token |
| `GRAFANA_OTLP_ENDPOINT` | `https://otlp-gateway-<zone>.grafana.net/otlp` |
| `SENTRY_DSN` | BE project DSN |
| `ENVIRONMENT` | `production` |

**Frontend** (Vercel project env vars, Production + Preview):

| Variable | Scope |
|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | Browser + server (safe in bundle) |
| `SENTRY_AUTH_TOKEN` | Build only (injected by Sentry Vercel integration) |
| `SENTRY_ORG` / `SENTRY_PROJECT` | Build only |

Local dev: add `NEXT_PUBLIC_SENTRY_DSN` to `<frontend>/.env.local`.

## Step 9 — Verify

**BE logs show `trace_id`:**

```bash
journalctl -u myproject-backend -f | grep trace_id
# expect: {"trace_id":"abc123...","message":"..."}
```

**Sentry test event fires:** In the FE browser console, `throw new Error('sentry-test')`. Confirm it appears under `<project>-fe → Issues` within 30 seconds.

**Grafana metrics visible:** Grafana Cloud → **Explore → Mimir** → query `http_server_requests_seconds_count`. Data should appear within 2 minutes of BE startup.

**UptimeRobot monitors green:** Dashboard shows status **Up** for all three monitors; keyword check matches `"status":"UP"`.

## Step 10 — manifest flag ON

```yaml
# .webstack/manifest.yaml
optional_integrations:
  observability: true
```

```bash
git -C <parent-dir> add .webstack/manifest.yaml
git -C <parent-dir> commit -m "chore: enable observability integration"
```

This flag signals to `/webstack:feature` and `/webstack:deploy` that observability is live and instrumentation expectations apply to all future features.

## Reference docs

- `docs/frontend/error-monitoring.md` — `@sentry/nextjs` SDK, Error Boundary patterns, Session Replay, Sentry MCP.
- `docs/backend/observability.md` — Micrometer, `@Timed`/`@Observed`, OTel Java agent, Logback JSON, trace-log correlation.
- `docs/infrastructure/observability-stack.md` — Grafana Cloud free limits, Loki derived fields, RED/USE dashboards, alert rules, upgrade triggers.

## Sources

- **Sentry Next.js manual setup:** https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/ — _authoritative_
- **Grafana Cloud OTLP endpoint:** https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/ — _authoritative_
- **Grafana OpenTelemetry Distribution for Java:** https://github.com/grafana/grafana-opentelemetry-java — _community: Grafana Labs_
- **UptimeRobot documentation:** https://uptimerobot.com/help/ — _authoritative_

Last verified: 2026-05-04 (Sentry SDK 8.X / Grafana Cloud Free / UptimeRobot Free / Spring Boot 4.0.X / Next.js 16.X).
