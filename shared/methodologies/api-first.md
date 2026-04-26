# API-First Development (Contract-First with OpenAPI 3.1)

> Sources:
> - OpenAPI 3.1 spec (https://spec.openapis.org/oas/v3.1.0)
> - Glovo Engineering, "Using contract-first to build an HTTP Application with OpenAPI and Gradle"
> - Schwarz IT, "Contract first with SpringBoot"
> - Baeldung, "API First Development with Spring Boot and OpenAPI 3.0"

## The Principle

The contract (OpenAPI YAML) is the **single source of truth**. Both ends — frontend and backend — derive from it. Divergence is impossible because:
- Frontend types are codegen'd from the contract (`@hey-api/openapi-ts`).
- Backend implementation is checked at runtime against the contract (`springdoc-openapi` exposes runtime spec; `contract-drift-detective` agent diffs against `.webstack/contracts/<feature>.yaml`).

## webstack workflow

```
plan-feature (P2)
  │ extract resources, operations, payloads
  ▼
sync-contract (P3) — write .webstack/contracts/<feature>.yaml
  │
  ├─[FE codegen]─▶ src/api/generated/{types.ts, sdk.ts, queries.ts}
  │              (frontend-implementer uses, never edits manually)
  │
  └─[BE direct write]─▶ DDD layered structure
                        ├─ domain/<aggregate>/
                        ├─ application/<usecase>/
                        └─ infrastructure/http/<Resource>Controller.kt
                          (manual writing; codegen NOT used because of DDD divergence)
                        │
                        ▼
                        contract-drift-detective verifies springdoc /v3/api-docs == contracts/<feature>.yaml
```

## What goes into a contract

- `paths`: every endpoint with method, parameters, request body, responses (one per status code).
- `components.schemas`: all DTOs (request, response, error).
- `components.securitySchemes`: auth (Bearer, OAuth2, API key).
- `components.parameters`: reusable query/path/header parameters.
- `info`: title, version, description.
- `servers`: dev, staging, prod URLs (templated).

## Drift policy

When `contract-drift-detective` finds a difference:

| Severity | Example | Action |
|---|---|---|
| Critical | Endpoint missing in implementation; status code mismatch; required field missing | Block PR. Fix immediately. |
| Important | Optional field type mismatch; description differs | Warn. Fix in same PR. |
| Info | Example value differs; description punctuation | Note in review. Optional fix. |

Source of truth in conflict: **contract YAML** wins. Implementation must adapt. If the contract is wrong, update contract first, then re-run feature flow.

## Versioning

- Breaking changes → new major version path (`/api/v2/users`). Old version coexists during deprecation window.
- Non-breaking additive changes → no version bump; bump `info.version` minor.

## Anti-patterns

- **Backend-first then export OpenAPI**: contract becomes implementation snapshot. Defeats consumer-driven design.
- **Hand-edited frontend types**: drift cause #1. Always regenerate.
- **Multiple contract files for one feature**: split contracts only on bounded-context lines.
- **Publishing internal types**: response schemas should hide aggregate internals — DTOs at boundary.

## References

- https://spec.openapis.org/oas/v3.1.0
- https://medium.com/glovo-engineering/using-contract-first-to-build-an-http-application-with-openapi-and-gradle-53b42c2c2094
- https://techblog.schwarz/posts/contract-first-with-springboot/
- https://www.baeldung.com/spring-boot-openapi-api-first-development
