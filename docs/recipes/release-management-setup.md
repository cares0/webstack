# Recipe — Release management setup (git-cliff + Vercel Rolling Releases)

> Setup walkthrough for activating webstack release management. Triggered when init's "Release management" question is answered Yes (`manifest.optional_integrations.release_management=true`). Recommended after first production deployment.
> Reference doc: `docs/infrastructure/release-management.md`.

## What this recipe activates

| Component | Role |
|---|---|
| **git-cliff 2.X** | Generates `CHANGELOG.md` per repo from Conventional Commits history |
| **GitHub Actions release workflow** | Tag-push trigger → CHANGELOG update → GitHub Release creation |
| **Vercel Rolling Releases** | Canary traffic splitting (10% → 100%) on every FE tag push |
| **commitlint via lefthook** | `commit-msg` hook enforces Conventional Commits format |
| **3-repo version sync** | `manifest.yaml` tracks the coordinated version triplet |

## Pre-conditions

- First production deployment complete — FE on Vercel, BE JAR running on OCI VM.
- Vercel project linked to the `<project>-frontend` GitHub repo.
- All three repos (`*-frontend`, `*-backend`, `*-infrastructure`) exist on GitHub.
- `.webstack/manifest.yaml` present in the parent workspace directory.
- `lefthook` installed in all three repos (ships with `webstack init`).

## Step 1 — git-cliff install

```bash
cargo install git-cliff          # Option A — Cargo
brew install git-cliff           # Option B — Homebrew
# Option C — binary (no toolchain)
V=2.13.1
curl -sSL "https://github.com/orhun/git-cliff/releases/download/v${V}/git-cliff-${V}-x86_64-unknown-linux-gnu.tar.gz" \
  | tar -xz --strip-components=1 -C ~/.local/bin git-cliff-${V}/git-cliff
```

Verify: `git-cliff --version`. CI runners use Option C inside the release workflow (Step 4).

## Step 2 — `cliff.toml`

Place `cliff.toml` at the root of each repo. All three repos use the same file — plain `v1.2.3` tags (no `fe/`/`be/`/`infra/` prefix):

```toml
[changelog]
header = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n"
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
  { breaking = true,       group = "Breaking Changes" },
  { message = "^feat",     group = "Features"         },
  { message = "^fix",      group = "Bug Fixes"        },
  { message = "^perf",     group = "Performance"      },
  { message = "^refactor", group = "Refactoring"      },
  { message = "^docs|^style|^test|^chore|^ci|^build", skip = true },
]
filter_commits = false
sort_commits = "oldest"
```

```bash
touch CHANGELOG.md
git add cliff.toml CHANGELOG.md
git commit -m "chore: add git-cliff config"
```

## Step 3 — Conventional Commits hook

commitlint via `lefthook`'s `commit-msg` hook ships with `webstack init`. Verify it is active:

```bash
lefthook run commit-msg --commit-msg-file <(echo "feat: test message")   # exit 0
lefthook run commit-msg --commit-msg-file <(echo "WIP broken")           # exit 1
```

If absent: `npm install --save-dev @commitlint/cli @commitlint/config-conventional lefthook && lefthook install`.

Cross-link: `docs/cross-cutting/pre-commit-hooks.md` — full config, rule set, bypass guidance.

## Step 4 — Release workflow

Add `.github/workflows/release.yml` to each of the three repos:

```yaml
name: Release

on:
  push:
    tags:
      - 'v[0-9]*'

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # full history required by git-cliff

      - name: Install git-cliff
        run: |
          V=2.13.1
          curl -sSL "https://github.com/orhun/git-cliff/releases/download/v${V}/git-cliff-${V}-x86_64-unknown-linux-gnu.tar.gz" \
            | tar -xz --strip-components=1 -C /usr/local/bin git-cliff-${V}/git-cliff

      - name: Generate + commit CHANGELOG
        run: |
          git-cliff --tag "${{ github.ref_name }}" -o CHANGELOG.md
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add CHANGELOG.md
          git diff --staged --quiet || git commit -m "docs: update CHANGELOG for ${{ github.ref_name }} [skip ci]"
          git push origin HEAD:main

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body_path: CHANGELOG.md
          make_latest: true
```

