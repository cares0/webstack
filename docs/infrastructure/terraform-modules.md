# OpenTofu Module Conventions

> Reference for the infra skill and tofu-plan-analyzer SubAgent. Covers OpenTofu basics in webstack, the infrastructure repo layout, sensitive variables, state management, plan output, apply/destroy safety, and the outputs that wire into the FE/BE repos.

## Why OpenTofu

webstack uses **OpenTofu** as its IaC engine. OpenTofu is the open-source fork of Terraform — accepted into the CNCF Sandbox in April 2025 — that preserves HCL syntax, plan/apply semantics, the provider ecosystem, the `.terraform.lock.hcl` lockfile, the `terraform.tfstate` file format, and the `TF_VAR_*` environment-variable contract. Switching from Terraform is a CLI rename: `terraform` → `tofu`. Every existing Terraform Registry provider (`vercel/vercel`, `oracle/oci`, `supabase/supabase`) is mirrored to `registry.opentofu.org` and resolves transparently.

webstack picks OpenTofu over Terraform because:

- **License posture** — OpenTofu remains under MPL 2.0; HashiCorp's Terraform shifted to BSL 1.1 in 2023, which restricts commercial offerings and adds licensing review burden for downstream tooling.
- **State encryption** — OpenTofu 1.7+ ships native, declarative encryption for the state file. Terraform's encryption requires Terraform Cloud (HCP).
- **Open governance** — CNCF-hosted technical steering committee. Direction is community-set, not vendor-set.
- **Drop-in compatibility** — HCL configurations, providers, plan binaries, and state files all interoperate with the Terraform 1.x line, so future migration in either direction is straightforward.

The CNCF Sandbox tier means OpenTofu is past prototype but not yet at Incubating maturity. webstack relies on the v1.10+ stable line for production infrastructure. The lock-step compatibility with Terraform is a fallback: if OpenTofu ever ceases to meet your needs, switch the CLI back to `terraform` without changing any HCL.

## OpenTofu basics in webstack

OpenTofu declares **infrastructure as code** in HCL, with a planner that diffs the desired state against the live state and applies the diff. webstack uses OpenTofu for Vercel (frontend deploy target), Oracle Cloud (backend host), and Supabase (managed Postgres only — Auth/Storage/Realtime/Edge Functions are not used) so every environment is reproducible from the repo.

The shape of webstack's OpenTofu usage:

