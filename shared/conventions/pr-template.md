# PR Template & Checklist

## Title format

`<type>(<scope>): <subject>`

Mirror the squash commit subject. See `conventional-commits.md`.

## Body sections

```markdown
## What

<2-3 sentences on the visible change. What does the user/consumer notice?>

## Why

<context: ticket link, design doc, decision rationale. If pure cleanup, say so.>

## How

<approach summary, key trade-offs, anything reviewer should focus on>

## Cross-repo links

- Backend PR: <url or "n/a">
- Frontend PR: <url or "n/a">
- Infrastructure PR: <url or "n/a">

## Contract version

- contracts/<feature>.yaml: <semver from info.version>

## Verification

- [ ] Tests added/updated. Coverage reasonable.
- [ ] `contract-drift-detective` clean (no Critical findings).
- [ ] `code-reviewer` review applied.
- [ ] Manual smoke test on local dev (steps below).

### Manual smoke

<step-by-step reproduction>

## Risks / rollback

<what breaks if this is wrong; how to revert>

## Screenshots / recordings (if UI)

<embed>
```

## Checklist (auto-attached to feature P8 PR)

- [ ] Branch follows `feature/<name>` naming.
- [ ] Conventional Commit subject.
- [ ] No `console.log` / `dbgPrintln` / `TODO without owner` left.
- [ ] No secrets, tokens, private URLs in code or commits.
- [ ] OpenAPI contract version bumped (if API changed).
- [ ] Database migration tested on copy of prod data (if schema changed).
- [ ] Cross-repo PRs linked.
- [ ] CHANGELOG updated (user-visible changes).

## Reviewer focus points

For backend reviewers:

- Domain layer free of Spring/JPA imports?
- Aggregate invariants enforced in entity, not service?
- Repository methods aggregate-scoped?

For frontend reviewers:

- Server / Client component boundary intentional?
- Codegen output not hand-edited?
- Form validation Zod-defined?
- Accessible (keyboard, screen reader, contrast)?

For infra reviewers:

- Terraform plan attached in PR comment?
- All sensitive variables marked `sensitive = true`?
- No state file committed?
- Free-tier limits checked?

## Merge strategy

- Squash & merge for feature/fix branches (single commit on main).
- Merge commit for release branches (preserves history).
- Rebase & merge banned (loses context, breaks bisect).
