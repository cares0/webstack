# Release management

> Reference for /webstack:deploy slash command.
> ⚙️ **Optional integration** — activated via init's "Release management" question (`manifest.optional_integrations.release_management=true`). Until activated, this document is reference-only; setup steps live in `recipes/release-management-setup.md`.
> semver + Conventional Commits + git-cliff CHANGELOG + Vercel Rolling Releases for webstack's 3-repo layout.

---

## What is webstack releases

webstack coordinates releases across three sibling repos: `*-frontend` (Vercel, tag `fe/v1.2.3`), `*-backend` (OCI JAR, tag `be/v1.2.3`), and `*-infrastructure` (OpenTofu, tag `infra/v1.2.3`).

A _release_ is a coordinated version bump across all three in a single promotion event. All repos share the same MAJOR.MINOR.PATCH string so any feature can be traced through all three histories. The version triplet is tracked in `.webstack/manifest.yaml`; each repo generates its own `CHANGELOG.md` via git-cliff; a parent-level `RELEASES.md` cross-links all three.

Version 0.y.z covers pre-production; `1.0.0` marks the first production release. Conventional Commits are enforced from day one so the transition is seamless.

---

## Why this approach

Release management is Tier 3 opt-in because early-stage projects deploy from `main` continuously. Adding release ceremony before first production users creates overhead without value; `1.0.0` is the natural activation trigger.

All tool choices are free-tier compatible: git-cliff (Apache-2.0, zero hosting), Vercel Rolling Releases (available on Hobby), GitHub Actions tag-push triggers (< 30 s per release), and commitlint (local npm dev-dep). The existing commitlint `commit-msg` hook (see `docs/cross-cutting/pre-commit-hooks.md`) enforces Conventional Commits structurally — release management depends on clean commit history.

---

## semver + Conventional Commits

### Version number rules

Semantic Versioning 2.0.0 defines three components (`MAJOR.MINOR.PATCH`) with strict increment rules:

| Component | When to increment | Example trigger |
|---|---|---|
| `PATCH` | Backward-compatible bug fix | `fix: null pointer on empty cart` |
| `MINOR` | Backward-compatible new feature | `feat: add discount code support` |
| `MAJOR` | Incompatible API change | `feat!: rename /api/v1 to /api/v2` |

When MAJOR increments, MINOR and PATCH both reset to 0. When MINOR increments, PATCH resets to 0.

### Conventional Commits format

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

The commit types webstack uses and their semver mapping:

| Commit prefix | semver effect | Example |
|---|---|---|
| `fix:` | PATCH | `fix(auth): token expiry not refreshed` |
| `feat:` | MINOR | `feat(cart): add quantity stepper` |
| `feat!:` / `fix!:` | MAJOR | `feat!: drop support for Basic auth` |
| `BREAKING CHANGE:` footer | MAJOR | see below |
| `docs:` `chore:` `ci:` `test:` | no release | not user-visible |
| `perf:` `refactor:` | PATCH (conventional) | git-cliff groups separately |

### Breaking change annotation

Express a breaking change with `!` before the colon, or in a `BREAKING CHANGE:` footer (uppercase, space-separated — not hyphenated):

```
feat!: remove legacy XML API

BREAKING CHANGE: /api/xml removed. Migrate to /api/v2/json.
```

The `!` form is preferred for brevity; the footer form accommodates a longer migration note. Both trigger a MAJOR version bump.

commitlint enforces Conventional Commits format via the `commit-msg` hook. Setup: `docs/cross-cutting/pre-commit-hooks.md`.

---

## git-cliff CHANGELOG

### What git-cliff does

git-cliff is a changelog generator that processes Git history using Conventional Commits and regex-powered custom parsers. It reads commits between two tags, groups them by type, and renders a structured `CHANGELOG.md`. Version 2.13.0 is the latest stable release.

The canonical invocation:

```bash
git-cliff --tag v1.2.3 -o CHANGELOG.md
```

For a range since the last tag:

```bash
git-cliff --latest -o CHANGELOG.md
```

### `cliff.toml` standard configuration

