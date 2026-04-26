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

## Module = top-level package

In Modulith, **a module is a single top-level package** below the application's root package. Sub-packages of a module are private by default; only types in the module's root package are visible to other modules.

```text
com.example.app/
├── Application.kt                    # @SpringBootApplication
├── billing/                          # module: billing
│   ├── package-info.java             # @ApplicationModule(displayName = "Billing")
│   ├── BillingService.kt             # PUBLIC api (in root)
│   ├── Invoice.kt                    # PUBLIC api
│   └── internal/
│       ├── InvoiceRepository.kt      # PRIVATE (sub-package)
│       └── PaymentGatewayClient.kt   # PRIVATE
├── catalog/                          # module: catalog
│   ├── package-info.java
│   ├── Product.kt
│   └── internal/
│       └── ProductRepository.kt
└── order/                            # module: order
    ├── package-info.java
    ├── OrderService.kt
    └── internal/
        └── OrderJpaEntity.kt
```

The `internal` sub-package name is convention; Modulith treats anything not in the module root as private unless explicitly exposed (see "Module dependency rules"). In practice all but the public-API types (services, value objects, events) belong in `internal/`.

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

webstack convention: Kotlin codebases use the `@PackageInfo` form to avoid a single Java source file in an otherwise-Kotlin module.

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

- A class in module B imports a class from `module-a.internal.*`.
- A class in module B imports any class from module A unless A's package is in B's `allowedDependencies`.
- An event handler in module B handles an event whose declaring class is in `module-a.internal.*`.

The "public API only" rule means: events, DTOs, and service interfaces meant for cross-module use sit at the module root; anything internal stays in `internal/`. This is the same discipline Java's package-private modifier was supposed to provide but rarely does, hardened with build-time enforcement.

## Bounded context = module

webstack convention is **one DDD bounded context = one Modulith module**. Discovery via `feature-architect` produces the bounded context list; the build-be SubAgent translates that list 1:1 into top-level packages with `package-info.java` declarations.

Inside a single module:

- **domain/** — entities, value objects, aggregates. Pure JVM, no Spring.
- **application/** — use cases, application services. Annotated with `@Service`. Depends on domain.
- **infrastructure/** — JPA entities, adapters, repositories. Depends on application/domain.
- **api/** (optional) — REST controllers if not centralized in a separate `web` module.

Cross-module communication happens **only via published domain events**, never via direct method calls into another module's internal package. The verifier enforces this; the event registry below makes it durable.

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

`@ApplicationModuleListener` is Modulith's wrapper for `@TransactionalEventListener(phase = AFTER_COMMIT)` plus `@Async` plus the registry's persistence semantics. Add the event registry starter to enable persistence:

```kotlin
implementation("org.springframework.modulith:spring-modulith-starter-jpa")
implementation("org.springframework.modulith:spring-modulith-events-jpa")
```

The schema (table `event_publication`) is created by Modulith's Flyway migration shipped with the starter.

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
- **Public API surface, by default, is the module root.** Domain events and application service interfaces live in `com.example.app.<module>.*`. Implementation details, JPA entities, repositories, adapters, and internal services live in `com.example.app.<module>.internal.*`.
- **Cross-module communication via events only.** Direct service-to-service calls between modules are forbidden by the verifier and policed in code review.
- **Event publication starter required.** Always include `spring-modulith-events-jpa`; reliability of cross-module events is non-negotiable.
- **Verifier test in CI.** `ModulithBoundaryTest` lives at `src/test/kotlin/com/example/app/`; CI fails on violation.
- **Documentation auto-rendered.** Documenter test runs on PR; rendered diagrams attached as artifact for review.

## Sources

- Spring Modulith reference: https://docs.spring.io/spring-modulith/reference/
- Modular monoliths with Kotlin and Spring (JetBrains blog): https://blog.jetbrains.com/kotlin/2026/02/building-modular-monoliths-with-kotlin-and-spring/
- ApplicationModule API: https://docs.spring.io/spring-modulith/reference/fundamentals.html
- Event publication registry: https://docs.spring.io/spring-modulith/reference/events.html
