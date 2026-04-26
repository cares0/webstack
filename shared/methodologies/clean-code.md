# Clean Code

> Source: Robert C. Martin, *Clean Code: A Handbook of Agile Software Craftsmanship* (2008)

## Naming

- **Reveal intent**: `daysSinceLastLogin` > `d`.
- **Pronounceable**: avoid abbreviations the team can't say out loud.
- **Searchable**: long names for things you'll grep — `MAX_LOGIN_ATTEMPTS` > `7`.
- **One word per concept**: don't mix `fetch` / `get` / `retrieve` for the same operation.
- **Domain language**: use ubiquitous language from DDD bounded context.

## Functions

- **Small**: 4-15 lines for most functions. If it's longer, it's probably doing too much.
- **One thing**: a function should do one thing, do it well, and only that.
- **One level of abstraction**: don't mix high-level orchestration with low-level details in one function.
- **Few arguments**: 0 (niladic) or 1 (monadic) ideal; 2 acceptable; 3+ smells like a missing object.
- **No flag arguments**: `render(true)` → split into `renderHtml()` / `renderText()`.
- **Pure where possible**: prefer functions returning new values over mutating state.

## Comments

> "Comments are, at best, a necessary evil. ... Every time you write a comment, you should grimace and feel the failure of your ability of expression."

Default: **no comments**. Only write comments when:

- Explaining non-obvious WHY (a hidden constraint, regulatory requirement, workaround).
- Marking deliberate `TODO` / `FIXME` with context (issue number, owner, deadline).
- Public API docs (KDoc, JSDoc) for libraries — but minimal, generated from signatures.

Don't:

- Explain WHAT the code does (rename / extract until it's obvious).
- Reference the current task or PR (rots fast).
- Repeat the function signature in prose.

## Error handling

- Throw on programmer errors (preconditions, invariants).
- Use `Result<T, E>` / `Either` / sealed classes for expected failures (validation, not-found, etc.).
- Never swallow exceptions silently. If you catch, you must do something useful.
- One responsibility per try block.

## Tests

- Test names describe behavior: `should reject email without domain`.
- One assertion per test conceptually (related assertions can group).
- Test data should be obvious — favor builder helpers over magic numbers.
- Tests must be independent — no shared mutable state between tests.

## Code Reviewer SubAgent applies these as

| Severity | Example |
|---|---|
| Critical | Function > 50 lines doing 3 different things; mutable global state introduced |
| Important | Function with 4+ arguments; flag argument; comment explaining what code does |
| Suggestion | Name could be more specific; could extract method for readability |

## References

- Martin, *Clean Code* (2008), chapters 1-9.
- Martin, *Clean Architecture* (2017) for higher-level structure.
