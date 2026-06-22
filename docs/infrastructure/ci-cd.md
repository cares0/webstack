# GitHub Actions CI/CD

> Reference for /webstack:infra and /webstack:deploy slash commands and tofu-plan-analyzer SubAgent.

CI/CD for the webstack 3-repo layout (FE/BE/Infra). **Phase 1** (Tier 1, always) covers lint, type-check, test, and build. **Phase 2** (Tier 2, opt-in) adds OIDC, CodeQL, Trivy, and Renovate gates. Phase 1 is sufficient for production; Phase 2 reduces attack surface for team-scale work.

---

## What is webstack CI/CD

webstack manages three sibling git repositories:

| Repo | Stack | Artifact |
|---|---|---|
| `*-frontend` | Next.js 16 + pnpm | Vercel deployment |
| `*-backend` | Spring Boot 4 + Gradle | OCI Compute JAR |
| `*-infrastructure` | OpenTofu | State in OCI Object Storage |

Each repo owns `.github/workflows/`. Shared reusable workflows use a `_*.yml` prefix (callable only). The infra repo also holds the `tofu plan` workflow invoked by `/webstack:infra`.

CI runs on push to `main` and on PRs targeting `main`. Goal: lint + type-check under 90 s; full test suite gates the merge.

---

## Why GitHub Actions

- **Free tier** — 2,000 min/month private repos. FE ≈ 3 min + BE ≈ 4 min + Infra ≈ 1 min fits solo/small-team usage.
- **OIDC** — Native OpenID Connect exchange with Vercel and OCI; short-lived per-job tokens replace long-lived secrets.
- **Reusable workflows** — `workflow_call` factors lint/test/build. All three repos call the same `_lint.yml`.
- **Ecosystem** — First-party or widely-adopted actions for Gradle, pnpm, Java, OpenTofu, CodeQL, Trivy.
- **Branch protection** — Required status checks wire directly to PR merge gates.

---

## Phase 1 — Baseline workflow (Tier 1, 항상)

Every webstack project ships with these workflows from day one. SHA pins shown below are examples; pin to the latest release SHA and keep them current via Renovate (see Phase 2).

### Frontend CI (`*-frontend/.github/workflows/ci.yml`)

All FE jobs share the same three-step setup: `actions/checkout`, `pnpm/action-setup` (version: 9), `actions/setup-node` (node-version: 22, cache: pnpm). The `cache: pnpm` key hashes `pnpm-lock.yaml`; lock file changes auto-bust the cache. Pin each action by SHA — the typecheck job below shows the canonical pattern; apply identically to test and build.

```yaml
name: FE CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: fe-ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint:
    uses: ./.github/workflows/_lint.yml

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: pnpm/action-setup@a3252b7022e6e49803e7c4c7b1c48da20d7bbf2e # v4.1.0
        with:
          version: 9
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile && pnpm typecheck

  # test: same setup + `pnpm test --passWithNoTests`
  # build: same setup + `pnpm build`, needs: [lint, typecheck, test]
```

### Backend CI (`*-backend/.github/workflows/ci.yml`)

The default runs tests on **Java 21 LTS** — the webstack runtime baseline (Spring Boot 4 supports 17/21/25; 21 is a safe current LTS). The job is written as a matrix so you can opt into extra versions (e.g., add `25` when you want to validate the next LTS before adopting it), but the default is a single-version run, not a 3-way 17/21/25 matrix. A `test-summary` aggregation job is the single required check for branch protection, so adding or removing a matrix entry never changes the branch-protection check name (`test (21)`, etc.).

```yaml
name: BE CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: be-ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint:
    uses: ./.github/workflows/_lint.yml

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        java: [21]          # default: single LTS. Add 25 (e.g. [21, 25]) only when validating the next LTS.
      fail-fast: false
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-java@c5195efecf7bdfc987ee8bae7a71cb8b11521c00 # v4.7.1
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
      - uses: gradle/actions/setup-gradle@06832c7b30a0129d7fb559bcc6e43d26f6374244 # v4.3.1
      - run: ./gradlew test

  test-summary:
    runs-on: ubuntu-latest
    needs: [test]
    if: always()
    steps:
      - run: |
          [[ "${{ needs.test.result }}" == "success" ]] || exit 1

  build:
    runs-on: ubuntu-latest
    needs: [lint, test-summary]
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-java@c5195efecf7bdfc987ee8bae7a71cb8b11521c00 # v4.7.1
        with:
          distribution: temurin
          java-version: 21
      - uses: gradle/actions/setup-gradle@06832c7b30a0129d7fb559bcc6e43d26f6374244 # v4.3.1
      - run: ./gradlew build -x test
```

`gradle/actions/setup-gradle` handles Gradle home caching automatically (wrapper JARs, dependency cache, build cache). It replaces the legacy `gradle/gradle-build-action`. `fail-fast: false` surfaces cross-version regressions in one run instead of canceling on first failure.

### Infrastructure CI (`*-infrastructure/.github/workflows/ci.yml`)

