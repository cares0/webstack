# Scenario 03: /webstack:infra (mocked terraform)

Verifies the infra skill's pre-flight + plan + analyze + confirm + apply gating.

## Pre-condition

Scenario 01 ran. `myapp-infrastructure/` exists with stub `.tf` files.

## Setup

Mock terraform:

```bash
# Replace real `terraform` with a mock that returns canned plan output.
# The mock recognizes specific arguments and emits expected JSON or text.
# See tests/fixtures/mock-terraform.sh (Tier 2; for 1차, you can inline or skip).

# For 1차 1차 manual run: skip terraform actually being called, follow flow up to confirmation gate, then say "cancel".
```

## Steps

- [ ] `cd $TEST_DIR/myapp-infrastructure`. Create a fake `.env` and export mock vars:

```bash
cat > .env <<EOF
VERCEL_TOKEN=mock_vercel_token
ORACLE_API_KEY=mock_oracle_key
ORACLE_FINGERPRINT=00:00:00:00
ORACLE_TENANCY_OCID=ocid1.tenancy.oc1..mock
SUPABASE_ACCESS_TOKEN=mock_supabase_token
EOF
set -a && source .env && set +a
```

- [ ] In Claude Code session, `cd $TEST_DIR`, run `/webstack:infra`.

- [ ] **P0 Pre-flight**: agent invokes security-auditor.
  - Expected: PASS — .env exists, gitignored, deny rules present, no secrets in source.
  - Expected: env vars verified exported (test -n "$VERCEL_TOKEN") without revealing values.

- [ ] **P1 terraform plan**: agent runs `terraform init` + `terraform plan -out=plan.tfplan`.
  - With mock: agent should emit the expected commands. With real terraform: it will fail provider auth (mock token); that's OK — the test ends here and we verify the agent's behavior up to this point.

- [ ] **P2 plan analysis**: invokes terraform-plan-analyzer (only if P1 produced a plan file).
  - For mock-failed case: agent surfaces error and stops gracefully.

- [ ] **P3 Confirmation gate**: agent presents plan summary, asks for `apply`.
  - Type `cancel` (or anything other than `apply`).
  - Expected: agent aborts cleanly, no changes made.

- [ ] **Re-run with `apply`** (in mocked-success scenario): high-risk would require `I understand` second confirmation.
  - Type `cancel` at second confirmation.
  - Expected: aborts.

## Pass criteria

- security-auditor invoked at P0.
- Confirmation gate reached and respects `cancel`.
- No `terraform apply` runs without explicit confirmation.
- Manifest unchanged on cancel.

<!-- script: 03-infra-flow
# This scenario primarily tests the gating logic; full E2E requires real or mocked providers.
echo "Scenario 03 is interactive; verify confirmation gate behavior manually."
-->
