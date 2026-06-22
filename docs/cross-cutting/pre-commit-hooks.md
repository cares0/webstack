# Pre-Commit Hooks

> Reference for /webstack:init slash command and feature workflow.

Lefthook + commitlint + ktlint across all three webstack repos (frontend, backend, infrastructure). Catches formatting and commit-message issues at the moment of `git commit`, before anything reaches CI.

---

## What is webstack pre-commit

A webstack project spans three sibling git repositories that evolve together:

- `*-frontend` — Next.js / TypeScript / pnpm
- `*-backend` — Spring Boot / Kotlin / Gradle
- `*-infrastructure` — OpenTofu / HCL

Each repo gets an identical hook contract enforced by lefthook: the same lifecycle events (`pre-commit`, `commit-msg`) are wired in all three, but the tools invoked differ by language and toolchain. The purpose is to catch small, mechanical issues — wrong formatting, invalid commit subject — at commit time rather than in a CI run that takes minutes.

Problems caught early by pre-commit hooks:

| Problem | Repo | Tool |
|---|---|---|
| TypeScript / JSX formatting | frontend | Prettier |
| ESLint rule violations | frontend | ESLint |
| Kotlin style violations | backend | ktlint (via Gradle) |
| HCL formatting | infrastructure | `tofu fmt` |
| Commit subject format | all three | commitlint |

The hooks operate only on **staged files** — lefthook's default `staged_files` filter means you pay zero cost on files you did not touch. A full-project format sweep belongs in a dedicated `chore` commit, not in every pre-commit run.

---

## Why lefthook

Husky is the default choice for Node projects, but a webstack project is polyglot: the backend is Kotlin + Gradle, and the infrastructure repo has no Node at all. Installing Node in every repo just to get hook management is wasteful and fragile.

Lefthook solves this cleanly:

**Single binary, no runtime dependency.** Lefthook is distributed as a standalone binary (also available via npm, Homebrew, apt, etc.). A backend or infra developer who does not have Node installed locally can still get hooks by installing the binary directly, or via the package manager they already have.

**Polyglot by design.** A `lefthook.yml` hook entry is just a shell command — it can call `./gradlew ktlintFormat`, `pnpm run lint`, `tofu fmt`, or anything else. There is no Node-centric assumption in the configuration model.

**Speed.** Lefthook runs jobs in parallel by default and supports a `staged_files` glob filter to limit the working set. For a mixed-language repo, husky's sequential shell-script model is noticeably slower once you add Gradle invocations.

**Declarative config, not shell scripts.** Husky stores hooks as shell scripts in `.husky/`. Lefthook centralises everything in one `lefthook.yml`. This is easier to review in code and to override locally (`lefthook-local.yml`).

**CI reuse.** `lefthook run pre-commit` re-executes the exact same hook definition in CI without any additional wrapper. There is no separate CI lint script to maintain alongside the hook scripts.

The official lefthook documentation (see Sources) explicitly acknowledges polyglot projects as the primary motivation for the tool.

---

## webstack convention

### lefthook.yml structure

Each repo contains a `lefthook.yml` at its root. The top-level keys correspond to git lifecycle events. webstack uses two events:

- `pre-commit` — formatting tools that operate on staged files.
- `commit-msg` — commitlint, which reads the draft commit message from the `.git/COMMIT_EDITMSG` path passed by git as `{1}`.

### commitlint subject rules

All three repos enforce Conventional Commits 1.0. The rules are defined once in `commitlint.config.js` (frontend and infra) or in a root-level `commitlint.config.js` (backend, placed alongside `build.gradle.kts`).

Enforced constraints (sourced from `shared/conventions/conventional-commits.md`):

| Rule | Value |
|---|---|
| `type-enum` | `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert` |
| `scope-case` | lower-case |
| `subject-case` | lower-case (except proper nouns) |
| `subject-full-stop` | no trailing period |
| `header-max-length` | 72 characters |
| `body-leading-blank` | blank line between subject and body required |

Scopes are validated as a warn (not error) to keep the config permissive for cross-repo commits where scope conventions differ slightly (e.g. `ui`, `api`, `db` vs `meta`, `skills`). The scopes table in `shared/conventions/conventional-commits.md` is the canonical reference.

---

## Installation

### Frontend (`*-frontend`, pnpm)

Lefthook and commitlint are devDependencies:

```bash
pnpm add -D lefthook @commitlint/cli @commitlint/config-conventional
```

Register the hooks (writes git hook stubs into `.git/hooks/`):

```bash
pnpm exec lefthook install
```

Add to `package.json` scripts for convenience:

```json
{
  "scripts": {
    "prepare": "lefthook install"
  }
}
```

The `prepare` lifecycle hook means `pnpm install` automatically re-registers lefthook for any new clone. This is the recommended pattern for frontend.

### Backend (`*-backend`, Gradle + Kotlin)

The backend has no Node runtime requirement. Install lefthook via Homebrew (macOS) or as a binary:

```bash
# macOS
brew install lefthook

# Linux (manual binary)
curl -fsSL https://raw.githubusercontent.com/evilmartians/lefthook/master/install.sh | bash
```