```yaml
name: Infra CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: opentofu/setup-opentofu@592200b631e4c7ed7dd77f61701eac87a9e13d98 # v1.0.5
        with:
          tofu_version: 1.10.0
      - run: tofu init -backend=false
      - run: tofu fmt --check --recursive
      - run: tofu validate
```

No cloud credentials are needed for `tofu validate`.

---

## Reusable workflows

Shared workflows reduce duplication. Each repo carries its own copy because reusable workflows must reside in the same repo as the caller (unless using the `org/repo/.github/workflows/file.yml@ref` form for cross-repo calls).

### `_lint.yml`

```yaml
# .github/workflows/_lint.yml
name: Lint (reusable)
on:
  workflow_call:
    inputs:
      node-version:
        type: string
        default: "22"
        required: false
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: pnpm/action-setup@a3252b7022e6e49803e7c4c7b1c48da20d7bbf2e # v4.1.0
        if: ${{ hashFiles('pnpm-lock.yaml') != '' }}
        with:
          version: 9
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        with:
          node-version: ${{ inputs.node-version }}
          cache: ${{ hashFiles('pnpm-lock.yaml') != '' && 'pnpm' || '' }}
      - run: |
          if [ -f "pnpm-lock.yaml" ]; then
            pnpm install --frozen-lockfile && pnpm lint
          elif [ -f "gradlew" ]; then ./gradlew ktlintCheck
          fi
```

Apply the same pattern for `_test.yml` (expose `java-version` string input) and `_build.yml` (expose `skip-tests` boolean).

**Permissions policy:** Declare `permissions: contents: read` in every reusable workflow. GitHub enforces permissions can only be maintained or reduced across a call chain. A callable workflow needing `id-token: write` (Phase 2) must declare it itself.

---

## Phase 2 — Hardening (Tier 2, 자율 적용)

Phase 2 is opt-in. Apply when the project serves real users or grows beyond a solo team. Each item is independent; adopt in any order. Checklist: OIDC for Vercel, OIDC for OCI, CodeQL for FE TypeScript, CodeQL for BE Kotlin, Trivy container scanning (SHA-pinned), Renovate auto-merge gate.

---

## OIDC 전환

Long-lived secrets stored in GitHub Secrets are permanently valid. A runner memory dump, log leak, or supply-chain compromise exposes them. OIDC replaces them with short-lived tokens that GitHub mints per-job; the cloud provider validates the JWT before issuing a scoped access token. Credential lifetime: seconds, not months.

### Vercel OIDC

Vercel OIDC federation is available on Pro/Enterprise only. Hobby tier must continue using `VERCEL_TOKEN` (scoped to project, annual rotation).

For Pro/Enterprise: In Vercel dashboard → Team Settings > Security > Identity Providers, add an OIDC provider with issuer `https://token.actions.githubusercontent.com` and subject `repo:<org>/<repo>:ref:refs/heads/main`. In the workflow, add `id-token: write` and use `actions/github-script` to call `core.getIDToken('vercel.com')`, then exchange the returned JWT for a short-lived Vercel token via the Vercel REST API token-exchange endpoint before running `vercel deploy --token <short-lived>`.

### OCI CI authentication (key-based)

OCI does not have a widely-available first-party GitHub Actions OIDC action. webstack uses **API key-based authentication** in CI: the private key, fingerprint, user OCID, tenancy OCID, and region are stored as GitHub Secrets and injected into the OCI CLI config at job start.

```yaml
jobs:
  deploy-be:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    environment: production
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - name: Configure OCI CLI
        run: |
          mkdir -p ~/.oci
          echo "[DEFAULT]" > ~/.oci/config
          echo "user=${{ secrets.OCI_USER_OCID }}" >> ~/.oci/config
          echo "tenancy=${{ secrets.OCI_TENANCY_OCID }}" >> ~/.oci/config
          echo "region=${{ secrets.OCI_REGION }}" >> ~/.oci/config
          echo "key_file=~/.oci/oci_api_key.pem" >> ~/.oci/config
          echo "fingerprint=${{ secrets.OCI_FINGERPRINT }}" >> ~/.oci/config
          echo "${{ secrets.OCI_PRIVATE_KEY }}" > ~/.oci/oci_api_key.pem
          chmod 600 ~/.oci/oci_api_key.pem
      - run: ./gradlew bootJar
```

Rotate `OCI_PRIVATE_KEY` and `OCI_FINGERPRINT` annually. Scope the IAM policy to the minimum compartment and object operations needed for deployment.

---

## Concurrency groups

For CI jobs, cancel superseded runs to save minutes:

```yaml
concurrency:
  group: ci-${{ github.ref }}-${{ github.workflow }}
  cancel-in-progress: true
```

For deploy jobs, serialize but never cancel mid-flight:

```yaml
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false   # partial deploy state is worse than queuing
```

Place the `concurrency` key at the workflow level (outside `jobs`) so it applies to the whole workflow, not a single job.

---

## Branch protection + required checks

In each repo: **Settings > Branches > Add rule** for `main`. Enable:

- **Require status checks** — add `lint`, `test-summary` (BE aggregation job), `build`.
- **Require branches up to date** — prevents stale-branch merges.
- **Require PR reviews** (≥ 1 for team projects).
- **Do not allow bypassing** — blocks admin force-merges.

