# Dependency management (Renovate)

> Reference for /webstack:init slash command and security-auditor SubAgent.
> ⚙️ **Optional integration** — activated via init's "Automated dependency upgrades" question (`manifest.optional_integrations.renovate=true`, default Yes). Until activated, this document is reference-only; setup steps live in `recipes/renovate-setup.md`.
> Renovate Bot configuration for webstack's 3-repo setup with grouping, scheduling, and selective auto-merge.

---

## What is webstack dependency management

A webstack project spans three sibling git repositories that accumulate dependencies independently:

| Repo | Ecosystem | Lock file |
|---|---|---|
| `*-frontend` | npm/pnpm | `pnpm-lock.yaml` |
| `*-backend` | Gradle/Kotlin | `gradle/libs.versions.toml` |
| `*-infrastructure` | OpenTofu | `*.tf` version constraints |

Left unmanaged, these repos drift: security patches go un-applied, major bumps pile up into high-risk rewrites, and lock files diverge from declared constraints. webstack designates **Renovate** as the standard update bot.

When `manifest.optional_integrations.renovate=true` (default at `/webstack:init` time), each repo receives a `renovate.json` at its root. Renovate runs as a **GitHub App** on Mend's hosted infrastructure — no secrets in the repo, no workflow YAML required.

---

## Why Renovate over Dependabot

GitHub ships Dependabot by default, so teams reach for it first. For a polyglot 3-repo setup, Renovate is a better fit across five dimensions:

**Single config, multiple managers.** Dependabot requires one `dependabot.yml` block per ecosystem. Renovate handles `npm`, `gradle`, `terraform`, `docker`, and `github-actions` from a single `renovate.json`. Adding a manager is one `packageRules` entry.

**Community grouping presets.** Dependabot can group packages but requires manual definition of every group. Renovate ships `monorepo:` presets that already know about `@radix-ui/*`, `@tanstack/*`, Spring Boot BOM, and hundreds of other monorepos. Several common groups are zero-config.

**Per-rule scheduling.** Renovate schedules apply globally, per manager, or per package rule. webstack uses `schedule:nonOfficeHours` for routine updates and `"at any time"` for security PRs. Dependabot's scheduling is an interval + optional day/time per `dependabot.yml` block with no security-only override.

**Dependency Dashboard.** Renovate opens a GitHub Issue listing every pending update with current/target versions and PR status. Dependabot has no equivalent.

**Merge confidence badges.** Each Renovate PR shows four signals — _Age_, _Adoption_, _Passing_, and _Confidence_ — sourced from Renovate's merge-confidence dataset. Dependabot shows one compatibility score badge.

**regexManager.** Renovate tracks `version = "..."` in `*.tf`, `FROM image:tag` in Dockerfiles, and plugin blocks in `build.gradle.kts` via custom regex. Dependabot has no equivalent for custom file patterns.

---

## webstack convention — `renovate.json` standard

All three repos share one structural convention: a common `extends` base, a `packageRules` array for group/schedule/auto-merge overrides, optional `customManagers` for non-standard files (infra only), and per-repo `ignorePaths` for generated code.

Shared `extends` value:

```json
"extends": [
  "config:recommended",
  ":dependencyDashboard",
  ":semanticCommits",
  ":separateMajorReleases",
  "schedule:nonOfficeHours"
]
```

| Preset | Effect |
|---|---|
| `config:recommended` | Renovate recommended defaults — lock file maintenance, SHA pinning for GitHub Actions (replaces the deprecated `config:base`) |
| `:dependencyDashboard` | Creates the dashboard issue |
| `:semanticCommits` | PR titles prefixed `chore(deps):` / `fix(deps):` — compatible with webstack commitlint |
| `:separateMajorReleases` | Major bumps get their own PRs, never grouped with minor/patch |
| `schedule:nonOfficeHours` | Batches non-urgent updates to weekends and outside 09:00–17:00 local |

---

## Group rules

Grouping reduces PR noise by bundling related packages into a single PR. The rule is: packages maintained together should be upgraded together.

### Frontend groups

| Group name | `matchPackageNames` |
|---|---|
| Radix UI primitives | `@radix-ui/**` |
| TanStack libraries | `@tanstack/**` |
| Next.js framework | `next`, `eslint-config-next` |
| React ecosystem | `react`, `react-dom`, `@types/react`, `@types/react-dom` |
| ESLint ecosystem | `eslint`, `eslint-**`, `@typescript-eslint/**` |
| Testing stack | `@testing-library/**`, `jest`, `jest-**`, `vitest`, `vitest-**` |

Each group is one PR. `matchPackageNames` accepts exact names and case-insensitive glob patterns (`@radix-ui/**`); the `**` suffix matches the whole namespace without false matches on packages that merely contain the string mid-name.

### Backend groups

| Group name | `matchPackageNames` |
|---|---|
| Spring Boot BOM | `org.springframework.**`, `io.spring.dependency-management` |
| Kotlin libraries | `org.jetbrains.kotlin.**` |
| Kotest | `io.kotest.**` |
| Mockk | `io.mockk.**` |

