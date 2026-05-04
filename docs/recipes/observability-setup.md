# Recipe — Observability setup (Sentry + Grafana Cloud + UptimeRobot)

> Setup walkthrough for activating webstack's observability stack. Triggered when init's "Observability" question is answered Yes (`manifest.optional_integrations.observability=true`).
> Reference docs: `docs/frontend/error-monitoring.md`, `docs/backend/observability.md`, `docs/infrastructure/observability-stack.md`.

This recipe is a step-by-step activation guide. Run the steps in order; each step produces a concrete artefact (account, DSN, token, config file) that the next step consumes.

## What this recipe activates

Three free-tier SaaS tools that cover the three golden signals across both deployment targets:

| Tool | Signal | Target |
|---|---|---|
| **Sentry** (SDK 8.X) | JS + JVM exceptions | Vercel FE + OCI BE |
| **Grafana Cloud Free** (LGTM) | Metrics + traces + logs via OTLP | OCI BE |
| **UptimeRobot Free** | External HTTP uptime | FE + BE public URLs |

Once all steps are complete, set `manifest.optional_integrations.observability: true` (Step 10) so webstack subagents know the integration is live.

## Pre-conditions

- webstack `init` completed; FE and BE repos exist under the parent directory.
- BE repo is a Spring Boot 3.4.X + Kotlin project with Gradle (`build.gradle.kts`).
- FE repo is a Next.js 16.X project managed with `pnpm`.
- You have shell access to both repos and can push env vars to Vercel and to the OCI VM systemd unit.
- Parent directory `.webstack/manifest.yaml` is present.

## Step 1 — Sentry account + DSN

1. Sign up at https://sentry.io/signup/ (Developer plan — no credit card).
2. Create **two projects** inside the same organisation:
   - Platform `javascript-nextjs` → name it `<project>-fe`.
   - Platform `java` (or `java-spring`) → name it `<project>-be`.
3. Copy each project's DSN from **Project Settings → Client Keys**:
   - FE DSN → `NEXT_PUBLIC_SENTRY_DSN`
   - BE DSN → `SENTRY_DSN`
4. Copy the organisation slug (`SENTRY_ORG`) and each project slug (`SENTRY_PROJECT`).
5. Install the **Sentry Vercel integration** (Sentry marketplace → Vercel → Connect) — this injects `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` into Vercel build environments automatically.

## Step 2 — Grafana Cloud Free + OTLP endpoint

1. Sign up at https://grafana.com/auth/sign-up/create-user (Free plan).
2. After email confirmation, create your first **Cloud stack**. Choose the zone nearest your OCI region (e.g., `prod-us-east-0`). Note the stack slug.
3. In Grafana Cloud Portal → **My Account → Access Policies**, create policy `webstack-ingest` with scopes `metrics:write`, `logs:write`, `traces:write`, `profiles:write`.
4. Generate a token → store it as `GRAFANA_OTLP_TOKEN`.
5. Note your numeric **Instance ID** from the portal → store as `GRAFANA_INSTANCE_ID`.
6. Your OTLP gateway URL is `https://otlp-gateway-<zone>.grafana.net/otlp` — store as `GRAFANA_OTLP_ENDPOINT`.

## Step 3 — UptimeRobot account

1. Sign up at https://uptimerobot.com/ (Free plan — 50 monitors, 5-minute interval).
2. After login, create three **HTTP(S) monitors**:

   | Monitor name | URL | Extra |
   |---|---|---|
   | `<project>-fe` | `https://<project>.vercel.app` | — |
   | `<project>-be-health` | `https://<oci-domain>/actuator/health/readiness` | Keyword: `"status":"UP"` |
   | `<project>-supabase` | `https://<project-ref>.supabase.co/rest/v1/` | — |

3. Enable a **Status Page** (free) at `https://status.uptimerobot.com/<slug>` — link it from your product footer.

## Step 4 — BE dependencies

Add to `<backend>/build.gradle.kts`:

