---
name: infra
description: Use when applying or modifying infrastructure (Vercel/Oracle/Supabase via Terraform). Calls security-auditor pre-flight, runs terraform plan, delegates analysis to terraform-plan-analyzer, requires explicit user confirmation before any apply/destroy. Updates manifest with infrastructure outputs.
---

# infra skill — Terraform IaC apply

You are running `/webstack:infra`. Apply or modify infrastructure based on `<project>-infrastructure/` Terraform files. Treat every apply as a first-time apply (confirm everything; never assume idempotency makes it safe).

## Required reads

- `docs/infrastructure/terraform-modules.md`
- `docs/infrastructure/vercel-setup.md`
- `docs/infrastructure/oracle-cloud-setup.md`
- `docs/infrastructure/supabase-setup.md`
- `docs/infrastructure/setup-guide.md`

## Pre-flight (P0)

1. Verify `<project_root>/.webstack/manifest.yaml` exists. Read project name and infrastructure repo path.
2. Verify `<infra-repo>/.env` exists (do NOT read its content; just check `[ -f .env ]`). If missing: stop, point user to SETUP.md.
3. Verify Terraform-prefixed env vars exported (Terraform reads `TF_VAR_*` automatically; `docs/infrastructure/setup-guide.md` Step 3 instructs the user to use this prefix). Check presence without revealing values:

   ```bash
   for v in TF_VAR_vercel_token TF_VAR_oci_tenancy_ocid TF_VAR_oci_user_ocid TF_VAR_oci_fingerprint TF_VAR_oci_private_key_path TF_VAR_oci_region TF_VAR_supabase_access_token TF_VAR_supabase_db_password; do
     bash -c "test -n \"\${$v:-}\"" || { echo "missing: $v"; exit 1; }
   done && echo "all TF_VAR_* present"
   ```

   If any var is missing: stop, point user to `<infra-repo>/SETUP.md` Step 3.
4. Verify terraform CLI: `terraform version`. Require ≥ 1.6.
5. Invoke `security-auditor` SubAgent with all 3 repos. Wait for report.
   - If Critical findings: stop. Show user, request resolution before proceeding.
6. Confirm with user: "Pre-flight OK. About to run `terraform plan`. Proceed?"

## Phase 1: terraform plan

```bash
cd <infra-repo>
terraform init -input=false -no-color | tee /tmp/tf-init.log
terraform plan -input=false -no-color -out=plan.tfplan | tee /tmp/tf-plan.log
```

If init fails (missing providers, network): show last 30 lines of log, stop.
If plan fails: same.

## Phase 2: Plan analysis

Invoke `terraform-plan-analyzer` SubAgent with `infra_repo_path` and `plan_path=<infra-repo>/plan.tfplan`. Receive structured report.

## Phase 3: User confirmation

Show user the analyzer report VERBATIM (do not summarize the High-risk section — it must surface fully).

Then ask, with explicit phrasing:

> "About to run `terraform apply`. Plan summary:
>
> - Create: A | Update: B | Replace: C | Destroy: D
>
> High-risk: <list — explicit destruction or data-loss risk>
>
> Type `apply` to proceed, `cancel` to abort."

Accept only literal `apply` (case-insensitive). Anything else = abort.

If High-risk count > 0 AND user types `apply`: re-confirm:

> "High-risk changes detected (data-loss possible). Final confirmation: type `I understand` to apply, anything else to abort."

## Phase 4: terraform apply

Only on confirmed:

```bash
cd <infra-repo>
terraform apply -input=false -no-color plan.tfplan 2>&1 | tee /tmp/tf-apply.log
```

If apply fails partway: surface last 50 lines, ask user how to proceed (rollback, re-apply after fix, manual).

On success:

```bash
terraform output -json > /tmp/tf-outputs.json
```

## Phase 5: manifest update + .env.local guidance

1. Read `/tmp/tf-outputs.json`. Update `<project_root>/.webstack/manifest.yaml` with output values that are NOT sensitive — the canonical non-sensitive output keys are `vercel_project_url`, `oracle_instance_public_ip`, `supabase_project_url` (declared in `infrastructure/outputs.tf` per `docs/infrastructure/terraform-modules.md` lines 163-176). Mirror those exact keys into `manifest.infrastructure.{vercel_project_url, oracle_instance_public_ip, supabase_project_url}` so `/webstack:deploy` pre-flight can read them. Sensitive outputs (`supabase_anon_key`, `database_url`, DB password) are NOT written to manifest — instead, instruct user how to retrieve via `terraform output -raw <name>` in their shell.
2. Generate `.env.local.template` updates for frontend repo (NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_API_URL, etc.) and backend repo (SUPABASE_DB_URL placeholder, etc.). Show user the diff; do not auto-commit.
3. Print:
   > Infrastructure applied. Outputs at `<infra-repo>/terraform.tfstate` (gitignored).
   > Sensitive values can be retrieved with: `terraform output -raw <name>`.
   > Update your frontend/backend `.env.local` files. Once done, you can deploy via `/webstack:deploy`.

## Escalation Protocol

If terraform plan/apply errors out with provider-specific issues you can't resolve from the log alone (e.g., Oracle quota, Vercel team mismatch): show error, stop, ask user.

## Style

- Always show plan analysis report before apply.
- Never echo, log, or output values that match sensitive variable names.
- Re-confirm for any High-risk action.
- Use `-no-color -input=false` on every terraform invocation.
