# Infrastructure Setup Guide

> Reference template for the `<infra>/SETUP.md` file emitted by `/webstack:init` P6. Walks the user through provider sign-up, token issuance, .env preparation, environment export, and the `/webstack:infra` invocation. The user's manual; webstack/Claude never reads token values.

## Overview

This guide takes a fresh machine from "no Vercel/Oracle/Supabase accounts" to "ready to run `/webstack:infra`." Each step is self-contained — complete one before moving to the next. **Claude Code does not read your tokens at any point**; the file containing them (`.env`) is excluded from AI reads via the project's `.claude/settings.local.json` deny rule. The user's shell and OpenTofu read the .env directly.

Time budget: 30-60 minutes for first-time provider sign-ups (the credit-card verification on Oracle Cloud is the slowest).

## Step 1: Sign up

Create accounts on each provider before issuing tokens. webstack assumes free tiers throughout.

- **Vercel** — https://vercel.com/signup. Continue with GitHub. Pick the **Hobby** plan.
- **Oracle Cloud** — https://cloud.oracle.com/free. Credit card required for identity verification (Always Free resources are never charged). Choose your **Home Region** carefully — it cannot change later. Recommendations: `ap-seoul-1` for Korea, `us-ashburn-1` for global.
- **Supabase** — https://supabase.com. Sign in with GitHub. Create an **organization** (free; holds your 2-project allowance).
- **GitHub** — required for the Vercel and Supabase OAuth flows. If you already have an account, you may still need a personal access token for the webstack marketplace publish flow in the future.

Make a note of the email address you used for each, and any organization IDs the providers display in the dashboard URL after sign-up.

## Step 2: Issue API tokens

You'll provision three tokens. Each goes into `.env` (Step 3); none are read by Claude.

### Vercel

1. Vercel dashboard → **Account Settings** → **Tokens** → **Create Token**.
2. Name: `webstack-iac`.
3. Scope: **Full Account**.
4. Expiration: 1 year.
5. Copy the token — it is shown **only once**. Save in a password manager as backup.

The token will be `VERCEL_TOKEN` in your .env.

### Oracle Cloud

1. Generate an API key locally:

   ```bash
   mkdir -p ~/.oci
   openssl genrsa -out ~/.oci/oci_api_key.pem 2048
   chmod 600 ~/.oci/oci_api_key.pem
   openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem
   cat ~/.oci/oci_api_key_public.pem
   ```

2. OCI Console → **Identity & Security** → **Users** → select your user → **API Keys** → **Add API Key** → **Paste Public Key** → paste the contents of `oci_api_key_public.pem`.
3. Note the **fingerprint** displayed.
4. From the user details page, copy your **user OCID**.
5. From **Tenancy** in the top-right menu, copy your **tenancy OCID**.
6. From the regions menu, identify your **home region** key (e.g., `ap-seoul-1`).

Your .env will need:

- `OCI_TENANCY_OCID`
- `OCI_USER_OCID`
- `OCI_FINGERPRINT`
- `OCI_PRIVATE_KEY_PATH=~/.oci/oci_api_key.pem`
- `OCI_REGION`

### Supabase

1. Supabase dashboard → **Account** (top-right avatar) → **Access Tokens** → **Generate New Token**.
2. Name: `webstack-iac`.
3. Copy and store. This is `SUPABASE_ACCESS_TOKEN` in your .env.

You will also need:

- `SUPABASE_ORGANIZATION_ID` — from the organization URL `https://supabase.com/dashboard/org/<id>`.
- `SUPABASE_DB_PASSWORD` — generate a strong password now (use a password manager); you will paste this into Terraform on the first apply, and Supabase will provision the database with it.

## Step 3: Fill .env

In your project's infrastructure repo:

```bash
cd <project>-infrastructure
cp .env.template .env
```

Open `.env` in an editor and paste in the values from Steps 1-2:

