---
name: build-be
description: Implementation guide for backend code from an OpenAPI 3.1 contract using DDD/Hexagonal Architecture with Spring Boot 3 + Kotlin + KoTest BehaviorSpec. Invoked by the backend-implementer SubAgent. Can also be followed by main agent for fallback / debug scenarios.
---

# build-be skill — backend implementation guide

This skill is the procedure followed when implementing the backend portion of a webstack feature. Operates inside a backend repo's `.worktrees/<feature>/` working tree.

## Inputs (from invoking context)

- `worktree_path`: cd here.
- `contract_path`: OpenAPI 3.1 YAML.
- `plan_path`: feature plan markdown.
- `architect_report`: domain mapping report.

## Required reads

- `shared/methodologies/ddd.md`
- `shared/methodologies/hexagonal.md`
- `shared/methodologies/api-first.md`
- `shared/methodologies/tdd.md`
- `shared/methodologies/clean-code.md`
- `docs/backend/spring-modulith.md`
- `docs/backend/kotest-behavior-spec.md`
- `docs/backend/jpa-patterns.md`
- (`docs/backend/jooq-patterns.md` only if jOOQ in active use)
- `shared/templates/kotest-spec-template.kt`

## Pre-conditions

- worktree on branch `feature/<feature_name>`.
- Working tree clean (initial entry).
- `./gradlew build` passes baseline (run once to confirm).

## Phase 1: Domain modeling

Per architect's aggregate proposals, for each new aggregate `<Aggregate>`:

1. Create package `domain/<aggregate>/`.
2. Write aggregate root entity: `<Aggregate>.kt` — class with private mutable state, public methods enforcing invariants.
3. Write value objects: `<Vo>.kt` — `@JvmInline value class` or `data class` with init validation.
4. Write repository port: `<Aggregate>Repository.kt` — interface with aggregate-scoped methods only.
5. Write domain events (if any): `<Event>.kt` — data class.
6. Write `package-info.java` declaring `@org.springframework.modulith.ApplicationModule(displayName="<Module>")` if this is a new module root.

For modifications to existing aggregate: add methods preserving existing invariants. Run KoTest spec for that aggregate; ensure no regression before changes.

**TDD per aggregate** (recommended order):

1. Write failing `<Aggregate>Spec.kt` for new behavior.
2. Run: `./gradlew test --tests "<package>.<Aggregate>Spec" --no-daemon`. Confirm fail.
3. Implement minimal code to pass.
4. Re-run; confirm pass.
5. Refactor; tests stay green.
6. Commit per Aggregate.

## Phase 2: Application layer

For each use case from architect/plan:

1. Define use case interface (driving port): `application/<usecase>/<UseCase>UseCase.kt`.
2. Define command DTO: `application/<usecase>/<UseCase>Command.kt` — Kotlin data class, no Jackson, validation via Kotlin require/check or arrow validation.
3. Implement service: `application/<usecase>/<UseCase>Service.kt` — `@Service @Transactional`, depends on repository ports + domain services.
4. Spec: `application/<usecase>/<UseCase>ServiceSpec.kt` — KoTest BehaviorSpec. Use MockK for repository mocks. NO @SpringBootTest at this level (pure JVM).

Commit per use case.

## Phase 3: Infrastructure adapters

For each endpoint from contract:

1. Write request/response DTO: `infrastructure/http/<resource>/<Resource>Dto.kt` — Jackson-bound, with validation annotations.
2. Write controller: `infrastructure/http/<resource>/<Resource>Controller.kt` — `@RestController`, methods translate DTO ↔ domain command, call use case.
3. Write controller integration spec: `infrastructure/http/<resource>/<Resource>ControllerSpec.kt` — `@SpringBootTest`, `@AutoConfigureMockMvc`, KoTest BehaviorSpec.
4. Write JPA entity (if new): `infrastructure/persistence/<aggregate>/<Aggregate>JpaEntity.kt` — `@Entity`, mapping to/from domain via `toDomain()` / `fromDomain()` extension functions in same file.
5. Write repository implementation: `infrastructure/persistence/<aggregate>/<Aggregate>JpaRepositoryImpl.kt` — wraps Spring Data JPA `<Aggregate>SpringDataRepository : JpaRepository<<Aggregate>JpaEntity, UUID>`, implements domain port.
6. Migration: add `src/main/resources/db/migration/V<N+1>__<feature>.sql` with new tables/columns.

Commit per resource (controller + persistence atomic).

## Phase 4: Wiring & validation

1. Run `./gradlew build` — full compile + tests + Modulith verifier (in @ApplicationModuleTests).
2. Resolve any compile/test failure before moving on.
3. Format: `./gradlew ktlintFormat` (or equivalent if installed).

## Phase 5: Drift verification

1. Start backend: `./gradlew bootRun &` — capture PID.
2. Wait for startup: poll `curl -fsS http://localhost:8080/actuator/health` until `{"status":"UP"}` (max 60s).
3. Invoke `contract-drift-detective` SubAgent with `contract_path` + `springdoc_url=http://localhost:8080/v3/api-docs`. (If invoking another SubAgent isn't supported in this context, perform the diff inline using `curl + python3` parsing.)
4. Stop backend: `kill $PID`.
5. If Critical drift: fix code (or, if contract is wrong, escalate `CLARIFICATION NEEDED:` to invoking caller).

## Output

Write `<project_root>/.webstack/features/<feature>/be-status.md` per backend-implementer agent's spec.

## Escalation Protocol (when invoked from SubAgent)

`CLARIFICATION NEEDED: <question>` then stop.

## Style

- Commit per logical unit (aggregate / use case / resource), not per file.
- Conventional Commits with scopes `domain`, `app`, `api`, `db`, `test`.
- KoTest spec names describe behavior in domain language.
