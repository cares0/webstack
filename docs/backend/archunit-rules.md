# ArchUnit rules (DDD/Hexagonal layer enforcement)

> Reference for build-be SubAgent and backend-implementer and code-reviewer SubAgent.
> Architecture tests with ArchUnit complementing Spring Modulith verifier for DDD/Hexagonal layer rules.

## What is ArchUnit

ArchUnit is a JVM architecture testing library that validates structural rules by analyzing **compiled bytecode** — not source text. It imports `.class` files through `ClassFileImporter`, constructs an in-memory graph of `JavaClass`, `JavaMethod`, `JavaField`, and their dependency relationships, then evaluates user-defined rules as ordinary JUnit tests.

The key distinction from linters (Checkstyle, Detekt) is that ArchUnit reasons _after_ compilation: it sees actual call sites, annotations, inheritance trees, and package membership. A rule like "no class in `domain/` may depend on a Spring type" catches indirect violations that regex-based linters miss.

ArchUnit 1.x ships three API layers: **Core** (`ClassFileImporter`), **Lang** (fluent DSL: `classes().that()...should()...`), and **Library** (pre-built rules: `layeredArchitecture()`, `slices().matching(...)`).

**JUnit 5 integration** requires only two annotations: `@AnalyzeClasses` on the test class, `@ArchTest` on rule fields. The imported classes are **cached per class-path snapshot** — a project with 20 rules pays the import cost once per test run.

```kotlin
// build.gradle.kts — version in gradle/libs.versions.toml (see dependency-management.md §Backend version catalog)
testImplementation(libs.archunit.junit5)
```

## Why ArchUnit + Modulith verifier 둘 다

Spring Modulith's verifier (see [`docs/backend/spring-modulith.md`](spring-modulith.md)) checks **cross-module boundaries** — it fails when module B imports a type from module A's internal packages. The verifier does not inspect how the layers inside a module are organized.

ArchUnit covers the complementary dimension: **intra-module structural rules**. The division:

| Concern | Modulith verifier | ArchUnit |
|---------|------------------|----------|
| Cross-module import violation | yes | supplementary |
| Hexagonal layer ordering inside a module | no | yes |
| Spring/JPA leaking into `domain/` | no | yes |
| Naming conventions (`*Controller`, `*JpaEntity`) | no | yes |
| Cyclic dependencies within a module | no | yes |
| DDD aggregate root discipline | no | yes |
| Value object immutability | no | yes |

A `domain/Invoice.kt` that imports `jakarta.persistence.Entity` passes the Modulith verifier silently — ArchUnit catches it. Spring Modulith 2.x documents a jMolecules integration (`JMoleculesArchitectureRules.ensureHexagonal(...)`) via `VerificationOptions` (verify the exact API name against your jmolecules-integration + Modulith 2.x at implementation time); webstack augments this with naming and structural rules that jMolecules does not cover.

## webstack convention

Test file: `src/test/kotlin/com/<org>/<project>/architecture/ArchitectureTest.kt` — one file per backend project; all rules live here.

```kotlin
@AnalyzeClasses(
    packages = ["com.<org>.<project>"],           // application root package
    importOptions = [ImportOption.DoNotIncludeTests::class],
)
class ArchitectureTest {
    // @ArchTest fields
}
```

`packages` must be the parent of the module packages (`billing`, `catalog`, `order`, …). `ImportOption.DoNotIncludeTests` prevents test classes from polluting the architecture graph. No `@ExtendWith` or `@RunWith` is required — the ArchUnit JUnit 5 TestEngine is auto-discovered via `ServiceLoader`.

**Kotlin notes:** Kotlin properties compile to Java fields + accessors; ArchUnit sees the Java bytecode. Rule predicates using `isAnnotatedWith(...)` work correctly on `val`/`var` properties.

## Layer rules (Hexagonal)

Allowed dependency direction: `infrastructure → application → domain`. `domain` must not depend on anything outside itself — no Spring, JPA, or Jackson. `application` may depend on `domain` only. `infrastructure` may depend on `application` and `domain`.