Spring Boot's BOM manages a large dependency graph under a single version. Grouping all `org.springframework.*` packages ensures the BOM and its managed dependencies upgrade together, which is the only safe upgrade path.

### Group naming convention

Group names follow the pattern `<Library/Framework> <category>` in title case (e.g. "Radix UI primitives", "Spring Boot BOM"). The PR title becomes `chore(deps): update <groupName>`. Keep names short enough to fit in a PR title at 72 characters. Full `packageRules` JSON for each group is embedded in the repo-specific configs below.

---

## Schedule

webstack uses two schedule tiers:

| Tier | When | Applied to |
|---|---|---|
| `schedule:nonOfficeHours` | Weekends + before 09:00 / after 17:00 local | All non-security updates |
| `"at any time"` | Immediately on advisory publication | `vulnerabilityAlerts` PRs |

`schedule:nonOfficeHours` is applied via the shared `extends` base. Security PRs bypass it by setting `"schedule": ["at any time"]` inside the `vulnerabilityAlerts` block (see Security PR priority section). `automerge: false` on vulnerability PRs is intentional — human review of blast radius is required before merge.

For teams that prefer a single weekly batch instead of the rolling off-hours drip, replace `schedule:nonOfficeHours` in `extends` with `"schedule": ["every weekend"]` in the `packageRules` entry. This opens all non-urgent PRs on Saturday morning as a reviewable group.

---

## Auto-merge policy

webstack's auto-merge strategy: **patch and digest updates auto-merge on green CI; minor and major updates require human review**.

| Update type | `automerge` | Notes |
|---|---|---|
| `patch`, `digest` | `true` | Squash-merge when all required checks pass |
| `minor` | `false` | Opens PR for review |
| `major` | `false` | Opens PR with `major-update` label |
| `github-actions` | `false` | Always manual; SHA pins carry elevated CI privilege |

### CI gate requirement

Auto-merge only proceeds when all required status checks pass. Configure via GitHub branch protection on `main`: add `lint`, `test-summary`, `build` as required checks (see `docs/infrastructure/ci-cd.md`). Without branch protection required checks, `automerge: true` merges immediately on PR creation — always pair it with required CI checks.

### GitHub Actions SHA pins

Renovate generates and maintains GitHub Actions SHA pins (`pinDigests: true` in `config:recommended`). These updates must never auto-merge: a malicious upstream SHA (supply chain compromise) could exfiltrate secrets from CI. Set `automerge: false` on `matchManagers: ["github-actions"]` in all three repos. See `docs/infrastructure/ci-cd.md` §Trivy for the 2026-03 supply chain incident context.

---

## regexManager

Renovate's `customManagers` field handles dependency tracking in files that no built-in manager understands. webstack uses it for three cases.

### Terraform provider versions

The built-in `terraform` manager handles `required_providers` blocks. For module `version` constraints outside that block, use a regex manager with inline annotations:

```hcl
# In *.tf — annotation comment immediately before the version string
# renovate: datasource=github-releases depName=hashicorp/terraform
version = "1.8.0"
```

The `matchStrings` pattern captures `datasource`, `depName`, and `currentValue` from the comment+assignment pair. Set `"versioningTemplate": "hashicorp"` for correct constraint parsing.

### Gradle plugin versions

The Kotlin DSL `plugins {}` block uses string literal versions that Gradle's built-in manager may not track. Use a regex manager targeting `build.gradle.kts` and `settings.gradle.kts` with annotation comments:

```kotlin
// In build.gradle.kts — add annotation comment on the line before version()
// renovate: datasource=gradle-version depName=org.springframework.boot:spring-boot-gradle-plugin
id("org.springframework.boot") version("3.2.5")
```

The corresponding `matchStrings` pattern captures `datasource`, `depName`, and `currentValue` from those comment+version pairs. Set `datasourceTemplate: "maven"` for Maven Central lookups.

### Dockerfile FROM tags

`config:recommended` includes the built-in `dockerfile` manager for standard locations. For non-standard Dockerfile paths, add a custom regex manager:

```json
{
  "customType": "regex",
  "managerFilePatterns": ["/(^|/)Dockerfile$/"],
  "matchStrings": ["FROM (?<depName>[^:]+):(?<currentValue>[^\\s@]+)"],
  "datasourceTemplate": "docker"
}
```

### RE2 regex note

Renovate uses the RE2 regex engine, which does not support lookahead, lookbehind, or backreferences. Use explicit named capture groups only.

---

## Security PR priority

Renovate integrates with GitHub Security Advisories (GHSA) to detect when a currently-installed version has a published CVE. Vulnerability PRs open independently of the regular batch schedule (see Schedule section for the `vulnerabilityAlerts` config block used in all three repos).

`prPriority: 10` floats security PRs to the top of the Renovate queue (default 0), ensuring the fix processes before queued routine updates.

