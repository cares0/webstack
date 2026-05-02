# Scenario 03: /webstack:infra (mocked OpenTofu)

Verifies the infra skill's pre-flight + plan + analyze + confirm + apply gating.

## Pre-condition

Scenario 01 ran. `myapp-infrastructure/` exists with stub `.tf` files.

## Setup

Mock OpenTofu:

```bash
# Replace real `tofu` with a mock that returns canned plan output.
# The mock recognizes specific arguments and emits expected JSON or text.
# See tests/fixtures/mock-tofu.sh (Tier 2; for 1차, you can inline or skip).

# For 1차 manual run: skip `tofu` actually being called, follow flow up to confirmation gate, then say "cancel".
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

- [ ] **P1 tofu plan**: agent runs `tofu init` + `tofu plan -out=plan.tfplan`.
  - With mock: agent should emit the expected commands. With real OpenTofu: it will fail provider auth (mock token); that's OK — the test ends here and we verify the agent's behavior up to this point.

- [ ] **P2 plan analysis**: invokes tofu-plan-analyzer (only if P1 produced a plan file).
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
- No `tofu apply` runs without explicit confirmation.
- Manifest unchanged on cancel.

<!-- script: 03-infra-static-assertions
# Static post-conditions verifiable without a Claude Code session.
# Interactive parts (the cancel-on-confirm gate) are verified manually.
TEST_DIR="${TEST_DIR:?set TEST_DIR before sourcing}"
cd "$TEST_DIR/myapp-infrastructure"
# .env exists (the user filled it) and is gitignored.
[ -f .env ] || { echo "FAIL: .env not present (was test setup skipped?)"; exit 1; }
git check-ignore -q .env || { echo "FAIL: .env is not gitignored"; exit 1; }
# .env.template is committed (the placeholder template), not .env itself.
git ls-files --error-unmatch .env.template >/dev/null 2>&1 || { echo "FAIL: .env.template missing from index"; exit 1; }
git ls-files --error-unmatch .env >/dev/null 2>&1 && { echo "FAIL: .env tracked in git"; exit 1; } || true
# All variable declarations carrying tokens/keys/passwords have sensitive = true.
grep -E "variable \"[a-zA-Z_]*(token|key|password)\"" -i variables.tf | while read line; do
  varname=$(echo "$line" | sed -E 's/.*"([^"]+)".*/\1/')
  awk -v v="$varname" '/^variable "/{name=$2;gsub(/[\"\{]/,"",name)} name==v && /sensitive *= *true/{found=1} END{exit found?0:1}' variables.tf || \
    { echo "FAIL: variable '$varname' missing sensitive = true"; exit 1; }
done
# After cancel, no state file exists (apply did not run).
[ ! -f terraform.tfstate ] || { echo "FAIL: terraform.tfstate present — apply ran when it should not have"; exit 1; }
echo "PASS: scenario 03 (static checks)"
-->