Then register hooks from the repo root:

```bash
lefthook install
```

For commitlint in the backend repo, a minimal Node setup is acceptable — add a `package.json` at the repo root containing only the commitlint devDependency. This does not make the backend project a Node project; it is purely a tooling bootstrap:

```bash
npm init -y
npm install -D @commitlint/cli @commitlint/config-conventional
```

Alternatively, use a `npx`-based invocation in `lefthook.yml` if Node is available on the developer machine (see Configuration examples below).

### Infrastructure (`*-infrastructure`, OpenTofu)

Same pattern as backend — no Node runtime in the IaC repo:

```bash
brew install lefthook
lefthook install
```

For commitlint, the same minimal `package.json` approach applies. OpenTofu is already present for `tofu fmt`; no additional tooling install is needed for formatting.

---

## CI에서 같은 hook 재실행

Lefthook hooks run locally on developer machines. But a commit can be pushed without hooks firing if:

- The developer used `--no-verify` (an anti-pattern covered below).
- The repo was cloned on a machine where `lefthook install` was never run.
- A hook was installed after the commit was already made.

To defend against these gaps, CI re-executes the pre-commit hook against the changed files using lefthook's explicit run command:

```bash
lefthook run pre-commit
```

In CI (GitHub Actions), there is no staged-file context. Use `--force` to run all commands regardless of staged-file filtering:

```yaml
# .github/workflows/lint.yml (excerpt)
- name: Run lefthook pre-commit
  run: lefthook run pre-commit --force
```

`--force` tells lefthook to skip the `staged_files` check and run against all relevant files — appropriate in CI where the PR diff is the equivalent of "what was staged."

For `commit-msg` enforcement in CI, validate the PR title instead (it becomes the squash-merge commit subject on merge):

```bash
echo "$PR_TITLE" | npx commitlint
```

---

## Configuration examples

### Frontend — `lefthook.yml`

```yaml
# *-frontend/lefthook.yml
pre-commit:
  parallel: true
  jobs:
    - name: prettier
      glob: "**/*.{ts,tsx,js,jsx,json,css,md}"
      staged_files: true
      run: pnpm exec prettier --write {staged_files} && git add {staged_files}

    - name: eslint
      glob: "**/*.{ts,tsx,js,jsx}"
      staged_files: true
      run: pnpm exec eslint --fix {staged_files} && git add {staged_files}

commit-msg:
  jobs:
    - name: commitlint
      run: pnpm exec commitlint --edit {1}
```

Notes:

- `parallel: true` runs prettier and eslint concurrently.
- `staged_files: true` restricts each tool to the files staged for the current commit.
- After auto-fix (`--write` / `--fix`), the hook re-stages the modified files with `git add {staged_files}`. This ensures the auto-fixed version is what gets committed, not the pre-fix version.
- `{1}` in commit-msg is the path to the temporary commit message file git provides.

### Backend — `lefthook.yml`

```yaml
# *-backend/lefthook.yml
pre-commit:
  jobs:
    - name: ktlint-format
      glob: "**/*.{kt,kts}"
      staged_files: true
      run: ./gradlew ktlintFormat --quiet && git add {staged_files}

commit-msg:
  jobs:
    - name: commitlint
      run: npx --no-install commitlint --edit {1}
```

Notes:

- `ktlintFormat` is a Gradle task provided by the `jlleitschuh/ktlint-gradle` plugin (or equivalent setup). It runs ktlint with the `-F` auto-fix flag, correcting style violations in place.
- `--quiet` suppresses Gradle's verbose build output so hook output stays readable.
- The glob `**/*.{kt,kts}` covers both `.kt` source files and `.kts` Gradle script files.
- After Gradle modifies the files, `git add {staged_files}` re-stages them. Note that `{staged_files}` refers to the originally staged paths — if ktlint modifies a file, the change is staged back to the index.
- `npx --no-install commitlint` requires the minimal `package.json` + `node_modules` setup described in the Installation section.

### Infrastructure — `lefthook.yml`

```yaml
# *-infrastructure/lefthook.yml
pre-commit:
  jobs:
    - name: tofu-fmt
      glob: "**/*.tf"
      staged_files: true
      run: tofu fmt {staged_files} && git add {staged_files}

commit-msg:
  jobs:
    - name: commitlint
      run: npx --no-install commitlint --edit {1}
```

Notes:

- `tofu fmt` accepts a list of file paths and formats them in-place. Passing `{staged_files}` limits formatting to staged `.tf` files. Lefthook splits `{staged_files}` into individual paths, so multiple files are handled correctly.
- `tofu fmt` is idempotent — running it on an already-formatted file is a no-op.
- `*.tfvars` files are intentionally excluded from the glob (they contain values, not HCL structure, and are often in `.gitignore`).
- The commit-msg job is identical across all three repos — commitlint config is the shared convention.

---

## commitlint config

Place `commitlint.config.js` at the root of each repo. A single shared config covers all three repos because the Conventional Commits type set is the same everywhere.