```kotlin
// Layered ordering — catches accidental upward imports
layeredArchitecture().consideringAllDependencies()
    .layer("Domain").definedBy("..domain..")
    .layer("Application").definedBy("..application..")
    .layer("Infrastructure").definedBy("..infrastructure..")
    .whereLayer("Domain").mayNotAccessAnyLayer()
    .whereLayer("Application").mayOnlyAccessLayers("Domain")
    .whereLayer("Infrastructure").mayOnlyAccessLayers("Application", "Domain")
```

Supplement with explicit prohibition rules for framework pollution in `domain/`. Repeat the pattern for JPA (`jakarta.persistence..`) and Jackson — both the Jackson 2 (`com.fasterxml.jackson..`) and Jackson 3 (`tools.jackson..`) packages, since Spring Boot 4 defaults to Jackson 3:

```kotlin
noClasses().that().resideInAPackage("..domain..")
    .should().dependOnClassesThat().resideInAPackage("org.springframework..")
    .because("Domain must be pure Kotlin — no Spring imports allowed")

// Controllers belong in infrastructure/http/, not application/
classes().that().areAnnotatedWith(RestController::class.java)
    .should().resideInAPackage("..infrastructure.http..")
```

## Module-internal layer enforcement

The Modulith verifier stops cross-module package imports. ArchUnit adds the orthogonal check: inside a module, layers must not reach into a sibling module's lower layers. Two rules cover this:

```kotlin
// Catches intra-module AND cross-module domain→infrastructure violations in one shot
noClasses().that().resideInAPackage("..domain..")
    .should().dependOnClassesThat().resideInAPackage("..infrastructure..")

// Cross-module direct dependency — replace (org).(project) with your package segments
SlicesRuleDefinition.slices()
    .matching("com.(org).(project).(*)..")
    .should().notDependOnEachOther()
    .because("Cross-module collaboration is via published domain events only.")
```

## Naming rules

ArchUnit enforces naming conventions at build time. Conventions: `@RestController` → `*Controller` (in `infrastructure/http/`), `@Service` → `*Service`, `@Entity` → `*JpaEntity`, domain `Repository` interface → `*Repository`, JPA adapter impl → `*JpaAdapter`, use case driving port → `*UseCase`.

The pattern is uniform — `classes().that().areAnnotatedWith(X).should().haveSimpleNameEndingWith("Y")`:

```kotlin
classes().that().areAnnotatedWith(RestController::class.java)
    .should().haveSimpleNameEndingWith("Controller")

classes().that().areAnnotatedWith(Service::class.java)
    .should().haveSimpleNameEndingWith("Service")

// *JpaEntity distinguishes JPA infrastructure entities from domain entities
classes().that().areAnnotatedWith(Entity::class.java)
    .should().haveSimpleNameEndingWith("JpaEntity")

classes().that().resideInAPackage("..application..").and().areInterfaces()
    .should().haveSimpleNameEndingWith("UseCase")
```

## Cyclic dependency

`SlicesRuleDefinition.slices().matching(...).should().beFreeOfCycles()` builds a dependency graph across slices and reports any strongly connected component. Replace `(org).(project)` with your package segments:

```kotlin
// Inter-module cycles
SlicesRuleDefinition.slices()
    .matching("com.(org).(project).(*)..")
    .should().beFreeOfCycles()

// Intra-module cycles — narrow to a single module, or generate dynamically
SlicesRuleDefinition.slices()
    .matching("com.(org).(project).billing.(*)..")
    .should().beFreeOfCycles()
```

## DDD-specific rules

Use jMolecules annotations (`org.jmolecules.ddd.annotation`: `@AggregateRoot`, `@ValueObject`, `@DomainEvent`) to mark types, then enforce rules against them.

**Aggregate root as the only public entry point** — external code must not reference internal aggregate entities directly:

```kotlin
noClasses().that().resideOutsideOfPackage("..domain..")
    .should().dependOnClassesThat()
        .resideInAPackage("..domain..")
        .and().areNotAnnotatedWith(AggregateRoot::class.java)
        .and().areNotInterfaces() // Repository ports are fine
        .and().areNotAnnotatedWith(DomainEvent::class.java)
    .because("Only aggregate roots, repository ports, and domain events are the public domain API.")
```

