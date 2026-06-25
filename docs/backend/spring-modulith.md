# Spring Modulith

> Reference for build-be SubAgent and feature-architect. Covers Spring Modulith's modular monolith conventions: package boundaries, the `ApplicationModule` annotation, the verifier, the event publication registry, and how DDD bounded contexts map onto modules.

## What Spring Modulith is

Spring Modulith is an extension of the Spring Framework that gives you **enforced module boundaries inside a single Spring Boot application**. It is not a microservices framework. The deployment unit remains a single jar; what changes is the discipline applied to internal package structure.

The core deliverables:

1. **Boundary verifier** — a test that fails the build if module A reaches into module B's internal packages.
2. **Event publication registry** — a transactional outbox that stores `@TransactionalEventListener` events durably and retries on failure, decoupling modules without infrastructure.
3. **Documentation generator** — runtime-introspected component diagrams (PlantUML / C4) so the architecture is always documented from the source of truth.
4. **Test slicing** — `@ApplicationModuleTest` boots only the module under test plus its declared dependencies.

For early-stage products webstack targets, Modulith is the right middle ground: the operational simplicity of a monolith, with the design enforcement that prevents the codebase from becoming a "distributed monolith waiting to be split."

## Module = top-level package = bounded context

In Modulith, **a module is a single top-level package** below the application's root package, and webstack convention pins **one module per DDD bounded context**. Sub-packages of a module are private by default; only types in the module's root package are visible to other modules.

webstack also composes Modulith with hexagonal architecture: the hexagonal layers (`domain/`, `application/`, `infrastructure/`) live **inside each module**. The naming aligns Modulith's "internal" privacy with the hexagonal boundary — `application/` and `infrastructure/` are private to the module by definition, while the public surface for cross-module use is the module-root types (typically domain events and a small set of service interfaces).

```text
com.example.app/
├── Application.kt                    # @SpringBootApplication
├── billing/                          # module: billing (bounded context)
│   ├── package-info.java             # @ApplicationModule(displayName = "Billing")
│   ├── BillingService.kt             # PUBLIC api (in root) — re-exports an application port
│   ├── InvoicePaid.kt                # PUBLIC domain event — other modules subscribe
│   ├── domain/                       # PRIVATE — pure Kotlin, no Spring/JPA
│   │   └── invoice/
│   │       ├── Invoice.kt            # aggregate root
│   │       ├── InvoiceId.kt          # value object
│   │       └── InvoiceRepository.kt  # driven port
│   ├── application/                  # PRIVATE — use cases, @Service @Transactional
│   │   └── pay/
│   │       ├── PayInvoiceUseCase.kt  # driving port
│   │       └── PayInvoiceService.kt  # impl
│   └── infrastructure/               # PRIVATE — adapters
│       ├── http/
│       │   └── BillingController.kt
│       ├── persistence/
│       │   ├── InvoiceJpaEntity.kt
│       │   └── InvoiceJpaRepository.kt
│       └── config/
│           └── BillingConfig.kt
├── catalog/                          # module: catalog (bounded context)
│   ├── package-info.java
│   ├── Product.kt                    # PUBLIC entity (read-only) for cross-BC reference
│   ├── domain/...
│   ├── application/...
│   └── infrastructure/...
└── order/                            # module: order
    ├── package-info.java
    ├── OrderPlaced.kt                # PUBLIC domain event
    ├── OrderInvoicePaidHandler.kt    # PUBLIC handler that subscribes to billing.InvoicePaid
    ├── domain/...
    ├── application/...
    └── infrastructure/...
```

Two things are conventional, not enforced by the verifier:

1. **Hexagonal layout inside the module** (`domain/`, `application/`, `infrastructure/`). The verifier doesn't care how you sub-divide a module's internals — it only checks cross-module imports. webstack picks this layout to keep the architecture readable.
2. **Public surface in the module root.** Place domain events, public application service interfaces, and any cross-module-readable VO at the module's root package. Modulith treats these as the module's public API.

For Modulith's privacy semantics specifically: anything not in the module root **and not annotated `@NamedInterface`** counts as internal. The conventional `internal/` sub-package some examples use is interchangeable with our `application/` + `infrastructure/` split — the import rules are the same.

## ApplicationModule annotation

Declare the module either on a Java `package-info.java` (the conventional JVM mechanism) or, in a Kotlin codebase, on a class annotated `@PackageInfo` (Modulith ≥ 1.2). Pick one form per module — don't mix.

