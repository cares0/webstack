# Terraform Module Conventions

> Reference for the infra skill and terraform-plan-analyzer SubAgent. Covers Terraform basics in webstack, the infrastructure repo layout, sensitive variables, state management, plan output, apply/destroy safety, and the outputs that wire into the FE/BE repos.

## Terraform basics in webstack

Terraform declares **infrastructure as code** in HCL, with a planner that diffs the desired state against the live state and applies the diff. webstack uses Terraform for Vercel (frontend deploy target), Oracle Cloud (backend host), and Supabase (database + auth) so every environment is reproducible from the repo.

The shape of webstack's Terraform usage:

- **Three providers, one repo.** `vercel/vercel`, `oracle/oci`, `supabase/supabase` all live in the same `<project>-infrastructure` repo.
- **No Terraform modules in v1.** Resources are declared at the root. Module abstraction is added in v2 once patterns stabilize across multiple webstack projects.
- **Local state in v1.** `terraform.tfstate` lives next to the .tf files, gitignored. v2 introduces a remote backend (Supabase Postgres or S3-compatible).
- **Manual approval per apply.** webstack never auto-applies. The infra skill runs `terraform plan`, the user reviews, then explicitly approves `terraform apply`.

This trade-off — local state, manual approve, no modules — keeps v1 understandable end-to-end for someone learning Terraform alongside webstack. v2 adds the team-scale features.

## webstack infrastructure repo layout

```text
<project>-infrastructure/
├── main.tf                     # provider versions, backend config
├── variables.tf                # input variables (all sensitive token vars marked)
├── outputs.tf                  # surface URLs, IDs to wire into FE/BE .env
├── vercel.tf                   # vercel resources (project, env vars, domain)
├── oracle.tf                   # oracle resources (vcn, subnet, instance)
├── supabase.tf                 # supabase resources (project, branches)
├── cloud-init.yaml             # OCI cloud-init script
├── .env.template               # placeholder names, no values
├── .env                        # gitignored; user fills with actual tokens
├── .gitignore                  # .env, .terraform/, *.tfstate*, tfplan
├── .terraform.lock.hcl         # provider lockfile (committed)
└── .claude/
    └── settings.local.json     # Claude Code deny rules: .env Read blocked
```

Notes:

- `main.tf` holds only the `terraform { required_providers { } }` block and the `provider "..." { }` declarations. No resources.
- Resource files are split per provider to keep blast radius and review diffs scoped.
- `.env.template` lists every variable name with empty values; the user copies to `.env` and fills in. The file is the contract between `/webstack:init` and the user.
- The `.claude/settings.local.json` deny rule is an explicit guardrail against an LLM session reading the secrets file. The user's shell can still source it.

## Sensitive variables

Mark every secret-bearing variable `sensitive = true`. Terraform redacts these from `plan` and `apply` output and from the state file's text rendering (the actual value is still in state; treat the state file itself as a secret).

```hcl
variable "vercel_token" {
  description = "Vercel API token (https://vercel.com/account/tokens)"
  type        = string
  sensitive   = true
}

variable "supabase_access_token" {
  description = "Supabase personal access token"
  type        = string
  sensitive   = true
}

variable "supabase_db_password" {
  description = "Database password for the Supabase project"
  type        = string
  sensitive   = true
}

variable "oci_tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
}

variable "oci_user_ocid" {
  description = "OCI user OCID for Terraform"
  type        = string
}

variable "oci_fingerprint" {
  description = "OCI API key fingerprint"
  type        = string
  sensitive   = true
}

variable "oci_private_key_path" {
  description = "Path to the OCI API signing private key (PEM)"
  type        = string
}

variable "oci_region" {
  description = "OCI home region (e.g., ap-seoul-1)"
  type        = string
}

variable "oci_compartment_id" {
  description = "OCI compartment OCID for webstack resources (defaults to root tenancy when set equal to oci_tenancy_ocid)"
  type        = string
}

variable "oci_ssh_public_key_path" {
  description = "Path to the SSH public key injected into the OCI VM for webstack:deploy SCP"
  type        = string
}
```

Values come from environment variables prefixed `TF_VAR_` (e.g., `TF_VAR_vercel_token=...`). The user's `set -a; source .env; set +a` workflow exports them for the shell session that runs `terraform`.

`sensitive = true` does **not** encrypt anything; it is a redaction signal. The actual secrecy is from the .env workflow, the gitignore, and the Claude Code deny rules.

## State

Terraform state holds the mapping between declared resources and live cloud resources. webstack v1 uses **local state** (`terraform.tfstate` in the repo root, gitignored).

Implications:

- **Single operator.** Only one person/machine can run `terraform apply` at a time. State conflicts are absent because the file lives on one disk.
- **Backups are user responsibility.** The state file should be backed up (e.g., periodic copy to a personal cloud drive). Losing it means re-importing or destroying-and-recreating.
- **Secrets in state.** Even sensitive-marked variables end up in `terraform.tfstate` in plaintext for resources that capture them (Vercel env var values, Supabase keys). Treat the state file like the .env.

webstack v2 introduces a **remote backend** (Supabase Postgres state backend or an S3-compatible store) plus state encryption. Out of scope for v1.