**Value objects are immutable** — enforce with a custom `ArchCondition<JavaClass>` that checks for the `component1()` method (generated by the Kotlin compiler for every `data class`). Full implementation is in the sample test class.

**Domain events in module root** (public surface for cross-module `@ApplicationModuleListener` subscribers):

```kotlin
classes().that().areAnnotatedWith(DomainEvent::class.java)
    .should().resideInAPackage("com.example.app.*")
    .because("Domain events must be in module root so Spring Modulith treats them as public.")
```

`resideInAPackage` treats `(...)` capture groups as literal characters, not wildcards (unlike `slices().matching(...)`). Use `com.example.app.*` — a single `*` matches exactly one package segment, i.e. the module root (`com.example.app.billing`), and excludes deeper packages like `com.example.app.billing.domain`.

## Sample test class

Complete, runnable Kotlin file. Replace `com.example.app` with your root package.

```kotlin
package com.example.app.architecture

import com.tngtech.archunit.core.importer.ImportOption
import com.tngtech.archunit.junit.AnalyzeClasses
import com.tngtech.archunit.junit.ArchTest
import com.tngtech.archunit.lang.ArchCondition
import com.tngtech.archunit.lang.ArchRule
import com.tngtech.archunit.lang.ConditionEvents
import com.tngtech.archunit.lang.SimpleConditionEvent
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses
import com.tngtech.archunit.library.Architectures.layeredArchitecture
import com.tngtech.archunit.library.dependencies.SlicesRuleDefinition
import jakarta.persistence.Entity
import org.jmolecules.ddd.annotation.AggregateRoot
import org.jmolecules.ddd.annotation.DomainEvent
import org.jmolecules.ddd.annotation.ValueObject
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.RestController

@AnalyzeClasses(
    packages = ["com.example.app"],
    importOptions = [ImportOption.DoNotIncludeTests::class],
)
class ArchitectureTest {

    @ArchTest val hexagonalLayerRule: ArchRule = layeredArchitecture()
        .consideringAllDependencies()
        .layer("Domain").definedBy("..domain..")
        .layer("Application").definedBy("..application..")
        .layer("Infrastructure").definedBy("..infrastructure..")
        .whereLayer("Domain").mayNotAccessAnyLayer()
        .whereLayer("Application").mayOnlyAccessLayers("Domain")
        .whereLayer("Infrastructure").mayOnlyAccessLayers("Application", "Domain")

    @ArchTest val domainHasNoSpringDependency: ArchRule =
        noClasses().that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAPackage("org.springframework..")
            .because("Domain must be pure Kotlin — no Spring imports allowed")

    @ArchTest val domainHasNoJpaDependency: ArchRule =
        noClasses().that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
                .resideInAnyPackage("jakarta.persistence..", "javax.persistence..")
            .because("Domain must be pure Kotlin — no JPA imports allowed")

    @ArchTest val domainHasNoJacksonDependency: ArchRule =
        noClasses().that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
                .resideInAnyPackage("com.fasterxml.jackson..", "tools.jackson..")
            .because("Domain must be pure Kotlin — no Jackson imports allowed (Jackson 2 or 3)")

    @ArchTest val controllersInInfrastructureHttp: ArchRule =
        classes().that().areAnnotatedWith(RestController::class.java)
            .should().resideInAPackage("..infrastructure.http..")

    @ArchTest val domainDoesNotDependOnInfrastructure: ArchRule =
        noClasses().that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAPackage("..infrastructure..")

    @ArchTest val modulesDoNotDependOnEachOtherDirectly: ArchRule =
        SlicesRuleDefinition.slices()
            .matching("com.example.app.(*)..")
            .should().notDependOnEachOther()
            .because("Cross-module collaboration is via published domain events only.")

    @ArchTest val controllerNaming: ArchRule =
        classes().that().areAnnotatedWith(RestController::class.java)
            .should().haveSimpleNameEndingWith("Controller")

    @ArchTest val serviceNaming: ArchRule =
        classes().that().areAnnotatedWith(Service::class.java)
            .should().haveSimpleNameEndingWith("Service")

    @ArchTest val jpaEntityNaming: ArchRule =
        classes().that().areAnnotatedWith(Entity::class.java)
            .should().haveSimpleNameEndingWith("JpaEntity")

    @ArchTest val useCaseNaming: ArchRule =
        classes().that().resideInAPackage("..application..").and().areInterfaces()
            .should().haveSimpleNameEndingWith("UseCase")

    @ArchTest val noCyclicDependencies: ArchRule =
        SlicesRuleDefinition.slices()
            .matching("com.example.app.(*)..")
            .should().beFreeOfCycles()

    @ArchTest val valueObjectsAreDataClasses: ArchRule =
        classes().that().areAnnotatedWith(ValueObject::class.java)
            .should(beKotlinDataClass())
            .because("Value objects are immutable; use Kotlin data class with val properties")

    @ArchTest val domainEventsAreInModuleRoot: ArchRule =
        classes().that().areAnnotatedWith(DomainEvent::class.java)
            .should().resideInAPackage("com.example.app.*")  // single * = one segment (module root)
            .because("Domain events must be in module root so Spring Modulith treats them as public.")

    @ArchTest val aggregateRootIsPublicEntryPoint: ArchRule =
        noClasses().that().resideOutsideOfPackage("..domain..")
            .should().dependOnClassesThat()
                .resideInAPackage("..domain..")
                .and().areNotAnnotatedWith(AggregateRoot::class.java)
                .and().areNotInterfaces()
                .and().areNotAnnotatedWith(DomainEvent::class.java)
            .because("Only aggregate roots, repository ports, and domain events are the public domain API.")
}

// component1() is generated by the Kotlin compiler for every data class with a primary constructor param.
private fun beKotlinDataClass() =
    object : ArchCondition<com.tngtech.archunit.core.domain.JavaClass>("be a Kotlin data class") {
        override fun check(clazz: com.tngtech.archunit.core.domain.JavaClass, events: ConditionEvents) {
            if (clazz.methods.none { it.name == "component1" })
                events.add(SimpleConditionEvent.violated(clazz,
                    "${clazz.name} is @ValueObject but is not a Kotlin data class"))
        }
    }
```