- **Three providers, one repo.** `vercel/vercel`, `oracle/oci`, `supabase/supabase` all live in the same `<project>-infrastructure` repo.
- **No modules in v1.** Resources are declared at the root. Module abstraction is added in v2 once patterns stabilize across multiple webstack projects.
- **Remote state in v1.** State lives in an S3-compatible backend on OCI Object Storage (versioned, native conditional-write locking) — see [State](#state) and `docs/infrastructure/backup-and-recovery.md` (Layer 2). A purely local `terraform.tfstate` is only a bootstrap convenience before the backend is configured.
- **Manual approval per apply.** webstack never auto-applies. The infra skill runs `tofu plan`, the user reviews via `tofu-plan-analyzer`, then explicitly approves `tofu apply`.

This trade-off — local state, manual approve, no modules — keeps v1 understandable end-to-end for someone learning IaC alongside webstack. v2 adds the team-scale features.

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
├── .terraform.lock.hcl         # provider lockfile (committed) — name preserved
└── .claude/
    └── settings.local.json     # Claude Code deny rules: .env Read blocked
```

Notes:

- `main.tf` holds only the `terraform { required_providers { } }` block (HCL block name preserved by OpenTofu) and the `provider "..." { }` declarations. No resources.
- Resource files are split per provider to keep blast radius and review diffs scoped.
- `.env.template` lists every variable name with empty values; the user copies to `.env` and fills in. The file is the contract between `/webstack:init` and the user.
- The `.claude/settings.local.json` deny rule is an explicit guardrail against an LLM session reading the secrets file. The user's shell can still source it.
- The `.terraform/` provider cache directory and `.terraform.lock.hcl` lockfile retain Terraform-compatible names so the same repo opens cleanly in either CLI.

## Sensitive variables

Mark every secret-bearing variable `sensitive = true`. OpenTofu redacts these from `plan` and `apply` output and from the state file's text rendering (the actual value is still in state; treat the state file itself as a secret, or enable OpenTofu state encryption — see "State" below).

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
  description = "OCI user OCID for OpenTofu"
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

Values come from environment variables prefixed `TF_VAR_` (e.g., `TF_VAR_vercel_token=...`). The user's `set -a; source .env; set +a` workflow exports them for the shell session that runs `tofu`.

`sensitive = true` does **not** encrypt anything; it is a redaction signal. The actual secrecy is from the .env workflow, the gitignore, and the Claude Code deny rules. For state-at-rest encryption, see the next section.

## State

State holds the mapping between declared resources and live cloud resources. webstack v1 stores state in a **remote S3-compatible backend on OCI Object Storage** (versioned bucket + native conditional-write locking), so the state survives a lost laptop and every `apply` leaves a recoverable prior version. The full `backend "s3" { … }` block (endpoints, `use_lockfile`, the `skip_*` flags for OCI's S3-compat API, and the OCI Customer Secret Key pair) is documented once in `docs/infrastructure/backup-and-recovery.md` (Layer 2 — IaC state); `main.tf`'s `terraform { backend "s3" { … } }` points at the `webstack-tofu-state` bucket. A purely local `terraform.tfstate` is only a bootstrap convenience before the backend is wired (`tofu init -migrate-state` moves an existing local file into the bucket).

Implications:

- **Shared, recoverable state.** The versioned bucket plus `use_lockfile = true` (conditional-write locking) means the state is backed up automatically and concurrent applies are serialized — no DynamoDB and no manual copy-to-a-drive ritual.
- **Secrets in state.** Even sensitive-marked variables end up in the state in plaintext for resources that capture them (Vercel env var values, Supabase passwords). OCI Object Storage encrypts at rest by default; add OpenTofu state encryption (below) as a second layer so the plaintext is also encrypted before it leaves the machine.

OpenTofu state encryption (1.7+) lets the state file be encrypted at rest with a key derived from a passphrase or fetched from a KMS:

```hcl
terraform {
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = var.tofu_state_passphrase
    }
    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }
    state {
      method = method.aes_gcm.default
    }
    plan {
      method = method.aes_gcm.default
    }
  }
}
```

Add `TF_VAR_tofu_state_passphrase` to `.env` if enabling. webstack v1 leaves encryption opt-in on top of the remote backend's at-rest encryption; the remote OCI backend + .env discipline is the baseline defense, OpenTofu state encryption is the second layer. webstack v2 makes state encryption mandatory.

## tofu plan output

Plan output is the contract between OpenTofu and the tofu-plan-analyzer SubAgent. Always run plan first, save to a file, and pipe through `tofu show -json` for the analyzer:

```bash
tofu plan -input=false -no-color -out=tfplan
tofu show -json tfplan > tfplan.json
```

The JSON shape (`{ planned_changes, resource_changes, configuration }`) lets the analyzer surface:

- Resources being created, updated, or destroyed.
- Sensitive value placeholders ((sensitive value)) that will be applied.
- Free-tier limit checks (e.g., counting `oci_core_instance` and summing OCPU).
- Drift between declared config and live state.

The analyzer SubAgent reads `tfplan.json` and produces a human-readable summary the user reviews before approving apply. Plan output **never** echoes secret values — `sensitive = true` ensures the JSON renders `"sensitive_values": true` for those fields.

## Apply safety

webstack convention for `tofu apply`:

1. `tofu plan -out=tfplan` saves a binary plan.
2. tofu-plan-analyzer reads `tfplan.json` and surfaces changes.
3. User reviews the summary, explicitly types "apply" or equivalent.
4. `tofu apply -input=false -no-color tfplan` applies the saved plan (no re-planning).

Flags:

- `-input=false` — fail on missing variables instead of prompting (CI-style).
- `-no-color` — clean output for log capture and analyzer parsing.
- Saved plan file in step 4 — guarantees the user approves what gets applied (no last-minute drift).

Auto-apply (CI on push) is explicitly **not** the webstack default. Manual approval is the safety mechanism for v1.

## Destroy safety

`tofu destroy` removes all managed resources. webstack's infra skill **does not invoke destroy** unless the user explicitly requests it with destroy semantics in their message. Even then:

1. The user states the intent ("tear down the staging Vercel project and the Oracle VM").
2. infra skill scopes the destroy with `-target=...` to the specific resources, not the whole config.
3. infra skill runs `tofu plan -destroy -out=destroyplan` first.
4. tofu-plan-analyzer surfaces what will be deleted.
5. User confirms.
6. `tofu apply destroyplan`.

Full-stack destroys (`tofu destroy` with no target) require a second-step confirmation explicitly mentioning the project name. Cloud resources can be expensive to recover; data in Supabase is the highest-stakes — destroying a Supabase project deletes the database irrevocably (free tier has no PITR).

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
  description = "Supabase project URL (https://<ref>.supabase.co) — Console link for the operator. The app does not call this URL."
  value       = "https://${supabase_project.main.id}.supabase.co"
}

# Do NOT string-build the pooler host as `aws-0-<region>...` — the pooler hostname has a
# dynamic prefix (aws-0-, aws-1-, …) that varies by project/region/provider. Read the host
# from the project's connection-string attribute exposed by the supabase data source instead
# of constructing it. (verify the exact attribute name against your pinned supabase/supabase
# provider — e.g. a `supabase_pooler` data source or the project's connection-string output.)
data "supabase_pooler" "main" {
  project_ref = supabase_project.main.id
}

output "database_url" {
  description = "Pooled Postgres connection string for the Spring app"
  # transaction-mode pooled URL (port 6543), host taken from the provider, not hand-built
  value       = data.supabase_pooler.main.url["transaction"] # (verify attribute shape against the pinned provider)
  sensitive   = true
}

output "database_direct_url" {
  description = "Direct Postgres connection string for Flyway migrations"
  value       = data.supabase_pooler.main.url["session"]     # or the project's direct (5432) connection string (verify attribute)
  sensitive   = true
}
```