Place `cliff.toml` at the repo root. webstack's standard config groups commits into four changelog sections and suppresses non-user-visible types:

```toml
[changelog]
header = """
# Changelog\n
All notable changes to this project will be documented in this file.\n
"""
body = """
{% if version %}\
## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
{% else %}\
## [unreleased]
{% endif %}\
{% for group, commits in commits | group_by(attribute="group") %}
### {{ group | upper_first }}
{% for commit in commits %}
- {% if commit.scope %}**{{ commit.scope }}**: {% endif %}{{ commit.message }}\
{% endfor %}
{% endfor %}\n
"""
trim = true
footer = ""

[git]
conventional_commits = true
filter_unconventional = true
split_commits = false
tag_pattern = "v[0-9].*"

commit_parsers = [
  { message = "^feat",     group = "Features"         },
  { message = "^fix",      group = "Bug Fixes"        },
  { message = "^perf",     group = "Performance"      },
  { message = "^refactor", group = "Refactoring"      },
  { message = "^docs|^style|^test|^chore|^ci|^build", skip = true },
  { breaking = true,       group = "Breaking Changes" },
]

filter_commits = false
sort_commits = "oldest"
```

### Tag-push trigger

git-cliff runs in GitHub Actions on every version tag push. Add `.github/workflows/changelog.yml` to the FE and BE repos with `on.push.tags: ['fe/v[0-9]*']` (backend uses `'be/v[0-9]*'`). The job checks out with `fetch-depth: 0` (full history required), installs git-cliff from the GitHub release tarball, runs `git-cliff --tag "${{ github.ref_name }}" -o CHANGELOG.md`, then commits the result back to `main` with `[skip ci]` in the message to prevent re-triggering CI. Grant `permissions: contents: write` on the job; add a `github-actions[bot]` bypass in branch protection or use a PAT.

---

## Vercel MCP integration

The Vercel MCP server (via `vercel-labs/agent-skills`) gives the `/webstack:deploy` SubAgent the ability to manage Rolling Releases and trigger Instant Rollback without leaving the Claude Code session. The relevant capabilities for release management are:

- **Promote deployment** — advance a Rolling Release to the next stage or complete it to 100%.
- **Instant Rollback** — revert production traffic to a prior deployment by deployment ID.
- **Check active rollout** — query current rolling release status (canary %, metrics delta).

### Vercel MCP invocation patterns (G1)

The Vercel MCP integration is available as the `mcp__claude_ai_Vercel__*` tool family. Authenticate once per session before running `/webstack:deploy` (`mcp__claude_ai_Vercel__authenticate`). During a deploy:

1. After a successful Vercel build, the agent calls `POST /v1/projects/{id}/rolling-release/approve-stage` to advance from stage 1 to 100% rather than navigating the dashboard.
2. If the BE health gate fails, the agent calls `POST /v1/projects/{id}/rollback/{deploymentId}` to revert the FE simultaneously, keeping FE and BE versions aligned.

---

## FE rolling release

### Configuration

Enable Rolling Releases at **Vercel Dashboard → Project Settings → Build & Deployment → Rolling Releases**. Configure two stages: Stage 1 at 10% (automatic on tag push) and Stage 2 at 100% (manual approve or automated health-gate pass).

Enable Skew Protection at **Project Settings → Deployment Protection → Skew Protection**. Without it users mid-rollout may receive a new HTML page paired with old API responses.

### Deployment marker

When a tag push triggers a Vercel build, set a deployment marker in the commit message so the rolling release can be traced back to a git-cliff CHANGELOG entry:

```bash
git tag fe/v1.2.3 -m "release: fe/v1.2.3"
git push origin fe/v1.2.3
```

Vercel picks up the tag push as a production promotion trigger if **Auto-assign Production Domain** is enabled (default). The new deployment enters Rolling Release stage 1 automatically.

### Canary observation window

Leave the canary at 10% for a minimum of 15 minutes. Observe **Speed Insights** delta in **Vercel → Observability → Rolling Releases** and your own error-rate dashboards (propagate `x-vercel-deployment-url` to distinguish canary vs stable traffic). A LCP or INP regression of > 10% is a rollback signal. Advance via the dashboard **Advance** button or the Vercel MCP `approve-stage` call.