```text
# Vercel
TF_VAR_vercel_token=<paste>

# Oracle Cloud
TF_VAR_oci_tenancy_ocid=<paste>
TF_VAR_oci_user_ocid=<paste>
TF_VAR_oci_fingerprint=<paste>
TF_VAR_oci_private_key_path=/Users/<you>/.oci/oci_api_key.pem
TF_VAR_oci_region=ap-seoul-1
TF_VAR_oci_ssh_public_key_path=/Users/<you>/.ssh/id_ed25519.pub

# Supabase
TF_VAR_supabase_access_token=<paste>
TF_VAR_supabase_organization_id=<paste>
TF_VAR_supabase_db_password=<paste>
```

The `TF_VAR_` prefix lets OpenTofu pick up these values automatically when exported in the shell. (The prefix is preserved by OpenTofu for backwards compatibility with Terraform — same env var name in both tools.)

**Never commit this file.** webstack's `.gitignore` already excludes `.env`. Verify in Step 4.

## Step 4: Verify .gitignore

Confirm the file is excluded from git tracking:

```bash
cd <project>-infrastructure
git status
```

`.env` should **not** appear as either modified or untracked-to-be-added. If it does, re-check `.gitignore` for the `.env` line.

```bash
cat .gitignore | grep '^\.env$'
# expected output: .env
```

If `.gitignore` is missing `.env`, add it:

```bash
echo '.env' >> .gitignore
git add .gitignore
git commit -m "chore: gitignore .env"
```

Also confirm `.claude/settings.local.json` includes a deny rule for reading `.env`:

```bash
cat .claude/settings.local.json
```

