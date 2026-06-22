# Domain & TLS (Cloudflare DNS + Vercel + Caddy on OCI)

> Reference for /webstack:infra and /webstack:deploy slash commands.
> Custom domain setup: Cloudflare DNS-only, Vercel apex + www, OCI VM HTTPS via Caddy 2 automatic ACME.

---

## What is webstack domain/TLS

A webstack project exposes two public surfaces:

- **Frontend** (`example.com` + `www.example.com`) — served by Vercel. Both records point to Vercel's edge; www redirects to apex (301).
- **API** (`api.example.com`) — served by the OCI Ampere A1 VM. Caddy 2 listens on 443, terminates TLS automatically via ACME, and reverse-proxies to Spring Boot on `localhost:8080`.

DNS lives in Cloudflare in **DNS-only mode** (gray cloud) — not a proxy, just a fast authoritative nameserver with API support for OpenTofu. Caddy manages TLS for the API subdomain end-to-end (issuance, storage, renewal, failover). Vercel manages TLS for apex and www automatically. No certbot, no cron jobs, no manual renewal anywhere in the stack.

---

## Why Caddy + Cloudflare DNS-only

### Automatic ACME removes operational burden

Caddy handles the complete TLS lifecycle — issuance, storage, renewal, CA failover — with no external tooling. The Caddyfile for a reverse-proxy entry is four lines; the nginx + certbot equivalent is fifty lines of infrastructure state that drifts. Caddy rate-limits ACME attempts internally (10/account/10 s) and retries renewal with exponential backoff for up to 30 days.

### Cloudflare proxy conflicts with Vercel apex routing

Orange-cloud proxying terminates TLS at Cloudflare and re-originates to Vercel, blocking Vercel's HTTP-01 ACME challenge and producing an `ERR_TOO_MANY_REDIRECTS` loop when Cloudflare SSL mode is "Flexible." Gray-cloud DNS-only lets DNS resolve directly to Vercel's IP and Vercel's ACME flow proceed normally.

The `api.example.com` record is also DNS-only to keep Caddy's HTTP-01 path clear. If Cloudflare proxying is needed for DDoS protection on the API, switch Caddy to DNS-01 challenge instead (requires a Cloudflare API token in the global block).

### Single-VM simplicity

