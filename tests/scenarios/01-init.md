# Scenario 01: /webstack:init

Verifies the init skill's full phase flow produces the expected file structure and metadata.

## Setup

```bash
# 1. fresh test dir
TEST_DIR=$(mktemp -d -t webstack-init-XXXXXX)
cd "$TEST_DIR"
echo "Test dir: $TEST_DIR"
```

## Steps

- [ ] In a Claude Code session, `cd "$TEST_DIR"`, run `/webstack:init`.

- [ ] **P0 Pre-flight**: agent verifies dir is empty, asks for project name. Type `myapp`.
  - Expected: dir empty confirmed; name accepted.

- [ ] **P1 Identity interview**: agent asks one-line def, core values, tone, category, archetype.
  - Mock answers:
    - one-line: `A self-care companion that nudges habits without nagging`
    - values: trustworthy, calm, encouraging
    - tone: gentle, clear, hopeful
    - category: B2C consumer mobile + DTC
    - archetype: unsure → expect agent to invoke brand-archetype-matcher
  - Expected: agent reports primary=Caregiver, secondary=Sage (or similar reasoning), confidence=High.
  - Checkpoint: confirm.

- [ ] Verify file: `cat .webstack/identity.md`
  - Expected: contains "Caregiver", core values listed.

- [ ] **P2 Persona interview**: agent asks demographics, goals, pain, context.
  - Mock answers: name=Mira, age=34, ...
  - Expected: `cat .webstack/personas/primary.md` shows Cooper-format content.

- [ ] **P3 Design system**: agent invokes design-system-architect.
  - Expected: `.webstack/design-system/` contains `tokens.json`, `theme.css`, `component-variants.md`.
  - Verify JSON: `python3 -c "import json; d=json.load(open('.webstack/design-system/tokens.json')); assert 'color' in d; print('OK')"`
  - Verify theme.css contains `:root {` and `--background:`, `--foreground:`, `--primary:`.

- [ ] **P4 Frontend repo**: agent creates `myapp-frontend/`.
  - Expected: `[ -d myapp-frontend/.git ]`, `[ -f myapp-frontend/package.json ]`, `[ -d myapp-frontend/src/app ]`, `[ -f myapp-frontend/components.json ]`.

- [ ] **P5 Backend repo**: agent creates `myapp-backend/`.
  - Expected: `[ -d myapp-backend/.git ]`, `[ -f myapp-backend/build.gradle.kts ]`, `[ -d myapp-backend/src/main/kotlin ]`.

- [ ] **P6 Infrastructure repo**: agent creates `myapp-infrastructure/`.
  - Expected: `[ -d myapp-infrastructure/.git ]`, `[ -f myapp-infrastructure/main.tf ]`, `[ -f myapp-infrastructure/.env.template ]`, `[ -f myapp-infrastructure/.claude/settings.local.json ]`, `[ -f myapp-infrastructure/SETUP.md ]`.

- [ ] **Completion**: agent writes manifest, prints next-step message.
  - Expected: `[ -f .webstack/manifest.yaml ]`. `python3 -c "import yaml; d=yaml.safe_load(open('.webstack/manifest.yaml')); assert d['project']['name']=='myapp'; assert d['last_phase']['init']=='completed'; print('OK')"`

## Cleanup

```bash
rm -rf "$TEST_DIR"
```

## Pass criteria

All [ ] above check off, no error popup at any checkpoint.

<!-- script: 01-init-assertions
TEST_DIR="${TEST_DIR:?set TEST_DIR before sourcing}"
cd "$TEST_DIR"
test -f .webstack/manifest.yaml || { echo "FAIL: manifest"; exit 1; }
test -f .webstack/identity.md || { echo "FAIL: identity"; exit 1; }
test -f .webstack/design-system/tokens.json || { echo "FAIL: tokens"; exit 1; }
test -d myapp-frontend/.git || { echo "FAIL: frontend repo"; exit 1; }
test -d myapp-backend/.git || { echo "FAIL: backend repo"; exit 1; }
test -d myapp-infrastructure/.git || { echo "FAIL: infrastructure repo"; exit 1; }
test -f myapp-infrastructure/SETUP.md || { echo "FAIL: SETUP.md"; exit 1; }
test -f myapp-infrastructure/.claude/settings.local.json || { echo "FAIL: deny rules"; exit 1; }
echo "PASS: scenario 01"
-->