### Canary abort

If the 10% canary shows regressions:

```bash
# CLI abort and revert to prior production deployment
vercel rollback [prior-deployment-id]
```

Or use the dashboard **Abort** button, which triggers Instant Rollback to the base deployment. After abort, `auto-assignment` of the production domain is paused. Re-enable it by promoting a clean deployment.

---

## BE blue-green-ish (single VM)

webstack runs the backend on a single Ampere A1 VM (OCI Always Free). True blue-green deployment requires two live VMs; webstack achieves a functional equivalent with a `current` symlink and an on-disk JAR archive at `/opt/app/releases/`.

### Artifact layout

```
/opt/app/
├── releases/
│   ├── app-20250501-120000.jar   ← oldest retained
│   ├── app-20250503-090000.jar
│   ├── app-20250503-140000.jar
│   ├── app-20250503-181500.jar
│   └── app-20250504-103000.jar   ← most recent
└── current -> /opt/app/releases/app-20250504-103000.jar
```

The five most recent JARs are retained; the sixth-oldest is pruned on every deploy, leaving four prior rollback targets available without a network download.

### systemd unit with version marker

```ini
[Unit]
Description=webstack backend
After=network.target

[Service]
User=opc
ExecStart=/usr/bin/java -jar /opt/app/current
Environment=APP_VERSION=1.2.3
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

`Environment=APP_VERSION=` is rewritten by the deploy workflow. The version is then visible in `systemctl status app` and in `/actuator/info` (requires `management.info.env.enabled=true` in `application.properties`).

### Deploy sequence

The `/webstack:deploy` GitHub Actions job executes these steps in order:

```bash
VERSION="1.2.3"
ARTIFACT="app-$(date -u +%Y%m%d-%H%M%S).jar"

# 1. Build and upload
./gradlew bootJar
scp build/libs/app.jar opc@"$OCI_VM_IP":/opt/app/releases/"$ARTIFACT"

# 2. Rewrite version marker in systemd unit, reload daemon
ssh opc@"$OCI_VM_IP" \
  "sudo sed -i 's/^Environment=APP_VERSION=.*/Environment=APP_VERSION=${VERSION}/' \
   /etc/systemd/system/app.service && sudo systemctl daemon-reload"

# 3. Swap symlink and restart
ssh opc@"$OCI_VM_IP" \
  "sudo ln -sfn /opt/app/releases/$ARTIFACT /opt/app/current && \
   sudo systemctl restart app"

# 4. Health gate — 3 retries × 10 s
for i in 1 2 3; do
  sleep 10
  curl -fsS "http://$OCI_VM_IP:8080/actuator/health" | grep -q '"status":"UP"' && break
  if [ "$i" -eq 3 ]; then
    PREV=$(ssh opc@"$OCI_VM_IP" "ls -t /opt/app/releases/app-*.jar | sed -n '2p'")
    ssh opc@"$OCI_VM_IP" \
      "sudo ln -sfn $PREV /opt/app/current && sudo systemctl restart app"
    exit 1   # marks Actions job failed; agent triggers FE Instant Rollback
  fi
done

# 5. Prune — keep newest 5
ssh opc@"$OCI_VM_IP" \
  "ls -t /opt/app/releases/app-*.jar | tail -n +6 | xargs -r sudo rm --"
```

Health gate failure at step 4 triggers automatic rollback to the prior JAR (step `sed -n '2p'` selects the second-newest) and exits with code 1. The `/webstack:deploy` agent then invokes Instant Rollback on the Vercel side to keep FE and BE versions aligned.

---

## 3-repo version sync

### Manifest tracking

`.webstack/manifest.yaml` is the source of truth for the current version triplet, committed to the parent workspace repo (not to any sibling repo):

```yaml
current_versions:
  frontend: "1.2.3"
  backend:  "1.2.3"
  infra:    "1.2.3"
last_release:
  date: "2026-05-04"
  git_sha:
    frontend: "abc1234"
    backend:  "def5678"
    infra:    "ghi9012"
