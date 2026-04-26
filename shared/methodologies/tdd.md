# Test-Driven Development (TDD)

> Source: Kent Beck, *Test-Driven Development by Example* (2002). Refactoring chapter.

## The 3 Laws (Robert Martin's distillation of Kent Beck)

1. You may not write production code until you have written a failing unit test.
2. You may not write more of a unit test than is sufficient to fail (compilation failures count).
3. You may not write more production code than is sufficient to pass the currently failing test.

## The Red-Green-Refactor Cycle

```
RED    → Write a failing test
GREEN  → Write the minimum code to pass
REFACTOR → Improve structure without changing behavior
```

Each cycle is 2-5 minutes. Frequent commits at GREEN.

## Why this matters in webstack

- **Backend (build-be)**: KoTest BehaviorSpec written first (Given/When/Then). Implementation follows. Drift between spec & code surfaces immediately.
- **Frontend (build-fe)**: Vitest + Testing Library tests written before components. Hooks/components emerge from test requirements.
- **Plugin itself (this repo)**: scenario-based — `tests/scenarios/*.md` define expected behavior; manual + scripted verification.

## Test design principles

1. **One reason to fail**: Each test asserts one behavior. If a test breaks, the cause is unambiguous.
2. **Fast feedback**: Unit tests < 100ms each. Integration tests separate.
3. **Isolation**: Tests don't share state. No order dependency.
4. **Descriptive names**: `should return 404 when user not found` > `test1`.
5. **AAA pattern**: Arrange (setup) → Act (call) → Assert (verify).

## Anti-patterns to avoid

- **Test-after**: Writing tests after the implementation. Defeats design feedback.
- **Mocking everything**: Mocks should isolate slow/unstable boundaries (network, DB), not internal collaborators.
- **Asserting implementation details**: Test behavior, not internal calls. `expect(result).toBe(42)` > `expect(internalMethod).toHaveBeenCalled()`.
- **Skipped tests**: `xit` / `@Disabled` accumulate as silent rot. Delete or fix.

## When TDD is mandatory in webstack

- All `build-be` aggregate, application service, controller code.
- All `build-fe` form/data-fetching hooks, custom components.
- Plugin itself: each new skill/agent/doc has a corresponding scenario verification.

## When TDD is relaxed

- Throwaway prototypes (none in 1차 출시).
- Pure config files (plugin.json, marketplace.json, theme.css).
- Generated code (`@hey-api/openapi-ts` output) — covered by upstream lib's tests.

## References

- Kent Beck, *Test-Driven Development: By Example*, Addison-Wesley (2002).
- Robert Martin, *Clean Code*, Chapter 9 (Unit Tests).
- Martin Fowler, "TestDouble", https://martinfowler.com/bliki/TestDouble.html