Java form (`package-info.java`):

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Billing",
    allowedDependencies = {"catalog", "shared"}
)
package com.example.app.billing;
```

Kotlin form (a small `ModuleMetadata.kt` in the module's root package):

```kotlin
package com.example.app.billing

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    displayName = "Billing",
    allowedDependencies = ["catalog", "shared"],
)
internal class ModuleMetadata
```

webstack convention: use the Java `package-info.java` form, even in an otherwise-Kotlin module, for tooling consistency with the Spring Modulith team's recommendation. The `@PackageInfo` Kotlin form is supported and works, but is not the default. Pick one form per module — don't mix.

- **`displayName`** — used by the documentation generator.
- **`allowedDependencies`** — explicit whitelist. Empty (the default) means "no other internal modules"; depending on Spring infrastructure or `java.*` is always allowed.
- **Named interfaces** — for finer-grained dependency control, declare a named interface (`@org.springframework.modulith.NamedInterface("spi")` on a sub-package) and reference it as `"<module> :: <interface>"` (e.g., `allowedDependencies = ["order :: spi"]`). Reference: Modulith reference, "Named Interfaces".

Whenever a new module needs a dependency on another, the `allowedDependencies` array is the audit trail: the change is reviewable in PR.

## Module dependency rules

The Modulith verifier (run as a unit test, see "Verifier test") reads:

- The package layout to discover modules.
- Each module's `@ApplicationModule.allowedDependencies`.
- Each Kotlin/Java import statement.

It fails the build when:

- A class in module B imports a class from a non-public sub-package of module A (anything below the module root, e.g. `module-a.application.*` / `module-a.infrastructure.*`).
- A class in module B imports any class from module A unless A's package is in B's `allowedDependencies`.
- An event handler in module B handles an event whose declaring class is in a non-public sub-package of module A.

The "public API only" rule means: events, DTOs, and service interfaces meant for cross-module use sit at the module root; everything else stays in the module's `application/` and `infrastructure/` sub-packages. This is the same discipline Java's package-private modifier was supposed to provide but rarely does, hardened with build-time enforcement.

## Bounded context = module (with hexagonal layers inside)

webstack convention is **one DDD bounded context = one Modulith module**, and **each module contains its own hexagonal layered structure**. Discovery via `feature-architect` produces the bounded context list; the `backend-implementer` SubAgent translates that list 1:1 into top-level packages with `package-info.java` declarations, and creates `domain/`, `application/`, `infrastructure/` subdirectories inside each.

Inside a single module:

- **domain/** — entities, value objects, aggregates, repository ports, domain events. Pure JVM, no Spring/JPA/Jackson imports.
- **application/** — use cases, application services. Driving ports here. `@Service @Transactional` lives at this layer. Depends on domain.
- **infrastructure/** — JPA entities + repository adapters, REST controllers + DTOs, config beans. Depends on application + domain.

The split between layers is enforced by code review (and optionally by ArchUnit tests). The split between modules is enforced by the Modulith verifier.

```text
com.example.app/billing/
├── package-info.java                # @ApplicationModule(displayName="Billing")
├── InvoicePaid.kt                   # public event (cross-module subscribers read this)
├── domain/
│   └── invoice/
│       ├── Invoice.kt               # aggregate root
│       ├── InvoiceId.kt
│       └── InvoiceRepository.kt     # driven port
├── application/
│   └── pay/
│       ├── PayInvoiceUseCase.kt     # driving port
│       └── PayInvoiceService.kt
└── infrastructure/
    ├── http/
    │   └── BillingController.kt
    ├── persistence/
    │   └── InvoiceJpaRepository.kt
    └── config/
        └── BillingConfig.kt
```

Cross-module communication happens **only via published domain events** at the module root, never via direct method calls into another module's `application/` or `infrastructure/`. The verifier enforces this; the event registry below makes it durable.

If a module has only one aggregate (rare but possible), keep the same shape — `domain/<aggregate>/`, `application/<usecase>/`, `infrastructure/...`. The shape, not the size, is the convention.

## Event publication registry

Without infrastructure, the registry persists every event published from a `@Transactional` boundary into a Modulith-managed table (`event_publication`) before commit. Listeners (`@TransactionalEventListener`) consume events asynchronously; if a listener fails, the registry retries.

```kotlin
// billing/InvoicePaid.kt — public domain event
data class InvoicePaid(val invoiceId: InvoiceId, val amount: Money, val occurredAt: Instant)

// billing/InvoiceService.kt — publisher
@Service
class InvoiceService(private val publisher: ApplicationEventPublisher) {
    @Transactional
    fun markPaid(id: InvoiceId, amount: Money) {
        // ... mutate aggregate ...
        publisher.publishEvent(InvoicePaid(id, amount, Instant.now()))
    }
}

