# Conventional Commits

> Source: https://www.conventionalcommits.org/en/v1.0.0/

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Types (1차 webstack 사용)

| Type | Use |
|---|---|
| `feat` | New feature (user-visible behavior) |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Whitespace, formatting (no behavior change) |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvement |
| `test` | Adding/fixing tests |
| `build` | Build system, dependencies |
| `ci` | CI configuration |
| `chore` | Maintenance (deps, configs) |
| `revert` | Reverts a previous commit |

## Scopes (webstack-specific)

For plugin development:
- `meta` — `.claude-plugin/`, package.json, LICENSE, CHANGELOG.
- `commands` — `commands/*.md`.
- `skills` — `skills/<name>/SKILL.md` (e.g., `feat(skills/init): ...`).
- `agents` — `agents/<name>.md`.
- `shared` — any `shared/` content.
- `docs` — any `docs/` content (or use top-level `docs:` type for full docs PRs).
- `hooks` — `hooks/hooks.json`.
- `tests` — `tests/`.
- `ci` — `.github/`.

For projects scaffolded BY webstack:
- `domain` — domain layer changes.
- `app` — application layer.
- `infra` — infrastructure adapter.
- `api` — controller / endpoint.
- `ui` — frontend components/routes.
- `db` — schema migrations.

## Subject

- Imperative mood: "add", "fix", "remove" (not "added" / "adds").
- Lowercase first word (unless proper noun).
- No trailing period.
- ≤ 72 chars.

## Body

- Wraps at 72 chars.
- Blank line between subject and body.
- Explain WHY and what changed semantically (not what changed mechanically — diff shows that).

## Footer

- `BREAKING CHANGE: <description>` for breaking changes.
- `Refs: #<issue>` / `Closes: #<issue>`.
- `Co-authored-by: Name <email>` for pair work.

## Examples

```
feat(skills/feature): add P2.5 architect SubAgent invocation

Wires feature-architect SubAgent between plan-feature interview and
sync-contract phase. The architect proposes aggregate boundaries and
route mapping based on existing .webstack/contracts/ + identity.md.

Refs: #42
```

```
fix(agents/contract-drift-detective): handle springdoc 404 gracefully

When backend is not running, /v3/api-docs returns 404. Previously the
agent crashed; now it reports "backend not reachable" and aborts diff.

Closes: #61
```

```
chore(meta): bump plugin version to v0.2.0

BREAKING CHANGE: skills/build-be SKILL.md now requires Spring Modulith
1.2+. Existing projects must update build.gradle.kts.
```

## Commit hooks (optional, v2)

Tooling like `commitlint` + Husky `commit-msg` can enforce. 1차 webstack does not auto-install — manual discipline.

## References

- https://www.conventionalcommits.org/en/v1.0.0/
- Angular's commit message convention (predecessor).
