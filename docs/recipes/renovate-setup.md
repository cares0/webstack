# Recipe — Renovate setup

> Setup walkthrough for activating Renovate dependency upgrades. Triggered when init's "Automated dependency upgrades" question is answered Yes (`manifest.optional_integrations.renovate=true`, default Yes).
> Reference doc: `docs/cross-cutting/dependency-management.md`.

## What this recipe activates

| Component | Role |
|---|---|
| **Renovate GitHub App** (Mend-hosted) | Runs on Mend's infrastructure — no secrets in repo, no workflow YAML required |
| **`renovate.json` (FE)** | npm/pnpm tracking with group rules and patch auto-merge |
| **`renovate.json` (BE)** | Gradle version catalog tracking with Spring Boot BOM grouping |
| **`renovate.json` (Infra)** | OpenTofu provider tracking + regex manager for annotated `version =` strings |
| **Dependency Dashboard issue** | GitHub Issue listing all pending updates — opened on first run |

## Pre-conditions

- `webstack init` complete; all three repos exist on GitHub under the same org/user.
- GitHub admin access to all three repos (needed for branch protection in Step 6).
- **Settings → Security → Dependency graph** enabled on each repo — required for Renovate's vulnerability advisory feed.

## Step 1 — Install Renovate GitHub App

1. Go to **https://github.com/apps/renovate** and click **Install**.
2. Choose **Only select repositories** and grant access to all three:
   - `<org>/<project>-frontend`
   - `<org>/<project>-backend`
   - `<org>/<project>-infrastructure`
3. Confirm. Renovate scans each repo immediately but opens no PRs until the onboarding PR is merged (Step 5).

## Step 2 — `renovate.json` base (FE)

Create `<frontend>/renovate.json`:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base", ":dependencyDashboard", ":semanticCommits", ":separateMajorReleases", "schedule:nonOfficeHours"],
  "ignorePaths": ["**/node_modules/**", "**/src/shared/api/generated/**"],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true },
    { "groupName": "Radix UI primitives", "matchPackagePatterns": ["^@radix-ui/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "TanStack libraries", "matchPackagePatterns": ["^@tanstack/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Next.js framework", "matchPackageNames": ["next", "eslint-config-next"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "React ecosystem", "matchPackageNames": ["react", "react-dom", "@types/react", "@types/react-dom"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "ESLint ecosystem", "matchPackagePatterns": ["^eslint", "^@typescript-eslint/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Testing stack", "matchPackagePatterns": ["^@testing-library/", "^jest", "^vitest"], "matchUpdateTypes": ["minor", "patch"] }
  ]
}
```

`ignorePaths` excludes the generated OpenAPI SDK (`src/shared/api/generated/`) — regenerate via `pnpm gen:api`. Full group rationale: `docs/cross-cutting/dependency-management.md` §Frontend groups.

## Step 3 — `renovate.json` base (BE)

Create `<backend>/renovate.json`. The built-in `gradle` manager reads `gradle/libs.versions.toml` automatically.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base", ":dependencyDashboard", ":semanticCommits", ":separateMajorReleases", "schedule:nonOfficeHours"],
  "ignorePaths": ["**/build/generated-src/**"],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true },
    { "groupName": "Spring Boot BOM", "matchPackagePatterns": ["^org\\.springframework", "^io\\.spring\\.dependency-management"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Kotlin libraries", "matchPackagePatterns": ["^org\\.jetbrains\\.kotlin"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Kotest", "matchPackagePatterns": ["^io\\.kotest"], "matchUpdateTypes": ["minor", "patch"] }
  ]
}
```

`ignorePaths` excludes jOOQ-generated source (`build/generated-src/`). Full BOM grouping rationale: `docs/cross-cutting/dependency-management.md` §Backend groups.

## Step 4 — `renovate.json` base (Infra)