Commit `release.yml` to `main` in all three repos before pushing the first version tag. Add a `github-actions[bot]` branch protection bypass (or use a PAT as `GH_RELEASE_TOKEN`) if `main` has push restrictions.

## Step 5 — Vercel Rolling Releases activate

1. **Vercel Dashboard → [Project] → Project Settings → Build & Deployment → Rolling Releases → On.**
2. Configure two stages: Stage 1 at **10%** (automatic), Stage 2 at **100%** (manual Advance).
3. **Save.**
4. Enable **Skew Protection**: same Settings page → Deployment Protection → Skew Protection → On. Without it, users mid-rollout may receive a new HTML page paired with old API responses.

Once enabled, any production-promoting action enters stage 1 at 10% automatically. Advance or abort via the **Rolling Releases** banner on the Deployments tab, or programmatically via `mcp__claude_ai_Vercel__*` tools during `/webstack:deploy`.

## Step 6 — 3-repo version sync

webstack uses _plain_ `v1.2.3` tags in every repo — not `fe/v1.2.3` or `be/v1.2.3`. This keeps `tag_pattern = "v[0-9].*"` consistent across all `cliff.toml` files.

Tag push order: **infra → backend → frontend**. Each layer confirmed healthy before the next is exposed.

Update `.webstack/manifest.yaml` after every release (all three SHAs + date):

```yaml
current_versions: { frontend: "0.1.0", backend: "0.1.0", infra: "0.1.0" }
last_release:
  date: "2026-05-04"
  git_sha: { frontend: "<sha>", backend: "<sha>", infra: "<sha>" }
```

```bash
git -C <parent-dir> add .webstack/manifest.yaml
git -C <parent-dir> commit -m "chore: release v0.1.0"
```

## Step 7 — Verify

```bash
# Push first tag across all three repos (infra → backend → frontend)
git tag v0.1.0 -m "release: v0.1.0" && git push origin v0.1.0
```

Expected outcomes after all three tags are pushed:

- GitHub Actions release workflows green for all three repos.
- `CHANGELOG.md` on `main` updated with Features / Bug Fixes sections.
- GitHub Releases page shows `v0.1.0` with CHANGELOG body.
- Vercel Deployments shows **Canary** badge at 10%; Observability → Rolling Releases shows metrics comparison.

After a minimum 15-minute canary window, click **Advance** to promote to 100%.

## Step 8 — manifest flag ON

```yaml
# .webstack/manifest.yaml
optional_integrations:
  release_management: true
```

```bash
git -C <parent-dir> add .webstack/manifest.yaml
git -C <parent-dir> commit -m "chore: enable release_management integration"
```

This flag signals to `/webstack:feature` and `/webstack:deploy` that release management is live.

## Reference doc

`docs/infrastructure/release-management.md` — semver rules, Conventional Commits type mapping, `cliff.toml` standard config, Vercel MCP integration, BE blue-green deploy sequence, hotfix policy, anti-patterns.

## Sources

- **git-cliff installation:** https://git-cliff.org/docs/installation/ — _authoritative_
- **git-cliff (Orhun Parmaksız):** https://github.com/orhun/git-cliff — _community: Apache-2.0 / MIT, maintained by Orhun Parmaksız_
- **Vercel Rolling Releases:** https://vercel.com/docs/rolling-releases — _authoritative_
- **Conventional Commits 1.0 specification:** https://www.conventionalcommits.org/en/v1.0.0/ — _authoritative_

Last verified: 2026-05-04 (git-cliff 2.X / Vercel Rolling Releases GA / Conventional Commits 1.0).
