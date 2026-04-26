# Scenario 02: /webstack:feature

Verifies the feature skill orchestrates parallel implementer SubAgents and produces all expected artifacts.

## Pre-condition

Scenario 01 has been run successfully (or its artifacts exist) in `$TEST_DIR`.

## Steps

- [ ] In a fresh Claude Code session at `$TEST_DIR`, run `/webstack:feature user-login`.

- [ ] **P0 Pre-flight**: agent verifies manifest exists, name valid, repos clean.
  - Expected: pass.

- [ ] **P1 Worktree creation**: agent runs `git worktree add` in both FE and BE repos.
  - Expected: `[ -d myapp-frontend/.worktrees/user-login ]`, `[ -d myapp-backend/.worktrees/user-login ]`.
  - Verify branches: `cd myapp-frontend && git branch | grep "feature/user-login"`.
  - Verify worktree-paths.yaml: `cat .webstack/features/user-login/worktree-paths.yaml`.

- [ ] **P2 plan-feature interview**: agent walks through PRD template.
  - Mock answers: goal=allow registered users to sign in via email+password; persona=primary; routes=`/login`; functions=submit form, redirect to dashboard; rules=lockout after 5 failed.
  - Expected: `.webstack/features/user-login/plan.md` written with all sections.

- [ ] **P2.5 Architect**: agent invokes feature-architect.
  - Expected: report references existing identity/personas, proposes `Auth` aggregate (or similar), `LoginUseCase` application, `/api/sessions` endpoint.

- [ ] **P3 sync-contract**: agent writes `.webstack/contracts/user-login.yaml`.
  - Expected: OpenAPI 3.1 valid (`python3 -c "import yaml; yaml.safe_load(open('.webstack/contracts/user-login.yaml'))"`); paths include `POST /api/sessions`; components.schemas include `LoginRequest`, `Session`, `Error`.

- [ ] **P4-5 Parallel implementation**: agent invokes backend-implementer + frontend-implementer in parallel.
  - Expected: both return successfully (or escalate, agent resolves with mock answers, re-invokes).
  - Verify FE: `[ -d myapp-frontend/.worktrees/user-login/src/api/generated ]`, `[ -f myapp-frontend/.worktrees/user-login/src/app/login/page.tsx ]`, `[ -f myapp-frontend/.worktrees/user-login/src/components/login/schema.ts ]`.
  - Verify BE: `[ -d myapp-backend/.worktrees/user-login/src/main/kotlin/com/example/myapp/domain/auth ]`, `[ -f myapp-backend/.worktrees/user-login/src/main/kotlin/com/example/myapp/infrastructure/http/SessionsController.kt ]` (or similar names per architect), `[ -f myapp-backend/.worktrees/user-login/src/test/kotlin/com/example/myapp/domain/auth/AuthSpec.kt ]`.

- [ ] **P6 Tests**: test-runner SubAgent runs `./gradlew test` and `pnpm test`.
  - Expected: report shows all green (mocked tests pass).

- [ ] **P7 Review**: code-reviewer + contract-drift-detective in parallel.
  - Expected: code-reviewer Critical=0; drift-detective Clean OR Important-only.

- [ ] **P8 PR generation**: agent emits push + gh pr create commands or actually runs them on a mock remote.
  - Expected: `.webstack/manifest.yaml` features array updated with `user-login` and PR URLs (if real `gh`) or placeholder (if mock).
  - Expected: be-status.md and fe-status.md exist under `.webstack/features/user-login/`.

## Pass criteria

All file artifacts present; no Critical findings; both status.md show "Definition of Done" satisfied.

<!-- script: 02-feature-assertions
TEST_DIR="${TEST_DIR:?}"
cd "$TEST_DIR"
test -d myapp-frontend/.worktrees/user-login || { echo "FAIL: FE worktree"; exit 1; }
test -d myapp-backend/.worktrees/user-login || { echo "FAIL: BE worktree"; exit 1; }
test -f .webstack/contracts/user-login.yaml || { echo "FAIL: contract"; exit 1; }
test -f .webstack/features/user-login/plan.md || { echo "FAIL: plan"; exit 1; }
test -f .webstack/features/user-login/be-status.md || { echo "FAIL: be-status"; exit 1; }
test -f .webstack/features/user-login/fe-status.md || { echo "FAIL: fe-status"; exit 1; }
echo "PASS: scenario 02"
-->