```kotlin
dependencies {
    // Grafana OTel Distribution — wires Micrometer + OTel + Logback to Grafana Cloud
    implementation("com.grafana:grafana-opentelemetry-java:2.x")

    // Micrometer OTLP registry (metrics export)
    implementation("io.micrometer:micrometer-registry-otlp")

    // Logback JSON encoder (structured logs with trace_id MDC field)
    implementation("net.logstash.logback:logstash-logback-encoder:9.0")

    // Sentry Spring Boot starter
    implementation("io.sentry:sentry-spring-boot-starter-jakarta:8.+")
}
```

Run `./gradlew dependencies` to confirm resolution before proceeding.

## Step 5 — BE config

Add to `<backend>/src/main/resources/application.yml`:

```yaml
grafana:
  otlp:
    cloud:
      zone: prod-us-east-0          # replace with your stack zone
      instanceId: "${GRAFANA_INSTANCE_ID}"
      apiKey: "${GRAFANA_OTLP_TOKEN}"
    global-attributes:
      service.version: "${APP_VERSION:dev}"
      deployment.environment: "${ENVIRONMENT:production}"

sentry:
  dsn: "${SENTRY_DSN}"
  traces-sample-rate: 0.1
  environment: "${ENVIRONMENT:production}"

management:
  otlp:
    metrics:
      export:
        url: "${GRAFANA_OTLP_ENDPOINT}/v1/metrics"
        step: 60s
  observations:
    annotations:
      enabled: true
```

Create `<backend>/src/main/resources/logback-spring.xml`:

```xml
<configuration>
  <springProperty scope="context" name="appName" source="spring.application.name"/>

  <appender name="JSON" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <customFields>{"service":"${appName}"}</customFields>
      <includeMdcKeyName>trace_id</includeMdcKeyName>
      <includeMdcKeyName>span_id</includeMdcKeyName>
      <includeMdcKeyName>request_id</includeMdcKeyName>
    </encoder>
  </appender>

  <springProfile name="local">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
      <encoder>
        <pattern>%d{HH:mm:ss} %-5level [%X{trace_id:-no-trace}] %logger{36} - %msg%n</pattern>
      </encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
  </springProfile>

  <springProfile name="!local">
    <root level="INFO"><appender-ref ref="JSON"/></root>
  </springProfile>
</configuration>
```

## Step 6 — FE Sentry SDK

```bash
# in <frontend>/
pnpm add @sentry/nextjs
```

Create `<frontend>/instrumentation-client.ts` (project root, not inside `src/`):

```ts
import * as Sentry from '@sentry/nextjs'

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  replaysSessionSampleRate: 0.001,
  replaysOnErrorSampleRate: 1.0,
  integrations: [Sentry.replayIntegration({ maskAllText: true, maskAllInputs: true })],
  environment: process.env.NODE_ENV,
})

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart
```

Create `<frontend>/instrumentation.ts`:

```ts
import * as Sentry from '@sentry/nextjs'

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') await import('./sentry.server.config')
  if (process.env.NEXT_RUNTIME === 'edge') await import('./sentry.edge.config')
}

export const onRequestError = Sentry.captureRequestError
```

Create `<frontend>/sentry.server.config.ts` and `<frontend>/sentry.edge.config.ts` (identical content):

```ts
import * as Sentry from '@sentry/nextjs'

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  environment: process.env.NODE_ENV,
})
```

Wrap `next.config.ts`:

```ts
import { withSentryConfig } from '@sentry/nextjs'
import type { NextConfig } from 'next'

const nextConfig: NextConfig = { /* existing config */ }

export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  tunnelRoute: '/sentry-tunnel',
  silent: !process.env.CI,
  sourcemaps: { disable: false, deleteSourcemapsAfterUpload: true },
})
```

## Step 7 — FE Error Boundary

Add a route-level `error.tsx` for each App Router route segment. Minimal template:

```tsx
// src/app/(features)/<route>/error.tsx
'use client'

import { useEffect } from 'react'
import * as Sentry from '@sentry/nextjs'

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    Sentry.captureException(error, { extra: { digest: error.digest } })
  }, [error])

  return (
    <div role="alert">
      <p>Something went wrong.</p>
      <button onClick={reset}>Try again</button>
    </div>
  )
}
```

