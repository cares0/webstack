# webstack tests

End-to-end scenario tests. Each scenario verifies one slash command's expected behavior.

## Structure

```
tests/
├── README.md                   ← this file
└── scenarios/
    ├── 01-init.md              ← /webstack:init flow
    ├── 02-feature.md           ← /webstack:feature flow
    ├── 03-infra.md             ← /webstack:infra (mocked terraform)
    └── 04-security.md          ← secret isolation
```

## How to run

### Manual (recommended for 1차)

Each scenario file is a step-by-step script. Open a fresh Claude Code session in a clean directory and follow the steps. Mark each step with `- [ ]` → check off as you go. Compare actual vs expected at every checkpoint.

### Semi-automated (CI-friendly)

Some assertions can be Bash-scripted (file existence, JSON shape, deny-rule pattern match). Look for `<!-- script: ... -->` blocks in scenario files; concatenate them into a runnable script.

```bash
# Example for scenario 01
grep -A 20 "<!-- script: 01" tests/scenarios/01-init.md > /tmp/01-init.sh
bash /tmp/01-init.sh
```

## Test data isolation

- Scenarios run in a temporary directory: `mktemp -d -t webstack-test-XXXXXX`.
- Mock provider tokens used (no real API calls).
- Mock GitHub remote: `gh-mock` or `--no-push` flags.

## What the scenarios DON'T test

- Actual Vercel/Oracle/Supabase API calls (would require real accounts and burn quota).
- Long-running deploy polling.
- Real PR creation on GitHub (use `gh pr create --dry-run` if available, else mock).

For real-environment validation, use scenario 02-feature in a sandbox project with disposable repos.
