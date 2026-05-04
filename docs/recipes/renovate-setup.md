# Recipe — Renovate setup

> Setup walkthrough for activating Renovate dependency upgrades. Triggered when init's "Automated dependency upgrades" question is answered Yes (`manifest.optional_integrations.renovate=true`, default Yes).
> Reference doc: `docs/cross-cutting/dependency-management.md`.

Step-by-step activation guide — each step produces a concrete artefact (App installation, config file, or merged PR) consumed by the next.

## What this recipe activates

| Component | Role |
|---|---|
| **Renovate GitHub App** (Mend-hosted) | Runs on Mend's infrastructure — no secrets in repo, no workflow YAML required |
| **`renovate.json` (FE)** | npm/pnpm dependency tracking with group rules and patch auto-merge |
| **`renovate.json` (BE)** | Gradle version catalog tracking with Spring Boot BOM grouping |
| **`renovate.json` (Infra)** | OpenTofu provider tracking via built-in `terraform` manager + regex manager for annotated `version =` strings |
| **Dependency Dashboard issue** | GitHub Issue listing all pending updates and PR status — opened automatically on first run |

## Pre-conditions

- `webstack init` complete; all three repos (`*-frontend`, `*-backend`, `*-infrastructure`) exist on GitHub under the same organisation or user.
- GitHub admin access to all three repos (required to configure branch protection in Step 6).
- GitHub Dependency Graph enabled on each repo: **Settings → Security → Dependency graph** — required for Renovate's vulnerability advisory feed.
- Optionally, enable **Dependabot alerts** on each repo (Settings → Security) — activates the GHSA feed Renovate reads for security PRs. This does not turn on Dependabot as an update bot.

## Step 1 — Install Renovate GitHub App

1. Go to **https://github.com/apps/renovate** and click **Install**.
2. Choose **Only select repositories** and grant access to all three repos:
   - `<org>/<project>-frontend`
   - `<org>/<project>-backend`
   - `<org>/<project>-infrastructure`
3. Confirm the installation. Renovate will scan each repo for known package files immediately, but will not open any update PRs until the onboarding PR is merged (Step 5).

> Tip: Installing on all repositories is convenient for future projects but means every repo with a package file receives an onboarding PR. Selecting specific repos gives tighter control.

## Step 2 — `renovate.json` base (FE)

Create `<frontend>/renovate.json` at the repo root. This config handles npm/pnpm packages including grouped Radix UI, TanStack, Next.js, React, ESLint, and testing stack updates.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:base",
    ":dependencyDashboard",
    ":semanticCommits",
    ":separateMajorReleases",
    "schedule:nonOfficeHours"
  ],
  "ignorePaths": ["**/node_modules/**", "**/src/shared/api/generated/**"],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true, "labels": ["dependencies", "github-actions"] },
    { "groupName": "Radix UI primitives", "matchPackagePatterns": ["^@radix-ui/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "TanStack libraries", "matchPackagePatterns": ["^@tanstack/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Next.js framework", "matchPackageNames": ["next", "eslint-config-next"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "React ecosystem", "matchPackageNames": ["react", "react-dom", "@types/react", "@types/react-dom"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "ESLint ecosystem", "matchPackagePatterns": ["^eslint", "^@typescript-eslint/"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Testing stack", "matchPackagePatterns": ["^@testing-library/", "^jest", "^vitest"], "matchUpdateTypes": ["minor", "patch"] }
  ]
}
```

Key points:

- `ignorePaths` excludes the generated OpenAPI SDK (`src/shared/api/generated/`) — regenerate via `pnpm gen:api`, not Renovate.
- Patch and digest updates auto-merge on green CI; minor and major updates open PRs for review.
- Full group definitions and rationale: `docs/cross-cutting/dependency-management.md` §Frontend groups.

## Step 3 — `renovate.json` base (BE)

Create `<backend>/renovate.json`. The Gradle manager tracks `gradle/libs.versions.toml` (version catalog). Spring Boot BOM grouping ensures the BOM and its managed dependencies upgrade together.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:base",
    ":dependencyDashboard",
    ":semanticCommits",
    ":separateMajorReleases",
    "schedule:nonOfficeHours"
  ],
  "ignorePaths": ["**/build/generated-src/**"],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true, "labels": ["dependencies", "github-actions"] },
    { "groupName": "Spring Boot BOM", "matchPackagePatterns": ["^org\\.springframework\\.boot", "^org\\.springframework", "^io\\.spring\\.dependency-management"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Kotlin libraries", "matchPackagePatterns": ["^org\\.jetbrains\\.kotlin"], "matchUpdateTypes": ["minor", "patch"] },
    { "groupName": "Kotest", "matchPackagePatterns": ["^io\\.kotest"], "matchUpdateTypes": ["minor", "patch"] }
  ]
}
```

Key points:

- `ignorePaths` excludes jOOQ-generated source (`build/generated-src/`) — regenerate via Gradle task.
- The `gradle` manager reads `gradle/libs.versions.toml` automatically; no extra `customManagers` needed for the catalog.
- Full BOM grouping rationale: `docs/cross-cutting/dependency-management.md` §Backend groups.

## Step 4 — `renovate.json` base (Infra)