Also create `<frontend>/app/global-error.tsx` for root layout errors (must render `<html><body>`):

```tsx
'use client'
import { useEffect } from 'react'
import * as Sentry from '@sentry/nextjs'

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => { Sentry.captureException(error, { tags: { scope: 'global' } }) }, [error])
  return <html><body><p>A critical error occurred. Please refresh.</p></body></html>
}
```

## Step 8 — Environment variables

**Backend** — add to `<infra>/.env` (gitignored) and OCI VM systemd unit `app.env`:

| Variable | Value |
|---|---|
| `GRAFANA_INSTANCE_ID` | Numeric instance ID from Grafana Cloud portal |
| `GRAFANA_OTLP_TOKEN` | Access policy token (`webstack-ingest`) |
| `GRAFANA_OTLP_ENDPOINT` | `https://otlp-gateway-<zone>.grafana.net/otlp` |
| `SENTRY_DSN` | BE project DSN from Sentry |
| `ENVIRONMENT` | `production` |
| `APP_VERSION` | `$(git rev-parse --short HEAD)` |

**Frontend** — add to Vercel project environment variables (Production + Preview):

| Variable | Scope |
|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | Browser + server (safe in bundle) |
| `SENTRY_AUTH_TOKEN` | Build only (injected by Sentry Vercel integration) |
| `SENTRY_ORG` | Build only |
| `SENTRY_PROJECT` | Build only |

For local dev, add `NEXT_PUBLIC_SENTRY_DSN` to `<frontend>/.env.local`.

## Step 9 — Verify

**Backend logs carry `trace_id`:**

```bash
# SSH into OCI VM, tail the service log
journalctl -u myproject-backend -f | grep trace_id
# Expect: {"trace_id":"abc123...","message":"..."}
```

**Sentry receives a test event:**

```bash
# In <frontend>/ — trigger a test error
pnpm sentry:wizard --no-telemetry
# Or manually: in browser console → throw new Error('sentry-test')
# Check sentry.io → <project>-fe → Issues
```

**Grafana metrics visible:**

1. Grafana Cloud → **Explore → Mimir data source**.
2. Run query: `{job="<project>-backend"}` or `http_server_requests_seconds_count`.
3. Confirm data points appear within 2 minutes of BE startup.

**UptimeRobot monitors green:**

- Dashboard → All monitors show status **Up**.
- Keyword monitor for BE health shows `"status":"UP"` match.

## Step 10 — manifest flag ON

Once all three tools are verified, set the manifest flag:

```yaml
# .webstack/manifest.yaml
optional_integrations:
  observability: true
```

Commit:

```bash
git -C <parent-dir> add .webstack/manifest.yaml
git -C <parent-dir> commit -m "chore: enable observability integration"
```

This flag signals to `/webstack:feature` and `/webstack:deploy` that the observability stack is active and instrumentation expectations apply to all future features.

## Reference docs

- `docs/frontend/error-monitoring.md` — `@sentry/nextjs` SDK details, Error Boundary patterns, Session Replay, Sentry MCP integration.
- `docs/backend/observability.md` — Micrometer meters, `@Timed`/`@Observed`, OTel Java agent, Logback JSON encoder, trace-log MDC correlation.
- `docs/infrastructure/observability-stack.md` — Grafana Cloud LGTM free limits, Loki derived fields for trace navigation, RED/USE dashboards, alert rules, UptimeRobot monitor table, pro upgrade triggers.

## Sources

- **Sentry Next.js manual setup:** https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/ — _authoritative_
- **Grafana Cloud OTLP endpoint:** https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/ — _authoritative_
- **Grafana OpenTelemetry Distribution for Java:** https://github.com/grafana/grafana-opentelemetry-java — _community: Grafana Labs_
- **UptimeRobot pricing + monitor types:** https://uptimerobot.com/pricing/ — _authoritative_

Last verified: 2026-05-04 (Sentry SDK 8.X / Grafana Cloud Free / UptimeRobot Free / Spring Boot 3.4.X / Next.js 16.X).
