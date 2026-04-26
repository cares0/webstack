# Vercel Setup

> Reference for the infra skill, terraform-plan-analyzer, and design-system-architect. Covers Vercel sign-up, project configuration, environment variables, Terraform automation, custom domains, and free-tier limits.

## Why Vercel for FE

Vercel is the company behind Next.js and provides first-class hosting for it. Builds use Next.js's native build pipeline; routing, ISR, image optimization, and Edge Functions work without configuration. Static assets serve from Vercel's global edge network with automatic cache invalidation per deploy. For an MVP-stage Next.js app, the Hobby tier is usually sufficient and free.

webstack's frontend-first deployment story (Next.js + Vercel for FE; backend on Oracle Cloud Compute; DB on Supabase) leans on this match. Other PaaS options (Netlify, Cloudflare Pages, AWS Amplify) work for static Next.js but lack first-party support for the App Router's Server Components and Server Actions.

## Free tier limits

The Hobby plan is free with these limits as of 2025:

- **100 GB outbound bandwidth per month.**
- **Unlimited requests** (Edge requests + Function invocations).
- **1 concurrent build** at a time; subsequent pushes queue.
- **6,000 build minutes per month** total.
- **No commercial use.** Hobby projects must be personal/non-commercial. Paid Pro tier is required for any commercial product.
- **100 deployments per day** per account.
- **No team members on Hobby**; collaboration requires Pro/Enterprise.

webstack assumes Hobby for the personal/learning/MVP use case and warns when usage approaches limits. A commercial product moving to Pro requires only re-confirming the plan in the Vercel dashboard; the project itself does not change.

## Sign-up & GitHub link

1. Visit https://vercel.com/signup.
2. Choose **Continue with GitHub** (or GitLab/Bitbucket; webstack recommends GitHub for the marketplace publish flow).
3. Authorize the Vercel app on the GitHub account that owns the project repos.
4. Pick the **Hobby** plan during onboarding. (Pro upgrade is one click later.)

webstack's `/webstack:init` outputs the sign-up URL when `VERCEL_TOKEN` is missing from the environment. The user signs up out-of-band, then proceeds to token issuance.

## Project import

To import a frontend repo as a Vercel project:

1. Vercel dashboard → **Add New** → **Project**.
2. Select the GitHub repo (must be in the previously authorized account).
3. Confirm the framework preset — Vercel auto-detects **Next.js** from `package.json` and `next.config.*`.
4. Set the **Root Directory** if the Next.js app is in a sub-folder (rare in webstack since each app gets its own repo).
5. Click **Deploy**.

The first deploy completes in 1-3 minutes. Subsequent deploys reuse cached node_modules and the Next.js build cache.

In webstack, project import is automated via `terraform-provider-vercel` (see below); the manual UI flow is the fallback for non-Terraform users.

## Environment variables

Vercel exposes environment variables to the build and runtime via three scopes:

- **Production** — used on builds against the production branch (default `main`).
- **Preview** — used for pull request preview deploys and non-production branches.
- **Development** — pulled by `vercel env pull` for `vercel dev` local runs.

Each variable can be marked **Sensitive** (encrypted, write-only after creation; cannot be read back from the UI). Use Sensitive for any token, key, or secret. Public-facing values (analytics IDs, the public Supabase URL) can stay non-sensitive.

`NEXT_PUBLIC_*` variables are inlined into the client bundle at build time. Anything in this prefix is **public**; never put secrets here. Server-only secrets (the backend API URL, database credentials, service-role keys) use any other variable name and are read only at runtime by Server Components, Route Handlers, or Server Actions.

## Token issuance

To allow Terraform / CI to manage Vercel resources:

1. Vercel dashboard → **Account Settings** → **Tokens**.
2. Click **Create Token**.
3. Name: `webstack-iac` (or similar — the name is for your records).
4. Scope: **Full Account** for v1; webstack v2 will use scope-limited tokens once the provider supports them per-project.
5. Expiration: 1 year (renew annually).
6. Copy the token — it is shown only once.