## Anti-patterns

**Over-ruling.** Rules should encode conventions that cause real architectural damage if broken — layer violations, naming collisions, cyclic dependencies. Style-level conventions (parameter order, line length) belong in Detekt/Ktlint, not ArchUnit. A project with 50 ArchUnit rules becomes noisy and fragile.

**Lazy verification — no rules.** Relying on code review alone is inconsistent over time. At minimum, four rules must be active in every webstack project: no Spring in domain, no JPA in domain, controllers in `infrastructure/http/`, cyclic dependency check.

**Over-broad analysis.** `@AnalyzeClasses(packages = [""])` (empty string → whole classpath) imports third-party libraries and produces false positives. Always scope `packages` to your application root and add `ImportOption.DoNotIncludeJars` if runtime is slow.

**Monolithic file with no structure.** One file is correct to start. When it exceeds ~200 lines, split by category: `LayerRuleTest.kt`, `NamingRuleTest.kt`, `CyclicDependencyTest.kt`. ArchUnit's JUnit 5 engine caches classes across test classes in the same suite — no runtime penalty for splitting.

**Freezing violations in a greenfield project.** `FreezingArchRule.freeze(rule)` is useful for brownfield adoption. In a webstack greenfield project, frozen violations hide design debt. Fix the code or delete the rule; never freeze.

## Sources

- **ArchUnit user guide:** https://www.archunit.org/userguide/html/000_Index.html — _authoritative_
- **ArchUnit GitHub (TNG/ArchUnit):** https://github.com/TNG/ArchUnit — _authoritative_
- **Spring Modulith reference — Verification:** https://docs.spring.io/spring-modulith/reference/verification.html — _authoritative_
- **jMolecules ArchUnit integration:** https://github.com/xmolecules/jmolecules-integrations/tree/main/jmolecules-archunit — _community: xmolecules_
- **webstack spring-modulith.md:** docs/backend/spring-modulith.md — _internal cross-reference_

Last verified: 2026-06-22 (ArchUnit 1.4.2 / Spring Modulith 2.x / Kotlin 2.x).
