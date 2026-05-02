# Scenario 02: /webstack:feature

Verifies the feature skill orchestrates parallel implementer SubAgents and produces all expected artifacts. Uses an unauthenticated feature (`note-create`) so the scenario does not depend on the auth opt-in or any ID provider — webstack does not bundle authentication.

## Pre-condition

Scenario 01 has been run successfully (or its artifacts exist) in `$TEST_DIR`.

## Steps

- [ ] In a fresh Claude Code session at `$TEST_DIR`, run `/webstack:feature note-create`.

- [ ] **P0 Pre-flight**: agent verifies manifest exists, name valid, repos clean.
  - Expected: pass.

- [ ] **P1 Worktree creation**: agent runs `git worktree add` in both FE and BE repos.
  - Expected: `[ -d myapp-frontend/.worktrees/note-create ]`, `[ -d myapp-backend/.worktrees/note-create ]`.
  - Verify branches: `cd myapp-frontend && git branch | grep "feature/note-create"`.
  - Verify worktree-paths.yaml: `cat .webstack/features/note-create/worktree-paths.yaml`.

- [ ] **P2 plan-feature interview**: agent walks through PRD template.
  - Mock answers: goal=let the user write a short personal note; persona=primary; routes=`/notes` (list) + `/notes/new` (create form); functions=submit form with title+body, redirect to list; rules=title 1–80 chars, body 0–5000 chars; out-of-scope: editing, deleting, sharing, authentication.
  - Expected: `.webstack/features/note-create/plan.md` written with all sections.

- [ ] **P2.5 Architect**: agent invokes feature-architect.
  - Expected: report proposes a `Note` aggregate (with title + body + createdAt), `CreateNoteUseCase` application service, `POST /api/notes` + `GET /api/notes` endpoints. The architect's `Auth:` field should be empty/omitted because the project's `needs_auth=false` (or the feature itself is unauthenticated even if `needs_auth=true`).

- [ ] **P3 sync-contract**: agent writes `.webstack/contracts/note-create.yaml`.
  - Expected: OpenAPI 3.1 valid (`python3 -c "import yaml; yaml.safe_load(open('.webstack/contracts/note-create.yaml'))"`); paths include `POST /api/notes` and `GET /api/notes`; components.schemas include `Note`, `NoteCreateRequest`, `NoteList`, `Error`. No `securitySchemes` block (the feature is unauthenticated).

- [ ] **P4-5 Parallel implementation**: agent invokes backend-implementer + frontend-implementer in parallel.
  - Expected: both return successfully (or escalate, agent resolves with mock answers, re-invokes).
  - Verify FE (FSD-lite layer skeleton + feature slice): `[ -d myapp-frontend/.worktrees/note-create/src/shared/api/generated ]`, `[ -f myapp-frontend/.worktrees/note-create/src/app/notes/new/page.tsx ]`, `[ -f myapp-frontend/.worktrees/note-create/src/features/note-create/model/schema.ts ]`. The feature slice should also have `src/features/note-create/ui/` and `src/features/note-create/api/` populated; an entity slice at `src/entities/note/` is acceptable for the read-side.
  - Verify BE (Modulith module = bounded context, hexagonal layers inside): `[ -d myapp-backend/.worktrees/note-create/src/main/kotlin/com/example/myapp/<module>/domain/note ]` (the architect typically names `<module>` something like `notes` or maps into the existing `core/` placeholder), `[ -f myapp-backend/.worktrees/note-create/src/main/kotlin/com/example/myapp/<module>/infrastructure/http/NotesController.kt ]`, `[ -f myapp-backend/.worktrees/note-create/src/test/kotlin/com/example/myapp/<module>/domain/note/NoteSpec.kt ]`.

- [ ] **P6 Tests**: test-runner SubAgent runs `./gradlew test` and `pnpm test`.
  - Expected: report shows all green (mocked tests pass).

- [ ] **P7 Review**: code-reviewer + contract-drift-detective in parallel.
  - Expected: code-reviewer Critical=0; drift-detective Clean OR Important-only.

- [ ] **P8 PR generation**: agent emits push + gh pr create commands or actually runs them on a mock remote.
  - Expected: `.webstack/manifest.yaml` features array updated with `note-create` and PR URLs (if real `gh`) or placeholder (if mock).
  - Expected: be-status.md and fe-status.md exist under `.webstack/features/note-create/`.

## Pass criteria

All file artifacts present; no Critical findings; both status.md show "Definition of Done" satisfied.

<!-- script: 02-feature-assertions
TEST_DIR="${TEST_DIR:?}"
cd "$TEST_DIR"
test -d myapp-frontend/.worktrees/note-create || { echo "FAIL: FE worktree"; exit 1; }
test -d myapp-backend/.worktrees/note-create || { echo "FAIL: BE worktree"; exit 1; }
test -f .webstack/contracts/note-create.yaml || { echo "FAIL: contract"; exit 1; }
test -f .webstack/features/note-create/plan.md || { echo "FAIL: plan"; exit 1; }
test -f .webstack/features/note-create/be-status.md || { echo "FAIL: be-status"; exit 1; }
test -f .webstack/features/note-create/fe-status.md || { echo "FAIL: fe-status"; exit 1; }
echo "PASS: scenario 02"
-->