## terraform plan output

Plan output is the contract between Terraform and the terraform-plan-analyzer SubAgent. Always run plan first, save to a file, and pipe through `terraform show -json` for the analyzer:

```bash
terraform plan -input=false -no-color -out=tfplan
terraform show -json tfplan > tfplan.json
```

The JSON shape (`{ planned_changes, resource_changes, configuration }`) lets the analyzer surface:

- Resources being created, updated, or destroyed.
- Sensitive value placeholders ((sensitive value)) that will be applied.
- Free-tier limit checks (e.g., counting `oci_core_instance` and summing OCPU).
- Drift between declared config and live state.

The analyzer SubAgent reads `tfplan.json` and produces a human-readable summary the user reviews before approving apply. Plan output **never** echoes secret values — `sensitive = true` ensures the JSON renders `"sensitive_values": true` for those fields.

## Apply safety

webstack convention for `terraform apply`:

1. `terraform plan -out=tfplan` saves a binary plan.
2. terraform-plan-analyzer reads `tfplan.json` and surfaces changes.
3. User reviews the summary, explicitly types "apply" or equivalent.
4. `terraform apply -input=false -no-color tfplan` applies the saved plan (no re-planning).

Flags:

- `-input=false` — fail on missing variables instead of prompting (CI-style).
- `-no-color` — clean output for log capture and analyzer parsing.
- Saved plan file in step 4 — guarantees the user approves what gets applied (no last-minute drift).

Auto-apply (CI on push) is explicitly **not** the webstack default. Manual approval is the safety mechanism for v1.

## Destroy safety

`terraform destroy` removes all managed resources. webstack's infra skill **does not invoke destroy** unless the user explicitly requests it with destroy semantics in their message. Even then:

1. The user states the intent ("tear down the staging Vercel project and the Oracle VM").
2. infra skill scopes the destroy with `-target=...` to the specific resources, not the whole config.
3. infra skill runs `terraform plan -destroy -out=destroyplan` first.
4. terraform-plan-analyzer surfaces what will be deleted.
5. User confirms.
6. `terraform apply destroyplan`.

Full-stack destroys (`terraform destroy` with no target) require a second-step confirmation explicitly mentioning the project name. Cloud resources can be expensive to recover; data in Supabase is the highest-stakes — destroying a Supabase project deletes the database irrevocably (free tier has no PITR).

## Outputs to consume

`outputs.tf` exposes the values FE/BE need:

```hcl
output "vercel_project_url" {
  description = "Production URL of the Vercel project"
  value       = "https://${vercel_project.frontend.name}.vercel.app"
}

output "oracle_instance_public_ip" {
  description = "Public IPv4 of the backend Oracle Cloud VM"
  value       = oci_core_instance.app.public_ip
}

output "supabase_project_url" {
  description = "Supabase project URL (https://<ref>.supabase.co)"
  value       = "https://${supabase_project.main.id}.supabase.co"
}

output "supabase_anon_key" {
  description = "Supabase anon key for client-side use"
  value       = supabase_project.main.anon_key
  sensitive   = true
}

output "database_url" {
  description = "Pooled Postgres connection string for Spring app"
  value       = "postgresql://postgres.${supabase_project.main.id}:${var.supabase_db_password}@aws-0-${supabase_project.main.region}.pooler.supabase.com:6543/postgres"
  sensitive   = true
}
```

After apply, `terraform output -json` produces a JSON object the infra skill reads to update FE/BE repos' `.env.local.template` (placeholder names) and to generate the user instructions for their `.env.local` (actual values, never written to disk by Claude). The user copies the values from `terraform output` (or from the post-apply summary) into the FE/BE `.env.local` files.

In webstack `/webstack:infra` P4: outputs are read, FE/BE `.env.local.template` files are confirmed to contain the expected variable names, and the user is instructed how to populate `.env.local` with the actual values.

## webstack convention

- **One infrastructure repo per project.** Sibling to FE and BE repos: `<project>-frontend/`, `<project>-backend/`, `<project>-infrastructure/`.
- **Local state in v1.** `terraform.tfstate` gitignored. Daily user backup recommended.
- **Plan-then-apply, always.** No `terraform apply` without an explicit prior `plan` reviewed via terraform-plan-analyzer.
- **Sensitive markers on every secret variable.** Even if the secret already comes from .env, the marker keeps it out of plan output.
- **Provider lockfile committed.** `.terraform.lock.hcl` is checked in for reproducibility across machines.
- **No destroy in default flows.** Destroy is opt-in, scoped to specific targets, and confirmed explicitly.
- **Outputs always include the FE/BE-relevant values.** The infra skill assumes `vercel_project_url`, `oracle_instance_public_ip`, `supabase_project_url`, `supabase_anon_key`, `database_url` exist as outputs.

## Sources

- Terraform docs: https://developer.hashicorp.com/terraform/docs
- Terraform CLI plan/apply: https://developer.hashicorp.com/terraform/cli/commands/plan
- Sensitive variables: https://developer.hashicorp.com/terraform/language/values/variables#suppressing-values-in-cli-output
- State file: https://developer.hashicorp.com/terraform/language/state