Use `test-summary` rather than per-entry names (`test (17)`, `test (21)`). This avoids updating branch protection when the matrix changes.

---

### Phase 2 detailed: security scanning

#### CodeQL

Add `.github/workflows/codeql.yml` to each repo. Use language `javascript-typescript` for FE and `java-kotlin` for BE. Schedule a weekly scan in addition to push/PR triggers. Required permissions: `contents: read`, `security-events: write`.

```yaml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'
permissions:
  contents: read
  security-events: write
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: github/codeql-action/init@45775bd8235c68ba998cffa5171334d58593da47 # v3.28.15
        with:
          languages: javascript-typescript
      - uses: github/codeql-action/autobuild@45775bd8235c68ba998cffa5171334d58593da47 # v3.28.15
      - uses: github/codeql-action/analyze@45775bd8235c68ba998cffa5171334d58593da47 # v3.28.15
```

Results appear in Security > Code scanning. Add `codeql` to required checks to block merges on critical/high findings.

#### Trivy — SHA pinning required

> **Warning (2026-03 supply chain incident — verify the specifics):** On (reportedly) March 19, 2026, attackers force-pushed malicious code to 75 of 76 version tags in `aquasecurity/trivy-action`. The attack persisted for ~12 hours and exfiltrated secrets from GitHub-hosted runners by dumping the runner process heap. Projects referencing the action by tag were exposed; projects pinned to a commit SHA were not. (verify the date and exact details against the linked source before quoting them — see Sources.) Regardless of the incident specifics, the lesson holds: **always pin third-party actions by commit SHA, never by tag.**

```yaml
# Vulnerable — tag is mutable
- uses: aquasecurity/trivy-action@v0.34.2

# Safe — commit SHA is immutable
- uses: aquasecurity/trivy-action@57a97c7e7821a5776cebc9bb87c984fa69cba8f1 # v0.35.0
```

Container scan workflow: build the image as `app:${{ github.sha }}`, invoke `aquasecurity/trivy-action` (SHA-pinned, see above) with `format: sarif`, `severity: CRITICAL,HIGH`, `exit-code: 1`, then upload SARIF via `github/codeql-action/upload-sarif` with `if: always()`. Set `permissions: security-events: write` on the job.

#### Renovate auto-merge gate

Add `renovate.json` at repo root with `"extends": ["config:recommended"]` (`config:base` is deprecated). In `packageRules`:

- `matchUpdateTypes: ["patch"]` + `automerge: true` — patch bumps merge automatically once CI passes.
- `matchUpdateTypes: ["minor", "major"]` + `automerge: false` — opens PRs for review.
- `matchManagers: ["github-actions"]` + `pinDigests: true` + `automerge: false` — Renovate keeps action SHA pins current and labels the PRs `dependencies, github-actions`. Review manually since these carry elevated CI privilege.

---

## Anti-patterns

**Tag references instead of SHA pins.** Tags are mutable — any upstream write can force-push to a malicious commit, as in the 2026-03 Trivy incident. Pin all third-party actions by commit SHA.

```yaml
- uses: actions/checkout@v4                                        # wrong
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2 — correct
```

**Long-lived cloud secrets instead of OIDC.** `VERCEL_TOKEN` and OCI API keys are valid for months or years. Any runner memory dump or dependency compromise exposes them permanently. Migrate to OIDC (Phase 2) where the cloud provider supports it.

**`pull_request_target` with untrusted input.** This trigger has write permissions and secret access even for fork PRs. The 2026-03 Trivy incident originated from a `pull_request_target` workflow that let a fork PR steal an org-scoped PAT. Never check out or execute fork code inside this trigger. Use `pull_request` for untrusted contributions.

**`cancel-in-progress: true` on deploy jobs.** Canceling mid-flight leaves infrastructure partially updated. Use it only for pure CI jobs; deploy workflows need `false` (see Concurrency groups).

**Broad permissions at workflow level.** Declare `permissions` per job and grant only what is needed (`contents: read`, `id-token: write`, `security-events: write`). Least privilege applies to `GITHUB_TOKEN` the same as to IAM roles.

---

## Sources

- **GitHub Actions OIDC documentation:** https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect — _authoritative_
- **GitHub Actions reusable workflows:** https://docs.github.com/en/actions/sharing-automations/reusing-workflows — _authoritative_
- **Trivy GitHub Actions supply chain compromise (March 2026):** https://snyk.io/articles/trivy-github-actions-supply-chain-compromise/ — _community: Snyk security research_
- **Vercel agent skills:** https://github.com/vercel-labs/agent-skills — _community: vercel-labs_
- **OCI Workload Identity Providers:** https://docs.oracle.com/en-us/iaas/Content/Identity/workloadidentity/manage-identity-domains-workload-identity-providers.htm — _authoritative_
- **gradle/actions setup-gradle:** https://github.com/gradle/actions/blob/main/setup-gradle/README.md — _authoritative_

Last verified: 2026-06-22 (GitHub Actions / actions/checkout@v4 / actions/setup-java@v4 / setup-node@v4 / pnpm/action-setup@v4).