The file should contain `permissions.deny` array entries that block AI Read of the file. Exact pattern depends on what `/webstack:init` P6 emitted — typical examples include `"Read(./.env)"`, `"Read(.env)"`, or globbed `"Read(**/.env)"`. This blocks Claude Code from reading the file in any session. (See the project's `hooks/hooks.json` PreToolUse rule as the second line of defence.)

## Step 5: Export environment variables

OpenTofu reads `TF_VAR_*` from the environment, not from .env directly. Source the file into your shell:

```bash
cd <project>-infrastructure
set -a && source .env && set +a
```

`set -a` causes every variable assignment to be exported until `set +a` turns it off. After this, `echo $TF_VAR_vercel_token` should print the value.

Repeat in any new shell session. The export does **not** persist across terminal windows. webstack's `/webstack:infra` skill will prompt you to re-source if it detects missing variables.

## Step 6: Run /webstack:infra

In a Claude Code session inside the same shell where Step 5 was executed:

```text
/webstack:infra
```

The skill runs `tofu init`, then `tofu plan -out=tfplan`, hands the plan output to the tofu-plan-analyzer SubAgent for review, presents the analysis to you, and waits for explicit approval before running `tofu apply tfplan`.

After apply, the skill surfaces the OpenTofu outputs (Vercel project URL, Oracle public IP, Supabase project URL, `database_url`, `database_direct_url`) and tells you how to populate the FE/BE repos' `.env.local` files. **You** copy the values from the output into those files; Claude does not write secrets.

## Troubleshooting

**`tofu: command not found`**

Install OpenTofu:

```bash
brew install opentofu            # macOS via Homebrew
# or download from https://opentofu.org/docs/intro/install/
```

Verify with `tofu -version`. Pin to 1.10+.

**`Error: No value for required variable`**

Re-export in your current shell:

```bash
cd <project>-infrastructure
set -a && source .env && set +a
```

Check with `env | grep ^TF_VAR_`. Each new terminal needs the export.

**`Error: ... permission denied: ./.env`**

This is expected for Claude Code reads. Your shell and OpenTofu should still be able to read it. Verify with `cat .env | head -1` in your terminal.

Provider authentication errors:

- Vercel: token revoked or expired → reissue in Step 2.
- Oracle: fingerprint mismatch → re-confirm public key was uploaded correctly; the fingerprint shown in OCI Console must match the one in .env.
- Supabase: token doesn't have project-create scope → reissue with default scopes.

**`Plan: 0 to add, 0 to change, 0 to destroy`**

Means OpenTofu thinks state matches reality. If you expect changes, the resource may already exist (manual creation in dashboard) and need to be imported via `tofu import`.

## Free tier monitoring

Each provider's dashboard exposes current usage. Recommended monthly check:

- **Vercel** — Account → Usage. Watch bandwidth and build minutes.
- **Oracle** — Cloud Console → Cost Analysis (filter Always Free SKUs). Watch OCPU and storage.
- **Supabase** — Project → Settings → Usage. Watch DB size, egress, MAU.

If approaching a limit:

- Vercel: upgrade to Pro ($20/mo) or split bandwidth-heavy assets to a CDN.
- Oracle: scale down OCPU, archive old block volumes, move object storage data to Archive tier.
- Supabase: archive cold tables (move to Storage), upgrade to Pro ($25/mo) for the project.

## Resetting credentials

If a token is exposed (committed accidentally, leaked in logs, included in a public message):

1. **Revoke immediately** at the provider:
   - Vercel: Account Settings → Tokens → Delete the compromised token.
   - Oracle: User → API Keys → Delete the compromised key. Generate a new one.
   - Supabase: Account → Access Tokens → Delete and regenerate.
2. **Rotate locally** by re-running Step 2 to issue a fresh token.
3. **Update .env** with the new value (Step 3).
4. **Re-export** in your shell (Step 5).
5. **Audit** the leak vector — was .env accidentally committed? `git log --all --full-history -- .env` shows any history. If yes, rewrite history with `git filter-repo` and force-push (this is destructive; coordinate with collaborators).

For Oracle: also rotate the API signing key file pair (Step 2 commands) — the public key in OCI Console must be replaced.

## Authentication (only if you opted in during init)

webstack does not bundle an authentication provider. If you answered **Yes** to the auth prompt during `/webstack:init`, the Spring backend already has `spring-boot-starter-security` on the classpath with a permissive default `SecurityFilterChain`. To turn that into real authentication:

1. Read `docs/recipes/spring-security-auth.md` (in the webstack plugin) for the recommended path: self-implemented Spring Security 7 with JWT (Nimbus) + BCrypt for password hashing, or OAuth2 social login.
2. Add an `auth` bounded context as a regular feature: `/webstack:feature auth`. The `feature-architect` SubAgent will scaffold a `User` aggregate, `LoginUseCase`, `RegisterUseCase`, etc.
3. Tighten the `SecurityFilterChain` to require authentication on protected endpoints; expose `/api/auth/login`, `/api/auth/register` as the only `permitAll` paths.

If you answered **No** to the auth prompt during init, this section does not apply — the project starts and stays without Spring Security on the classpath. You can switch later by adding `spring-boot-starter-security` to `build.gradle.kts` and following the same recipe.

<!-- BEGIN observability — copy if optional_integrations.observability=true -->

## Observability setup

See `docs/recipes/observability-setup.md` for the full walkthrough.

Required actions for this project:

1. Sign up for Sentry → copy DSN.
2. Sign up for Grafana Cloud Free → copy OTLP endpoint URL + token.
3. Sign up for UptimeRobot → register monitor URL.
4. Add `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` to `.env`.

<!-- END observability -->

<!-- BEGIN i18n — copy if optional_integrations.i18n=true -->

## i18n setup

See `docs/recipes/i18n-setup.md`. No external signup required — only library install + `[locale]` segment scaffolding.

<!-- END i18n -->

<!-- BEGIN renovate — copy if optional_integrations.renovate=true -->

## Renovate setup

See `docs/recipes/renovate-setup.md`.

Required action: install the Renovate GitHub App on all 3 repos (`<project>-frontend`, `<project>-backend`, `<project>-infrastructure`).

<!-- END renovate -->

<!-- BEGIN release_management — copy if optional_integrations.release_management=true -->

## Release management setup

See `docs/recipes/release-management-setup.md`. Recommended to activate after first production deploy, not at init time.

<!-- END release_management -->

## Sources

- Vercel environment variables: https://vercel.com/docs/projects/environment-variables
- OCI API signing keys: https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm
- OpenTofu install: https://opentofu.org/docs/intro/install/

Last verified: 2026-04-27.