On a single OCI Ampere A1 VM there is no load balancer, no ingress controller, and no container orchestrator. Caddy installs as one systemd service and reads one `Caddyfile`. See [Why not Nginx/Traefik](#why-not-nginxtraefik) for a direct comparison.

---

## DNS topology

All DNS records are created in Cloudflare for the registered domain. The table below shows the complete set for a domain named `example.com`.

| Record type | Name | Value | Proxy | Purpose |
|---|---|---|---|---|
| A | `example.com` | Vercel IP (from dashboard) | DNS-only (gray) | Apex → Vercel |
| CNAME | `www` | `cname.vercel-dns.com` | DNS-only (gray) | www → Vercel |
| A | `api` | OCI VM public IP | DNS-only (gray) | API → OCI VM |
| TXT | `_vercel` | Vercel verification token | DNS-only | Domain ownership proof |
| MX | `example.com` | mail provider records | DNS-only | Email — separate from app |
| TXT | `example.com` | SPF record | DNS-only | Email — separate from app |
| CNAME | `_dmarc` | DMARC provider | DNS-only | Email — separate from app |

Notes: Vercel provides the exact A record IP in **Project Settings > Domains** — copy it from there. The `api` A record IP is the `instance_public_ip` OpenTofu output. MX/SPF/DMARC are independent of app hosting and must remain DNS-only. Propagation on Cloudflare's anycast network is typically 1–5 minutes; TTL defaults to `Auto` (300 s).

---

## Cloudflare DNS-only setup

### Adding the domain

1. Cloudflare dashboard → **Add a Site**, enter `example.com`, choose **Free** plan.
2. Cloudflare scans existing records. Remove any conflicting A/CNAME entries.
3. Copy the two Cloudflare nameserver hostnames provided (e.g., `aisha.ns.cloudflare.com`).
4. At your registrar, replace existing nameservers with the two Cloudflare ones. NS delegation propagates in 15 minutes to 48 hours.

### Switching records to DNS-only (gray cloud)

Cloudflare defaults to proxying (orange cloud) for imported A/CNAME records. Disable it:

1. **DNS > Records** → edit the apex A record.
2. Click the orange cloud icon in **Proxy status** — it toggles to gray **DNS only**.
3. Save. Repeat for the `www` CNAME and `api` A record.

### Vercel apex domain — OpenTofu resources

Add the apex first; Vercel prompts you to add `www` and choose redirect direction (**www → apex**, 301). OpenTofu equivalent:

```hcl
resource "vercel_project_domain" "apex" {
  project_id = vercel_project.frontend.id
  domain     = "example.com"
}

resource "vercel_project_domain" "www" {
  project_id  = vercel_project.frontend.id
  domain      = "www.example.com"
  redirect    = "example.com"
  redirect_status_code = 301
}
```

### Cloudflare API token for OpenTofu

Create a token via **My Profile > API Tokens > Create Token** using the **Edit zone DNS** template scoped to `example.com`. Store as `CLOUDFLARE_API_TOKEN` in `<infra>/.env`. Provider: `cloudflare/cloudflare ~> 4.0`. All records use `proxied = false`:

> **(verify the provider major + resource names):** this pins `cloudflare/cloudflare ~> 4.0` and uses the `cloudflare_record` resource. Provider **v5 renamed the resource to `cloudflare_dns_record`** (and changed several attribute shapes). Confirm whether staying on v4 is a deliberate choice; if you adopt v5, rename `cloudflare_record` → `cloudflare_dns_record` (and `data.cloudflare_zone` usage) accordingly before `tofu apply`.

```hcl
resource "cloudflare_record" "apex" {
  zone_id = data.cloudflare_zone.main.id
  name    = "example.com"
  type    = "A"
  content = "<vercel-apex-ip>"
  proxied = false
}

resource "cloudflare_record" "api" {
  zone_id = data.cloudflare_zone.main.id
  name    = "api"
  type    = "A"
  content = oci_core_instance.app.public_ip
  proxied = false
}
```

---

## Vercel custom domain

### Adding apex + www

1. Project → **Settings > Domains** → **Add Domain** → enter `example.com` (apex first).
2. Copy the A record IP Vercel displays. When prompted, also add `www.example.com` and choose redirect direction **www → apex (301)**.
3. Create the DNS records in Cloudflare (DNS-only). Vercel verifies within minutes and shows **Valid Configuration**.

If the domain was previously used by another Vercel project, a `_vercel` TXT record verification is required. Add it in Cloudflare as DNS-only.

### Automatic TLS certificates and redirects

Once DNS verifies, Vercel automatically provisions Let's Encrypt certificates for `example.com` and `www.example.com` and keeps them renewed. No manual step is needed. Certificate status is visible in **Settings > Domains**.

Vercel enforces two redirects automatically:

- **HTTP → HTTPS**: port 80 requests for both apex and www redirect to HTTPS.
- **www → apex 301**: configured by the `www.example.com` domain entry's redirect setting.

The `vercel_project_domain` HCL pattern is shown in the Cloudflare section above (apex resource + www with `redirect` and `redirect_status_code = 301` in `infrastructure/vercel.tf`).

---

## OCI VM HTTPS — Caddy 2

### Installation

Install Caddy from the official package repository on Ubuntu 22.04 (ARM):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

The package installs Caddy as a systemd service (`caddy.service`) and creates `/etc/caddy/Caddyfile` as the default config location. Caddy's data directory (certificates, ACME state) is `/var/lib/caddy`.

### Standard Caddyfile

The webstack standard Caddyfile for the OCI VM:

```
{
  email admin@example.com
}

api.example.com {
  tls admin@example.com
  reverse_proxy localhost:8080
}
```

Replace `admin@example.com` with the operator email (used by Let's Encrypt / ZeroSSL for expiry notifications and account registration). Replace `api.example.com` with the actual API subdomain. The site-level `tls <email>` directive is redundant when the global `email` block is set, but spelling it out is the canonical form for the agent to recognise TLS configuration explicitly.

On first run, Caddy contacts Let's Encrypt via HTTP-01 challenge (port 80 must be open), stores the certificate in `/var/lib/caddy/.local/share/caddy/certificates/`, begins serving HTTPS on 443, and redirects HTTP automatically. It renews at ~2/3 of the 90-day lifetime and fails over to ZeroSSL automatically if Let's Encrypt is unreachable.

### Full Caddyfile with HSTS

The complete production Caddyfile with HSTS (see section below for preload caveats):

```
{
  email admin@example.com
}

api.example.com {
  tls admin@example.com
  reverse_proxy localhost:8080
  header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
}
```

The global `email` block sets the ACME account email for all site blocks. The `header` directive injects HSTS on all responses.

### Systemd service

Caddy is managed by `caddy.service`. Use `systemctl reload caddy` (not `restart`) after editing the Caddyfile — `reload` performs a graceful zero-downtime config swap.

```bash
sudo systemctl enable caddy   # start on boot
sudo systemctl reload caddy   # apply Caddyfile changes (zero downtime)
sudo journalctl -u caddy -f   # follow logs
```

### OCI security list / NSG ports

The OCI VM's Network Security Group must open inbound TCP ports **80** and **443** from `0.0.0.0/0`. Port 80 is required for Caddy's HTTP-01 ACME challenge. Port 443 serves HTTPS traffic. Caddy handles both; no other process should bind these ports.

Port 8080 (Spring Boot) must **not** be open to the internet. Caddy is the only entry point; inbound 8080 from `0.0.0.0/0` would bypass TLS entirely.

Cross-link: full NSG HCL and security list configuration are in `infrastructure/network-security.md`.

### Let's Encrypt rate limits

Relevant limits for a webstack single-domain project:

- **50 certificates per registered domain per 7 days** — essentially unreachable for a single project.
- **5 duplicate certificates per 7 days** — triggered if `/var/lib/caddy` is wiped and Caddy restarts repeatedly. Never delete the data directory during normal deploys.
- **5 failed validations per identifier per hour** — triggered if DNS has not propagated when Caddy first starts. Verify with `dig api.example.com @1.1.1.1` before starting Caddy against a new domain.

For development, add `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` in the global block (untrusted certs, much higher limits). ZeroSSL is Caddy's automatic fallback CA with its own independent limits.

---

## Why not Nginx/Traefik

**Nginx** requires certbot (or acme.sh) as a separate process, a cron job or systemd timer running `certbot renew` twice daily, a post-renewal reload hook, and manual intervention when the two drift apart. That is four moving parts for a problem Caddy solves with zero extra configuration. On a single VM the operational surface area of nginx + certbot exceeds the complexity of the application itself.

**Traefik** integrates ACME natively but is designed for dynamic service discovery in container orchestration environments (Docker labels, Kubernetes CRDs). Its configuration is split across static and dynamic files plus provider annotations — appropriate for a Kubernetes cluster, disproportionate for one Spring Boot process on one VM. webstack's OCI VM runs Spring Boot as a systemd service with no Docker in the production path; Caddy's static Caddyfile is the better fit.

---

## Force HTTPS + HSTS preload

### HTTP → HTTPS redirect

Caddy issues automatic 308 redirects from port 80 to port 443 for all managed domains. Vercel does the same for apex and www. No configuration is required on either side.

### HSTS header

Add HSTS via Caddy's `header` directive (shown in the full Caddyfile above). For Vercel-served domains, add the same header via `next.config.ts` `headers()` targeting `source: "/(.*)"`. The required values for preload submission:

- `max-age=63072000` — 2 years (minimum 1 year for preload).
- `includeSubDomains` — required for preload; applies HSTS to all subdomains.
- `preload` — signals intent to be included in the browser preload list.

### HSTS preload submission

The HSTS preload list is embedded in Chrome, Firefox, Safari, and Edge. Domains on the list are contacted only via HTTPS, even on the user's first ever visit — no HTTP request is ever made.

**Warning:** Preload is hard to reverse — removal takes months to propagate through browser stable releases. Do not submit until all subdomains under `example.com` serve valid HTTPS, `includeSubDomains` will remain true permanently, and the domain will stay HTTPS-only.

To submit: confirm the full HSTS header is served on `https://example.com`, then visit [hstspreload.org](https://hstspreload.org), enter the domain, verify eligibility, and click **Submit**. New entries take several months to reach stable Chrome.

For early-stage projects, set `max-age=63072000; includeSubDomains` without `preload` and add `preload` once the domain topology is stable.

---

## Renewal monitoring

### Caddy logs and metrics

Follow certificate events in the systemd journal:

```bash
sudo journalctl -u caddy -f | grep -i cert
```

Renewal occurs ~30 days before expiry (60 days into the 90-day Let's Encrypt lifetime). A successful renewal logs `"certificate obtained successfully"`.

Enable Prometheus metrics by adding `metrics` to the global block. The metrics endpoint binds to `localhost:2019` (Caddy's admin API). Key metric: `caddy_tls_certificates_expiry_seconds` — seconds until certificate expiry per hostname. Configure a Grafana alert when this value falls below 604,800 (7 days); Caddy's own renewal fires at 30 days, so a 7-day alert signals a renewal failure.

Scrape target for Prometheus:

```yaml
- job_name: caddy
  static_configs:
    - targets: ["localhost:2019"]
  metrics_path: /metrics
```

Cross-link: Prometheus + Grafana setup is in `infrastructure/observability-stack.md`.

### External certificate check

As an independent check, use UptimeRobot/Freshping or a weekly cron on a separate host to verify expiry via `openssl s_client -connect api.example.com:443 | openssl x509 -noout -enddate`. This is independent of Caddy's internal renewal state.

---

## Anti-patterns

**Manual certbot cron.** `certbot renew` in cron fails silently when cron is disabled, the reload hook breaks, or the ACME challenge fails. Caddy's built-in renewal retries for 30 days with no external dependencies.

**Cloudflare proxy (orange cloud) + Vercel apex simultaneously.** Cloudflare terminates TLS and re-originates to Vercel, intercepting the HTTP-01 ACME challenge and breaking certificate issuance. Vercel's HTTPS redirect then conflicts with Cloudflare Flexible SSL, producing `ERR_TOO_MANY_REDIRECTS`. Fix: switch apex and www to DNS-only (gray cloud).

**HSTS missing or short `max-age`.** Without HSTS, a downgrade attack intercepts the first HTTP request. `max-age=60` is meaningless. Use `max-age=63072000` (2 years). Without `includeSubDomains`, `api.example.com` is unprotected even when the apex has HSTS.

**Spring Boot port 8080 open to the internet.** Bypasses TLS entirely. All application traffic must flow through Caddy (443 → localhost:8080). Block 8080 in the OCI NSG.

**Wiping `/var/lib/caddy` on redeploy.** Forces re-issuance. Five re-issues of the same certificate in 7 days hits Let's Encrypt's duplicate certificate limit. Treat `/var/lib/caddy` as persistent state.

**Starting Caddy before DNS propagates.** HTTP-01 validation fails immediately. After 5 failures per hour, Let's Encrypt blocks attempts for an hour. Verify propagation first: `dig api.example.com @1.1.1.1`.

---

## Sources

- **Caddy Automatic HTTPS:** https://caddyserver.com/docs/automatic-https — _authoritative_
- **Caddyfile reference:** https://caddyserver.com/docs/caddyfile — _authoritative_
- **Vercel — Adding a custom domain:** https://vercel.com/docs/domains/working-with-domains/add-a-domain — _authoritative_
- **Cloudflare — Proxied vs DNS-only records:** https://developers.cloudflare.com/dns/manage-dns-records/reference/proxied-dns-records/ — _authoritative_
- **HSTS Preload List submission:** https://hstspreload.org/ — _community: hstspreload.org (Chrome security team)_
- **Let's Encrypt rate limits:** https://letsencrypt.org/docs/rate-limits/ — _authoritative_

Last verified: 2026-06-22 (Caddy 2.X / Cloudflare DNS / Vercel custom domains / Let's Encrypt + ZeroSSL).