```js
// commitlint.config.js
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Types — keep in sync with shared/conventions/conventional-commits.md
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'style',
        'refactor',
        'perf',
        'test',
        'build',
        'ci',
        'chore',
        'revert',
      ],
    ],
    // Header length (subject line)
    'header-max-length': [2, 'always', 72],
    // Subject must not end with a period
    'subject-full-stop': [2, 'never', '.'],
    // Subject must start lowercase (proper nouns are exceptions — warn only)
    'subject-case': [1, 'always', 'lower-case'],
    // Scope must be lowercase
    'scope-case': [2, 'always', 'lower-case'],
    // Blank line required between subject and body
    'body-leading-blank': [2, 'always'],
    // Blank line required between body and footer
    'footer-leading-blank': [1, 'always'],
  },
};
```

Rule severity:

- `2` = error (commit is rejected)
- `1` = warning (commit proceeds, violation is logged)
- `0` = disabled

`subject-case` is a warning (`1`) rather than an error (`2`) because the rule does not understand proper nouns. For example, `feat(api): add OAuth2 provider` would fail an error-level lower-case rule even though "OAuth2" is correct.

For ES module compatibility, either use `commitlint.config.mjs` as the filename, or ensure `package.json` contains `"type": "module"`. The config above uses `export default` syntax, which requires one of these conditions — commitlint has supported ESM config this way since v18 (no special Node version is required beyond a current LTS).

### Scopes

The `scope-enum` rule is intentionally omitted from the shared config. Scopes vary between repos:

- Frontend: `ui`, `api`, `app`, `entities`, `features`, `shared`
- Backend: `domain`, `app`, `infra`, `api`, `db`
- Infrastructure: `network`, `compute`, `storage`, `dns`, `iam`

To enforce scopes per repo, add a `scope-enum` rule at severity `1` (warn) in that repo's `commitlint.config.js`. Warn rather than error so new scopes don't block contributors before the list is updated:

```js
'scope-enum': [1, 'always', ['domain', 'app', 'infra', 'api', 'db']],
```

---

## Anti-patterns

### `--no-verify` bypass

```bash
# Never do this in normal workflow
git commit --no-verify -m "wip"
```

`--no-verify` skips all hooks — both `pre-commit` and `commit-msg`. It is tempting when a hook is slow or when you want to commit broken work in progress. The problems:

- The commit message is unvalidated; a typo in the subject type (`fixe:` instead of `fix:`) silently lands on the branch.
- Formatting violations accumulate and create noisy diffs in later commits.
- If CI re-runs lefthook, the build fails anyway — you have deferred the problem, not eliminated it.

The correct workflow for WIP commits is to use `git stash` or a dedicated `wip` branch that is rebased and cleaned before PR. If a hook is consistently too slow, the fix is to optimise the hook configuration, not to bypass it.

### Heavy builds in pre-commit

```yaml
# Anti-pattern: running tests in pre-commit
pre-commit:
  jobs:
    - name: test  # BAD — too slow
      run: ./gradlew test
```

Pre-commit hooks must be fast (under ~5 seconds total) to stay non-intrusive. Tests belong in CI (`push` event), not pre-commit. The only things appropriate for pre-commit are:

- **Auto-formatters** that modify staged files in place (Prettier, ktlint, tofu fmt).
- **Fast linters** that fail immediately on a rule violation without compiling the full program.

Compiling the Kotlin project (`./gradlew build`) or running the Jest test suite in pre-commit defeats the purpose: developers will disable the hook rather than wait.

### Lint in pre-push instead of pre-commit

```yaml
# Anti-pattern: deferring lint to pre-push
pre-push:
  jobs:
    - name: eslint
      run: pnpm run lint
```

`pre-push` fires when you push, which may be minutes or hours after you committed. By then you may have stacked multiple commits on top of the violation. Fixing it requires an interactive rebase or an additional fixup commit. Catching the same issue in `pre-commit` means you fix it before the commit is even recorded, keeping history clean.

The webstack model: **pre-commit for format/lint, CI for tests, pre-push for nothing** (or at most a quick `pnpm run typecheck` if type errors aren't caught by ESLint).

### Worktree hook installation

Run `lefthook install` once from the **main working tree** after cloning, not from inside a worktree. In a worktree `.git` is a file pointer, not a directory; hooks are shared from the main repo's `.git/hooks/` and do not need to be re-registered per worktree.

---

## Sources

- **Lefthook official documentation:** https://lefthook.dev/llms.txt — _authoritative_
- **Lefthook GitHub repository:** https://github.com/evilmartians/lefthook — _authoritative_
- **commitlint getting started guide:** https://commitlint.js.org/guides/getting-started.html — _authoritative_
- **ktlint Gradle integrations:** https://pinterest.github.io/ktlint/latest/install/integrations/ — _authoritative_
- **Conventional Commits 1.0 specification:** https://www.conventionalcommits.org/en/v1.0.0/ — _authoritative_
- **webstack `shared/conventions/conventional-commits.md`:** internal — _authoritative; bundled with this plugin_
- **jlleitschuh/ktlint-gradle plugin:** https://github.com/jlleitschuh/ktlint-gradle — _community: jlleitschuh_

Last verified: 2026-06-22 (lefthook 1.X / commitlint 19.X / ktlint 1.X).