**How detection works:** Renovate reads the lock file (`pnpm-lock.yaml`, `gradle.lockfile`) to determine exact installed versions, checks them against the GitHub Advisory Database, and opens a PR to the minimum safe version (not necessarily latest). The PR body includes the CVE ID, CVSS score, and affected range.

**Prerequisite:** Enable the **GitHub Dependency Graph** (Settings → Security → Dependency graph). For private repos, also enable **Dependabot alerts** — this activates the advisory feed Renovate reads; it does not require using Dependabot as the update bot.

---

## webstack repo-specific configs

All three repos share the same `extends` base (see webstack convention section) and `vulnerabilityAlerts` block (see Security PR priority section). The diff between them: auto-merge policy, group rules, and optional `customManagers`.

### Frontend (`*-frontend/renovate.json`)

Patch/digest auto-merge, `github-actions` pin rule, six frontend groups, and `ignorePaths` to exclude the generated OpenAPI SDK (`src/shared/api/generated/` — regenerate via `pnpm gen:api`):

```json
"ignorePaths": ["**/node_modules/**", "**/src/shared/api/generated/**"],
"packageRules": [
  { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
  { "matchUpdateTypes": ["minor", "major"], "automerge": false },
  { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true, "labels": ["dependencies", "github-actions"] },
  { "groupName": "Radix UI primitives", "matchPackageNames": ["@radix-ui/**"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "TanStack libraries", "matchPackageNames": ["@tanstack/**"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "Next.js framework", "matchPackageNames": ["next", "eslint-config-next"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "React ecosystem", "matchPackageNames": ["react", "react-dom", "@types/react", "@types/react-dom"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "ESLint ecosystem", "matchPackageNames": ["eslint", "eslint-**", "@typescript-eslint/**"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "Testing stack", "matchPackageNames": ["@testing-library/**", "jest", "jest-**", "vitest", "vitest-**"], "matchUpdateTypes": ["minor", "patch"] }
]
```

### Backend (`*-backend/renovate.json`)

Same auto-merge policy as frontend. `ignorePaths` excludes jOOQ-generated source (`build/generated-src/`):

```json
"ignorePaths": ["**/build/generated-src/**"],
"packageRules": [
  { "matchUpdateTypes": ["patch", "digest"], "automerge": true, "automergeType": "pr", "automergeStrategy": "squash" },
  { "matchUpdateTypes": ["minor", "major"], "automerge": false },
  { "matchManagers": ["github-actions"], "automerge": false, "pinDigests": true, "labels": ["dependencies", "github-actions"] },
  { "groupName": "Spring Boot BOM", "matchPackageNames": ["org.springframework.**", "io.spring.dependency-management"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "Kotlin libraries", "matchPackageNames": ["org.jetbrains.kotlin.**"], "matchUpdateTypes": ["minor", "patch"] },
  { "groupName": "Kotest", "matchPackageNames": ["io.kotest.**"], "matchUpdateTypes": ["minor", "patch"] }
]
```

### Infrastructure (`*-infrastructure/renovate.json`)

Auto-merge is **disabled for all update types** — infrastructure changes must go through `tofu plan` review regardless of semver magnitude. Use labels (`infra-patch`, `infra-minor`, `needs-review`) for triage.

```json
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
```

---

## Anti-patterns

**Global `automerge: true` without type scoping.** Merges major bumps automatically. Major versions introduce breaking API changes CI rarely covers. Always scope to `matchUpdateTypes: ["patch", "digest"]`.

**No groups — daily PR flood.** One PR per package update. A frontend repo with 80 dependencies produces 10–20 PRs per week, training engineers to ignore them. Group any ecosystem with three or more co-released packages.

**`lockFileMaintenance: { "enabled": false }`.** Disabling it lets `pnpm-lock.yaml` and `gradle.lockfile` drift, so transitive-only security fixes are never applied. `config:recommended` enables it by default.

**Unpinned `latest` Docker tags.** Renovate cannot track `latest`. Use explicit tags (`node:22-alpine`) or SHA digests.

**Schedule suppression on security PRs.** `"schedule": ["every weekend"]` on `vulnerabilityAlerts` means a Monday CVE waits until Saturday. Use `"at any time"`.

---

## Sources

- **Renovate configuration options reference:** https://docs.renovatebot.com/configuration-options/ — _authoritative_
- **Renovate default presets:** https://docs.renovatebot.com/presets-default/ — _authoritative_
- **Renovate regex custom manager:** https://docs.renovatebot.com/modules/manager/regex/ — _authoritative_
- **Renovate vs Dependabot comparison:** https://docs.renovatebot.com/bot-comparison/ — _authoritative_
- **Renovate GitHub App installation guide:** https://github.com/apps/renovate — _authoritative_
- **Mend Renovate community discussion — monorepo presets:** https://github.com/renovatebot/renovate/discussions — _community: renovatebot_

Last verified: 2026-06-22 (Renovate 39.X / GitHub App).