// order/OrderInvoicePaidHandler.kt — subscriber in another module
@Component
class OrderInvoicePaidHandler(private val orderService: OrderService) {
    @ApplicationModuleListener
    fun on(event: InvoicePaid) {
        orderService.recordPayment(event.invoiceId, event.amount)
    }
}
```

`@ApplicationModuleListener` is Modulith's wrapper for `@TransactionalEventListener(phase = AFTER_COMMIT)` plus `@Async` plus the registry's persistence semantics. Add the event registry starter to enable persistence (pin to the latest 2.x stable line):

```kotlin
// build.gradle.kts — modulith version centralised in gradle/libs.versions.toml
implementation(platform(libs.modulith.bom))
implementation("org.springframework.modulith:spring-modulith-starter-jpa")
// (spring-modulith-events-jpa is pulled in transitively by -starter-jpa; no separate entry needed)
```

The BOM keeps every Modulith artifact in lockstep. Verify the latest version at https://github.com/spring-projects/spring-modulith/releases at implementation time; webstack updates this pin per major Spring Boot release.

The schema (table `event_publication`) is created by Modulith's Flyway migration shipped with the starter.

### Migrating from 1.x to 2.x

If a project was scaffolded against Spring Modulith 1.x:

- **Annotation API**: `@ApplicationModule` keeps the same shape; `@NamedInterface` is unchanged. No source rewrites required for typical webstack code.
- **Kotlin module declaration**: 1.x supported `@PackageInfo` on a Kotlin class; 2.x continues to support both `@PackageInfo` and the conventional Java `package-info.java`. Spring Modulith team recommends `package-info.java` even in Kotlin codebases for tooling consistency. webstack v1 picks `package-info.java`; 1.x projects on `@PackageInfo` work but should plan to migrate.
- **Verifier API**: `ApplicationModules.of(<App>::class.java).verify()` is unchanged.
- **Event publication table schema**: a 1.x → 2.x migration adds optional columns; the auto-applied Flyway script handles it. No manual SQL.

For active 1.x projects: bump the BOM version, run `./gradlew build`, address any `@Deprecated` warnings, run the Modulith verifier test, ship.

## Documentation generation

The `Documenter` class introspects the running module structure and emits PlantUML or C4 diagrams. Run it from a test:

```kotlin
class GenerateDocumentationTest {
    @Test
    fun `render module documentation`() {
        val modules = ApplicationModules.of(Application::class.java)
        Documenter(modules)
            .writeDocumentation()
            .writeIndividualModulesAsPlantUml()
            .writeAggregatingDocument()
    }
}
```

Output lands in `target/spring-modulith-docs/` (or `build/`). Each module gets a diagram of its dependencies; an aggregate document shows the system. webstack runs this test as part of CI to keep architecture docs current; the `code-reviewer` SubAgent surfaces the rendered diagrams when reviewing structural changes.

## Verifier test

A single Spring Boot test asserts boundaries:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules

class ModulithBoundaryTest {
    @Test
    fun `module boundaries are respected`() {
        ApplicationModules.of(Application::class.java).verify()
    }
}
```

`verify()` throws `Violations` listing every illegal cross-module reference. The test fails CI on any boundary leak — typically a teammate importing a JPA entity from another module instead of consuming the published event.

In webstack, `code-reviewer` SubAgent runs this test in P5 review and blocks merge on any violation.

## webstack convention

- **Bounded context discovery → module list.** `feature-architect` SubAgent produces the BC list during `/webstack:feature` P1; build-be SubAgent creates one Modulith module per BC, including `package-info.java`.
- **Public API surface, by default, is the module root.** Domain events and application service interfaces live in `com.example.app.<module>.*` (the module root). Implementation details — JPA entities, repositories, adapters, and internal services — live in the module's `application/` and `infrastructure/` sub-packages; only module-root types are public to other modules. There is no `internal/` package in webstack.
- **Cross-module communication via events only.** Direct service-to-service calls between modules are forbidden by the verifier and policed in code review.
- **Event publication starter required.** Always include `spring-modulith-starter-jpa` (it pulls in `spring-modulith-events-jpa` transitively); reliability of cross-module events is non-negotiable.
- **Verifier test in CI.** `ModulithBoundaryTest` lives at `src/test/kotlin/com/example/app/`; CI fails on violation.
- **Documentation auto-rendered.** Documenter test runs on PR; rendered diagrams attached as artifact for review.

## Sources

- Spring Modulith reference: https://docs.spring.io/spring-modulith/reference/
- Modular monoliths with Kotlin and Spring (JetBrains blog): https://blog.jetbrains.com/kotlin/2026/02/building-modular-monoliths-with-kotlin-and-spring/
- ApplicationModule API: https://docs.spring.io/spring-modulith/reference/fundamentals.html
- Event publication registry: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith releases: https://github.com/spring-projects/spring-modulith/releases

Last verified: 2026-06-22 (Spring Modulith 2.x stable).