The user pastes the token into `<infra>/.env` as `VERCEL_TOKEN=...`. The .env is gitignored and excluded from Claude Code reads via `.claude/settings.local.json` deny rules; the user exports it into the shell before invoking `/webstack:infra`.

## terraform-provider-vercel

The official `vercel/vercel` provider exposes the platform as Terraform resources.

```hcl
terraform {
  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "~> 2.0"
    }
  }
}

provider "vercel" {
  api_token = var.vercel_token
}

resource "vercel_project" "frontend" {
  name      = "example-app-frontend"
  framework = "nextjs"
  git_repository = {
    type              = "github"
    repo              = "your-org/example-app-frontend"
    production_branch = "main"
  }
  serverless_function_region = "icn1" # Seoul; change per geography
  build_command              = "next build"
}

resource "vercel_project_environment_variable" "api_url" {
  project_id = vercel_project.frontend.id
  key        = "NEXT_PUBLIC_API_URL"
  value      = var.public_api_url
  target     = ["production", "preview"]
}

resource "vercel_project_environment_variable" "supabase_anon" {
  project_id = vercel_project.frontend.id
  key        = "NEXT_PUBLIC_SUPABASE_ANON_KEY"
  value      = var.supabase_anon_key
  target     = ["production", "preview", "development"]
  sensitive  = true
}

resource "vercel_project_domain" "primary" {
  project_id = vercel_project.frontend.id
  domain     = "example.com"
}
```

Common resources:

- `vercel_project` — the project itself; framework, build settings, git linkage.
- `vercel_project_environment_variable` — env vars per scope and per sensitivity.
- `vercel_project_domain` — assigns a custom domain.
- `vercel_deployment` — triggers a deploy from a specific git ref (used by webstack only when bypassing the auto-deploy hook).
- `vercel_team` / `vercel_team_member` — Pro+ only.

## Custom domain

Vercel Hobby supports unlimited custom domains. Steps:

1. Add the domain via `vercel_project_domain` (or the dashboard's **Domains** tab).
2. Vercel returns the required DNS records — typically a CNAME for `www` and an A record for the apex.
3. Configure DNS at the registrar (Cloudflare, Route53, Google Domains, etc.).
4. Vercel issues a Let's Encrypt TLS certificate automatically once DNS verifies.

For DNS managed in Cloudflare, set the records to **Proxy: DNS only** (gray cloud) or use Cloudflare's "Full (strict)" SSL with a Cloudflare-issued cert; orange-cloud proxying breaks Vercel's automatic TLS.

## Deploy webhook

Project import wires a Git hook automatically: `git push origin main` triggers a production deploy; pushing to any other branch creates a preview deploy with a unique URL like `example-app-frontend-git-feat-foo-org.vercel.app`. PR comments on GitHub include the preview URL.

For non-git triggers (cron, manual deploys), Vercel exposes per-project **Deploy Hooks** under **Project Settings** → **Git**. Posting any payload (including empty) to the hook URL triggers a deploy.

In webstack, the convention is `git push origin main` is the deploy command. `/webstack:deploy` runs nothing more than the push; Vercel takes over.

## webstack convention

- **Provider config in `infrastructure/main.tf`.** Version pinned (`~> 2.0`); token bound to `var.vercel_token`.
- **Project resource in `infrastructure/vercel.tf`.** One resource per Vercel project; webstack creates one project per frontend repo.
- **Env vars in same file.** `NEXT_PUBLIC_*` values flow from outputs of other Terraform resources (Supabase URL, backend API URL); secrets are passed via sensitive variables from `.env`.
- **Deploy via git push.** No `vercel_deployment` resources in webstack — preserve the auto-deploy hook semantics.
- **Free-tier monitoring.** webstack does not enforce usage caps; the user reviews monthly. The infra skill flags when `vercel_project` count or estimated bandwidth (from build metadata) approaches Hobby limits.

## Sources

- Vercel docs: https://vercel.com/docs
- terraform-provider-vercel: https://registry.terraform.io/providers/vercel/vercel/latest/docs
- Vercel pricing & limits: https://vercel.com/docs/limits
- Vercel environment variables: https://vercel.com/docs/projects/environment-variables