webstack uses Supabase strictly as a managed Postgres host (see `docs/infrastructure/supabase-setup.md`). The outputs are the two connection strings the backend needs — no anon keys, no service-role keys, no JWT secrets, because Auth/Storage/Realtime/Edge Functions are not used. If the pinned provider version does not expose a pooler/connection-string attribute, copy the pooled and direct strings from the Supabase dashboard (Settings → Database) into `TF_VAR_*` and surface those instead — never reconstruct the `aws-0-` host.

After apply, `tofu output -json` produces a JSON object the infra skill reads to update FE/BE repos' `.env.local.template` (placeholder names) and to generate the user instructions for their `.env.local` (actual values, never written to disk by Claude). The user copies the values from `tofu output` (or from the post-apply summary) into the FE/BE `.env.local` files.

In webstack `/webstack:infra` P5: outputs are read, FE/BE `.env.local.template` files are confirmed to contain the expected variable names, and the user is instructed how to populate `.env.local` with the actual values.

## webstack convention

- **One infrastructure repo per project.** Sibling to FE and BE repos: `<project>-frontend/`, `<project>-backend/`, `<project>-infrastructure/`.
- **Remote state in v1.** S3-compatible backend on OCI Object Storage (versioned + `use_lockfile` locking), configured in `main.tf` and detailed in `backup-and-recovery.md` (Layer 2). Any stray local `terraform.tfstate` stays gitignored; opt-in OpenTofu state encryption adds a second layer.
- **Plan-then-apply, always.** No `tofu apply` without an explicit prior `plan` reviewed via tofu-plan-analyzer.
- **Sensitive markers on every secret variable.** Even if the secret already comes from .env, the marker keeps it out of plan output.
- **Provider lockfile committed.** `.terraform.lock.hcl` (Terraform-compatible name) is checked in for reproducibility across machines and across CLI choice.
- **No destroy in default flows.** Destroy is opt-in, scoped to specific targets, and confirmed explicitly.
- **Outputs always include the FE/BE-relevant values.** The infra skill assumes `vercel_project_url`, `oracle_instance_public_ip`, `supabase_project_url`, `database_url`, `database_direct_url` exist as outputs.

## Switching back to Terraform (escape hatch)

Because every artifact (HCL, providers, plan binary, state file, lockfile) is byte-compatible with Terraform 1.x, the switch is mechanical:

```bash
brew install terraform   # or download from https://developer.hashicorp.com/terraform/install
terraform init           # uses the same providers from .terraform.lock.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

The webstack convention writes commands as `tofu` because that is the supported default. If a user prefers Terraform, replace `tofu` with `terraform` in any invocation; nothing else changes.

## Sources

- OpenTofu docs: https://opentofu.org/docs/
- OpenTofu CLI reference: https://opentofu.org/docs/cli/commands/
- OpenTofu Registry (provider lookup): https://search.opentofu.org/
- OpenTofu state encryption: https://opentofu.org/docs/language/state/encryption/
- CNCF project page: https://www.cncf.io/projects/opentofu/
- Sensitive variables (HCL — same shape across both CLIs): https://opentofu.org/docs/language/values/variables/#suppressing-values-in-cli-output

Last verified: 2026-06-22 (OpenTofu 1.11.6 stable / 1.12.0-beta1; remote OCI S3 state backend is the v1 default).