Create `<infrastructure>/renovate.json`. The built-in `terraform` manager handles `required_providers` blocks. A `customManagers` regex entry tracks annotated `version = "..."` strings elsewhere in `*.tf` files.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:base",
    ":dependencyDashboard",
    ":semanticCommits",
    ":separateMajorReleases",
    "schedule:nonOfficeHours"
  ],
  "vulnerabilityAlerts": { "schedule": ["at any time"], "prPriority": 10, "automerge": false },
  "packageRules": [
    { "matchUpdateTypes": ["patch", "digest"], "automerge": false, "labels": ["infra-patch"] },
    { "matchUpdateTypes": ["minor", "major"], "automerge": false, "labels": ["infra-minor", "needs-review"] },
    { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true, "labels": ["dependencies", "github-actions"] },
    { "groupName": "OpenTofu providers", "matchManagers": ["terraform"], "matchUpdateTypes": ["minor", "patch"] }
  ],
  "customManagers": [
    {
      "customType": "regex",
      "managerFilePatterns": ["/\\.tf$/"],
      "matchStrings": ["# renovate: datasource=(?<datasource>[a-z-]+?) depName=(?<depName>.+?)\\s+version\\s*=\\s*\"(?<currentValue>[^\"]+)\""],
      "versioningTemplate": "hashicorp"
    }
  ]
}
```

Key points:

- **All update types have `automerge: false`** — infrastructure changes must go through `tofu plan` review regardless of semver magnitude.
- To use the regex manager, annotate `version` strings in `*.tf` with a comment immediately above:

  ```hcl
  # renovate: datasource=github-releases depName=hashicorp/terraform
  version = "1.8.0"
  ```

- Renovate uses the RE2 engine — no lookahead/lookbehind. Use explicit named capture groups only.
- Full regex manager reference: `docs/cross-cutting/dependency-management.md` §regexManager.

## Step 5 — Onboarding PR review + merge

After the `renovate.json` files are committed to each repo's default branch, Renovate opens an **onboarding PR** in each repo (branch: `renovate/configure`). The PR description lists detected package managers and a preview of what updates Renovate would open.

Review checklist before merging each onboarding PR:

- Detected managers match expectations (e.g., `npm`, `gradle`, `terraform`, `github-actions`).
- No unexpected paths listed under "Ignored".
- Group rules appear under "Package Rules" preview.
- No configuration errors flagged in the PR description.

Merge each onboarding PR with a standard merge commit (not squash — preserves the `renovate/configure` branch history for audit). Renovate does not make any changes to the repo until the onboarding PR is merged.

If you need to adjust config before merging, edit `renovate.json` in the `renovate/configure` branch — the PR description updates automatically.

## Step 6 — Auto-merge gate

Auto-merge is only safe when branch protection requires CI green. Configure this for each repo's `main` branch before Renovate begins opening update PRs.

**GitHub Settings → Branches → Add branch ruleset for `main`:**

1. Enable **Require status checks to pass** before merging.
2. Add required checks: `lint`, `test-summary`, `build` (match your CI job names exactly).
3. Enable **Require branches to be up to date before merging**.
4. Enable **Require a pull request before merging** (at least 1 approval) — can be exempted for bot PRs if desired.

Without required checks, `automerge: true` in `renovate.json` merges patch PRs immediately on creation, bypassing CI. Always pair auto-merge with required checks.

Full CI/CD check names: `docs/infrastructure/ci-cd.md`.

## Step 7 — Verify

After merging all three onboarding PRs, confirm Renovate is live:

**Dependency Dashboard issue opened:**

```
GitHub → <repo> → Issues → search "Renovate Dependency Dashboard"
```

The issue should list pending updates grouped by type. If it hasn't appeared within 10 minutes, check the Renovate app logs at https://app.renovatebot.com/dashboard (log in with GitHub OAuth).

**First dependency PR arrives:**

Within the first scheduled window (`schedule:nonOfficeHours`), Renovate opens batched update PRs. Each PR shows:

- Package name, current version → target version
- Merge confidence badges (Age, Adoption, Passing, Confidence)
- CI status

Patch/digest PRs on FE and BE repos auto-merge on green CI. Infra PRs and minor/major PRs remain open for review.

**Security PR smoke test (optional):**

Temporarily pin a known-vulnerable version in `package.json` (e.g., a package with a published CVE), push to a branch, and confirm Renovate opens a vulnerability PR outside the normal schedule.

## Step 8 — manifest flag ON

Once all three onboarding PRs are merged and the Dependency Dashboard issue is open:

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

`docs/cross-cutting/dependency-management.md` — group rules, schedule tiers, auto-merge policy, regexManager details, anti-patterns, and the full `packageRules` JSON for all three repos.

## Sources

- **Renovate installing and onboarding:** https://docs.renovatebot.com/getting-started/installing-onboarding/ — _authoritative_
- **Renovate GitHub App (Mend.io):** https://github.com/apps/renovate — _community: Mend.io_
- **Renovate regex custom manager:** https://docs.renovatebot.com/modules/manager/regex/ — _authoritative_
- **Renovate configuration options reference:** https://docs.renovatebot.com/configuration-options/ — _authoritative_

Last verified: 2026-05-04 (Renovate 39.X / GitHub App).
