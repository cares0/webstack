---
name: build-be
description: Internal sub-skill — implementation guide for backend code from an OpenAPI 3.1 contract using DDD/Hexagonal Architecture with Spring Boot 3 + Kotlin + KoTest BehaviorSpec. Invoked by the backend-implementer SubAgent only; not a user-facing slash command.
disable-model-invocation: true
---

# build-be skill — backend implementation guide

This skill is the procedure followed when implementing the backend portion of a webstack feature. Operates inside a backend repo's `.worktrees/<feature>/` working tree.

## Inputs (from invoking context)

- `worktree_path`: cd here.
- `contract_path`: OpenAPI 3.1 YAML.
- `plan_path`: feature plan markdown.
- `architect_report`: domain mapping report.

## Reference docs (lazy — read on demand)

These references are loaded **lazily** — do NOT preload before Phase 1. When a phase below names a doc, Read it at that point only.

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

Each aggregate lives inside a Modulith module that maps 1:1 to a bounded context. The architect's report names the module(s) per BC; if a feature introduces a new BC, the module name comes from the architect's mapping (otherwise the aggregate slots into an existing module). Inside the chosen module, hexagonal layers are subdirectories.

For each new aggregate `<Aggregate>` belonging to module `<module>`:

1. Create package `<module>/domain/<aggregate>/`. (e.g., `billing/domain/invoice/`.)
2. Write aggregate root entity: `<Aggregate>.kt` — class with private mutable state, public methods enforcing invariants.
3. Write value objects: `<Vo>.kt` — `@JvmInline value class` or `data class` with init validation.
4. Write repository port: `<Aggregate>Repository.kt` — interface with aggregate-scoped methods only. (Lives in `<module>/domain/<aggregate>/`; the JPA implementation goes under `<module>/infrastructure/persistence/` in Phase 3.)
5. Write domain events (if any): `<Event>.kt`. **If the event is read by another module, place it at the module root** (`<module>/<Event>.kt`) so it is part of the module's public API. Module-internal events stay under `<module>/domain/<aggregate>/`.
6. If `<module>` is a brand-new bounded context (not adding to an existing one), create the module declaration at `<module>/package-info.java`:

   ```java
   @org.springframework.modulith.ApplicationModule(
       displayName = "<Module display name>",
       allowedDependencies = {}  // populate explicitly when this BC needs to depend on another
   )
   package com.<org>.<project>.<module>;
   ```

For modifications to existing aggregate: add methods preserving existing invariants. Run KoTest spec for that aggregate; ensure no regression before changes.

**TDD per aggregate** (recommended order):

1. Write failing `<Aggregate>Spec.kt` for new behavior.
2. Run: `./gradlew test --tests "<package>.<Aggregate>Spec" --no-daemon`. Confirm fail.
3. Implement minimal code to pass.
4. Re-run; confirm pass.
5. Refactor; tests stay green.
6. Commit per Aggregate.

## Phase 2: Application layer

For each use case from architect/plan, scoped to its module `<module>`:

