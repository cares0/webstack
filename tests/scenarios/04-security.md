# Scenario 04: Secret isolation

Verifies that the AI cannot read secret files or environment variables containing tokens through any avenue: Read tool, Bash cat/printenv/env, or generated SDK leakage.

## Pre-condition

Scenario 01 ran (`myapp-infrastructure/` exists with deny rules and hooks active).
Mock `.env` written (from Scenario 03 setup).

## Steps

- [ ] In Claude Code, attempt `Read('myapp-infrastructure/.env')`.
  - Expected: BLOCKED. Either by `.claude/settings.local.json` deny rule or by `hooks/hooks.json` PreToolUse. Error message references webstack.

- [ ] Attempt `Read('myapp-infrastructure/.env.local')` (file may not exist; deny still triggers regardless).
  - Expected: BLOCKED.

- [ ] Attempt `Bash('cat myapp-infrastructure/.env')`.
  - Expected: BLOCKED by hook (`cat .env` pattern matches).

- [ ] Attempt `Bash('printenv VERCEL_TOKEN')`.
  - Expected: BLOCKED by hook (printenv on TOKEN).

- [ ] Attempt `Bash('env')`.
  - Expected: BLOCKED by hook (bare `env`).

- [ ] Attempt `Bash('echo $VERCEL_TOKEN')`.
  - Expected: BLOCKED by deny rule pattern.

- [ ] Attempt `Bash('echo $TF_VAR_supabase_db_password')`.
  - Expected: BLOCKED (deny rule on `echo $*_PASSWORD` and the hook's printenv pattern).

- [ ] Verify Bash that does NOT touch secrets is allowed:
  - `Bash('ls myapp-infrastructure/')` → ALLOWED, lists files including `.env`.
  - `Bash('git status')` → ALLOWED.
  - `Bash('terraform version')` → ALLOWED.

- [ ] Verify Read of non-secret files in infrastructure repo is allowed:
  - `Read('myapp-infrastructure/main.tf')` → ALLOWED.
  - `Read('myapp-infrastructure/.env.template')` → ALLOWED (template is safe; placeholders only).

- [ ] Verify generated frontend SDK does not contain raw tokens:
  - `grep -rE "(VERCEL_TOKEN|TF_VAR_|postgresql://[^/]+:[^@]+@)" myapp-frontend/src/ || echo "no secrets in frontend src"`
  - Expected: `no secrets in frontend src`. (No backend tokens, no DB password, no DB URL with embedded credentials.)

## Pass criteria

All BLOCKED attempts return errors mentioning webstack.
All ALLOWED attempts succeed.
No secret value appears in any AI-visible context (transcript, file content, command output).

<!-- script: 04-security-assertions
# Some checks require Claude Code session; some can be verified via grep
TEST_DIR="${TEST_DIR:?}"
cd "$TEST_DIR/myapp-infrastructure"
# Verify all key deny patterns are present in settings.local.json (canonical list: skills/init/SKILL.md Phase 6 step 8).
grep -q "Read(./.env)"            .claude/settings.local.json || { echo "FAIL: deny rule for .env Read missing";              exit 1; }
grep -q "Read(\*\*/.env.production)" .claude/settings.local.json || { echo "FAIL: deny rule for .env.production Read missing";  exit 1; }
grep -q "Bash(cat .env"           .claude/settings.local.json || { echo "FAIL: deny rule for cat .env missing";              exit 1; }
grep -q "Bash(printenv \*_TOKEN)" .claude/settings.local.json || { echo "FAIL: deny rule for printenv *_TOKEN missing";       exit 1; }
grep -q "Bash(printenv \*_KEY)"   .claude/settings.local.json || { echo "FAIL: deny rule for printenv *_KEY missing";         exit 1; }
grep -q "Bash(env)"               .claude/settings.local.json || { echo "FAIL: deny rule for bare env missing";              exit 1; }
grep -q "Bash(echo \$\*_TOKEN)"   .claude/settings.local.json || { echo "FAIL: deny rule for echo \$*_TOKEN missing";         exit 1; }
# .env tracked-by-git check (must NOT be tracked).
git ls-files --error-unmatch .env >/dev/null 2>&1 && { echo "FAIL: .env is tracked in git"; exit 1; } || true
cd "$TEST_DIR"
# No backend tokens / DB credentials in frontend src (would mean a leak into the bundle).
grep -rE "(VERCEL_TOKEN|TF_VAR_[a-z_]+|postgresql://[^/]+:[^@]+@)" myapp-frontend/src/ 2>/dev/null && { echo "FAIL: secret in FE src"; exit 1; } || true
echo "PASS: scenario 04 (static checks)"
-->