```

### Tag order and drift detection

Tags are pushed in order: `infra/v1.2.3` → `be/v1.2.3` → `fe/v1.2.3`. This guarantees each layer is healthy before the next is exposed. The full release flow:

```
/webstack:deploy "1.2.3"
  ├── infra: tofu apply (if changed) → tag infra/v1.2.3
  ├── backend: deploy JAR → health gate → tag be/v1.2.3
  └── frontend: push fe/v1.2.3 → Vercel rolling release (canary → approve)
manifest updated; RELEASES.md cross-links generated
```

If a partial failure leaves the manifest with mismatched versions, `/webstack:deploy` detects the drift on the next run and prompts for reconciliation before proceeding.

---

## Hotfix branches

### Policy

A hotfix is a PATCH-level release that bypasses the normal feature-branch → PR → main cycle. Use hotfix branches when a critical bug in production must be patched immediately without including in-progress `main` changes.

```
Branch naming: hotfix/<version>
Example:       hotfix/1.2.4
```

### Workflow

```bash
# Branch from the last release tag — not from main
git checkout -b hotfix/1.2.4 be/v1.2.3

# Apply one minimal fix commit
git commit -m "fix(auth): session token not invalidated on logout"

# Tag and push (triggers CHANGELOG + deploy)
git tag be/v1.2.4 -m "hotfix: be/v1.2.4"
git push origin hotfix/1.2.4 be/v1.2.4

# Merge back to main (--ff-only keeps history linear)
git checkout main && git merge --ff-only hotfix/1.2.4
git push origin main

# Clean up
git branch -d hotfix/1.2.4 && git push origin --delete hotfix/1.2.4
```

### Fast-forward and multi-repo coordination

Hotfix branches merge back to `main` via `--ff-only`. If main has diverged, rebase the hotfix onto the current tip first (`git rebase main hotfix/1.2.4`), then `git merge --ff-only`. This keeps git history linear for git-cliff.

Not all hotfixes touch all three repos. If only BE and FE are affected, tag only `be/v1.2.4` and `fe/v1.2.4`; leave `infra` at `v1.2.3`. Update the manifest to reflect the asymmetric bump (`infra: "1.2.3"`, `backend: "1.2.4"`, `frontend: "1.2.4"`).

---

## Anti-patterns

**Manual CHANGELOG editing.** Hand-editing `CHANGELOG.md` diverges from git history and breaks git-cliff's deterministic regeneration. Any correction belongs in a `docs:` commit, not in the file directly.

**Ignoring semver.** Date tags (`v2026-05-04`) or sequential integers (`v47`) make it impossible to express compatible version ranges. Use `MAJOR.MINOR.PATCH` from day one.

**Hotfix directly to main without a tag.** An untagged hotfix never appears in the CHANGELOG and cannot be rolled back by version. Always tag before deploying, even a single-line fix.

**Skipping the canary stage.** Force-promoting from 0% to 100% defeats Rolling Releases. A regression at 10% costs an order of magnitude less than one at 100%.

**Releasing FE before BE is healthy.** A FE that references a broken BE produces immediate user-visible errors. Always confirm the BE health gate before pushing the FE tag.

**Bumping MAJOR for internal refactors.** MAJOR is for incompatible API surface changes visible to callers. An internal restructure that does not change the HTTP contract is at most MINOR.

---

## Sources

- **git-cliff documentation:** https://git-cliff.org/docs/ — _authoritative_
- **Vercel Rolling Releases:** https://vercel.com/docs/rolling-releases — _authoritative_
- **Vercel Instant Rollback:** https://vercel.com/docs/instant-rollback — _authoritative_
- **Conventional Commits 1.0 specification:** https://www.conventionalcommits.org/en/v1.0.0/ — _authoritative_
- **Semantic Versioning 2.0.0:** https://semver.org/ — _authoritative_
- **Vercel agent-skills (Claude Code plugin):** https://github.com/vercel-labs/agent-skills — _community: Vercel-affiliated, MIT licensed_

Last verified: 2026-05-04 (git-cliff 2.X / Vercel Rolling Releases GA / Conventional Commits 1.0).