1. Define use case interface (driving port): `<module>/application/<usecase>/<UseCase>UseCase.kt`.
2. Define command DTO: `<module>/application/<usecase>/<UseCase>Command.kt` — Kotlin data class, no Jackson, validation via Kotlin require/check or arrow validation.
3. Implement service: `<module>/application/<usecase>/<UseCase>Service.kt` — `@Service @Transactional`, depends on repository ports + domain services within the same module. Cross-module collaboration is via `ApplicationEventPublisher.publishEvent(...)` (with the event class at the **other** module's root), never by injecting a service from another module.
4. Spec: `<module>/application/<usecase>/<UseCase>ServiceSpec.kt` — KoTest BehaviorSpec. Use MockK for repository mocks. NO @SpringBootTest at this level (pure JVM).

If the use case **subscribes** to another module's published event, the handler lives at the module root (e.g., `<module>/<Other>InvoicePaidHandler.kt`) and is annotated `@ApplicationModuleListener`. Inside the handler, delegate to `<module>/application/...` services.

Commit per use case.

## Phase 3: Infrastructure adapters

For each endpoint from contract, scoped to its owning module `<module>`:

1. Write request/response DTO: `<module>/infrastructure/http/<resource>/<Resource>Dto.kt` — Jackson-bound, with validation annotations.
2. Write controller: `<module>/infrastructure/http/<resource>/<Resource>Controller.kt` — `@RestController`, methods translate DTO ↔ domain command, call the module's use case.
3. Write controller integration spec: `<module>/infrastructure/http/<resource>/<Resource>ControllerSpec.kt` — `@SpringBootTest`, `@AutoConfigureMockMvc`, KoTest BehaviorSpec.
4. Write JPA entity (if new): `<module>/infrastructure/persistence/<aggregate>/<Aggregate>JpaEntity.kt` — `@Entity`, mapping to/from domain via `toDomain()` / `fromDomain()` extension functions in same file.
5. Write repository implementation: `<module>/infrastructure/persistence/<aggregate>/<Aggregate>JpaRepositoryImpl.kt` — wraps Spring Data JPA `<Aggregate>SpringDataRepository : JpaRepository<<Aggregate>JpaEntity, UUID>`, implements the domain repository port.
6. Module-scoped Spring config (if needed): `<module>/infrastructure/config/<Module>Config.kt` — `@Configuration`, beans private to this module.
7. Migration: add `src/main/resources/db/migration/V<N+1>__<feature>.sql` with new tables/columns. Migrations are global to the application; prefix table names with the module name (`billing_invoice`, `order_orderline`) to keep ownership readable in the schema.

Commit per resource (controller + persistence atomic).

## Phase 4: Wiring & validation

1. Run `./gradlew build` — full compile + tests + Modulith verifier (in @ApplicationModuleTests).
2. Resolve any compile/test failure before moving on.
3. Format: `./gradlew ktlintFormat` (or equivalent if installed).

## Phase 4.5: Integration tests with TestContainers

If the feature touched persistence (new aggregate, new query, new migration), at least one spec must run against a real Postgres via Testcontainers. webstack's pattern is `@SpringBootTest` + `@Testcontainers` + `@ServiceConnection` + `PostgreSQLContainer` — see `docs/backend/kotest-behavior-spec.md` "Integration testing with TestContainers" and `docs/backend/jpa-patterns.md` "Verifying migrations with TestContainers" for full examples.

1. Add `org.springframework.boot:spring-boot-testcontainers` + `org.testcontainers:postgresql` + `org.testcontainers:junit-jupiter` to `testImplementation` if absent (Spring Boot's BOM resolves the version).
2. Write at least one spec under `<module>/infrastructure/persistence/<aggregate>/<Aggregate>JpaAdapterSpec.kt` (or `<Aggregate>QueryAdapterSpec.kt` for read-only adapters) that:
   - Boots a `PostgreSQLContainer("postgres:16-alpine")` (pin the major to whatever Supabase's pooled instance reports — check `SELECT version();` against the live project at any time).
   - Uses `@ServiceConnection` so Spring Boot wires JDBC config automatically.
   - Lets Flyway apply migrations (default behavior under `@SpringBootTest`).
   - Exercises the adapter (save → findById round trip, or query → expected row count) with KoTest BehaviorSpec.
3. Run `./gradlew test --tests "<package>.<...>JpaAdapterSpec"` — must pass with Docker daemon available.

If the feature is pure domain (no persistence), skip Phase 4.5 and document the choice in `be-status.md` ("no persistence change; TestContainers spec not added").

## Phase 5: Drift sanity (inline)

The canonical drift report is produced by the `contract-drift-detective` SubAgent in the main `/webstack:feature` Phase 7. This phase is a local sanity check inside the worktree only; SubAgent-to-SubAgent invocation is not supported, so the diff is done inline. Do NOT attempt to invoke `contract-drift-detective` from this skill.

1. Start backend: `./gradlew bootRun &` — capture PID.
2. Wait for startup: poll `curl -fsS http://localhost:8080/actuator/health` until `{"status":"UP"}` (max 60s).
3. Fetch the runtime spec: `curl -sf http://localhost:8080/v3/api-docs > /tmp/runtime-spec.json`.
4. Diff against `<contract_path>` inline with `python3 -c "import yaml,json,sys; ..."`. At minimum verify: (a) every contract path is in runtime, (b) every contract method per path is present, (c) status codes per operation match, (d) required request/response field types match.
5. Stop backend: `kill $PID`.
6. If Critical drift (missing endpoint, status-code mismatch, type mismatch): fix code in this worktree; or, if the contract itself is wrong, escalate `CLARIFICATION NEEDED: <question>` to the invoking caller and stop.

## Output

Write `<project_root>/.webstack/features/<feature>/be-status.md` per backend-implementer agent's spec.

## Escalation Protocol (when invoked from SubAgent)

`CLARIFICATION NEEDED: <question>` then stop.

## Style

- Commit per logical unit (aggregate / use case / resource), not per file.
- Conventional Commits with scopes `domain`, `app`, `api`, `db`, `test`.
- KoTest spec names describe behavior in domain language.