Create `<infrastructure>/renovate.json`. **All update types have `automerge: false`** — infra changes require `tofu plan` review. The `customManagers` regex entry tracks annotated `version = "..."` strings in `*.tf` files outside `required_providers`.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base", ":dependencyDashboard", ":semanticCommits", ":separateMajorReleases", "schedule:nonOfficeHours"],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": false, "labels": ["infra-patch"] },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false, "labels": ["infra-minor", "needs-review"] },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true },
    { "groupName": "OpenTofu providers", "matchManagers": ["terraform"], "matchUpdateTypes": ["minor", "patch"] }
  ],
  "customManagers": [{
    "customType": "regex",
    "managerFilePatterns": ["/\\.tf$/"],
    "matchStrings": ["# renovate: datasource=(?<datasource>[a-z-]+?) depName=(?<depName>.+?)\\s+version\\s*=\\s*\"(?<currentValue>[^\"]+)\""],
    "versioningTemplate": "hashicorp"
  }]
}
```

Annotate `version` strings in `*.tf` to activate the regex manager:

```hcl
# renovate: datasource=github-releases depName=hashicorp/terraform
version = "1.8.0"
```

Renovate uses RE2 — no lookahead/lookbehind; use explicit named capture groups only. Full reference: `docs/cross-cutting/dependency-management.md` §regexManager.

## Step 5 — Onboarding PR review + merge

After committing `renovate.json` to each repo's default branch, Renovate opens an onboarding PR (branch: `renovate/configure`). The PR description lists detected managers and a preview of planned updates. Renovate makes no changes until this PR is merged.

Before merging, verify: detected managers match expectations (`npm`, `gradle`, `terraform`, `github-actions`), no unexpected paths listed under "Ignored", and no config errors flagged. To adjust config before merging, edit `renovate.json` on the `renovate/configure` branch — the PR description updates automatically. Merge with a standard merge commit.

## Step 6 — Auto-merge gate

Set branch protection on `main` in each repo (**GitHub Settings → Branches → Add branch ruleset**): enable **Require status checks to pass** with checks `lint`, `test-summary`, `build`; enable **Require branches to be up to date before merging**.

Without required checks, `automerge: true` merges patch PRs on creation, bypassing CI. Full CI check names: `docs/infrastructure/ci-cd.md`.

## Step 7 — Verify

Search each repo's Issues for "Renovate Dependency Dashboard". The issue lists pending updates by type. If absent after 10 minutes, check https://app.renovatebot.com/dashboard (GitHub OAuth).

Within the first `schedule:nonOfficeHours` window, Renovate opens batched update PRs showing merge confidence badges (Age, Adoption, Passing, Confidence) and CI status. Patch/digest PRs on FE and BE auto-merge on green CI; infra and minor/major PRs remain open for review.

## Step 8 — manifest flag ON

Once all three onboarding PRs are merged and the Dependency Dashboard is open:

```yaml
# .webstack/manifest.yaml
optional_integrations:
  renovate: true
```

```bash
git -C <parent-dir> add .webstack/manifest.yaml
git -C <parent-dir> commit -m "chore: enable renovate integration"
```

This flag signals to `/webstack:feature` and `/webstack:deploy` that Renovate is live and dependency hygiene expectations apply to all future features.

## Reference doc

`docs/cross-cutting/dependency-management.md` — group rules, schedule tiers, auto-merge policy, regexManager details, anti-patterns, and full `packageRules` JSON for all three repos.

## Sources

- **Renovate installing and onboarding:** https://docs.renovatebot.com/getting-started/installing-onboarding/ — _authoritative_
- **Renovate GitHub App (Mend.io):** https://github.com/apps/renovate — _community: Mend.io_
- **Renovate regex custom manager:** https://docs.renovatebot.com/modules/manager/regex/ — _authoritative_
- **Renovate configuration options reference:** https://docs.renovatebot.com/configuration-options/ — _authoritative_

Last verified: 2026-05-04 (Renovate 39.X / GitHub App).
