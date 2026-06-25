# KoTest BehaviorSpec

> Reference for build-be SubAgent. Covers KoTest's BehaviorSpec testing style — Given/When/Then scenarios, matchers, MockK integration, Spring slices, coroutine and property-based testing.

## Why BehaviorSpec

BehaviorSpec is KoTest's BDD-flavored testing style. Tests read like Gherkin scenarios:

```text
Given an order with status NEW
  When the customer cancels it
  Then the order status becomes CANCELLED
  And a refund event is published
```

The structure communicates intent to non-engineers (product, QA, domain experts). Renaming a test does not break wiring; the Given/When/Then strings are the test names, surfaced verbatim in build reports. For the webstack TDD loop (see `shared/methodologies/tdd.md`), this is the difference between specs that document the domain and tests that document the implementation.

KoTest's other styles (FunSpec, DescribeSpec, ShouldSpec, FreeSpec) are interchangeable; BehaviorSpec is the webstack default for its match with use-case-driven design.

## Setup

In `build.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm")
    id("org.jetbrains.kotlin.plugin.spring")
}

dependencies {
    // Versions are centralised in gradle/libs.versions.toml (see dependency-management.md
    // §Backend version catalog). The Spring extension is io.kotest:kotest-extensions-spring —
    // lockstep with the runner (≥ 6.2.0 for Spring 7 / Boot 4), NOT io.kotest.extensions:…:1.3.0.
    testImplementation(libs.kotest.runner)
    testImplementation(libs.kotest.assertions)
    testImplementation(libs.kotest.property)
    testImplementation(libs.kotest.spring)
    testImplementation(libs.mockk)
    testImplementation("org.springframework.boot:spring-boot-starter-test") {
        exclude(group = "org.junit.vintage", module = "junit-vintage-engine")
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Pin to the current KoTest 6.x stable; refresh per major Spring Boot release or every two months. The Spring extension wires `@SpringBootTest` into KoTest's lifecycle; without it, the application context does not boot for KoTest specs.

### Migrating from 5.x to 6.x

KoTest 6 introduces a few intentional breaking changes from 5.x; webstack's BehaviorSpec usage is mostly unaffected, but verify per project:

- **Coroutines**: `runTest` semantics aligned with kotlinx-coroutines-test 1.8+. Existing `runTest { ... }` blocks compile unchanged.
- **Property-based testing**: `Arb` API is unchanged for the patterns webstack uses (`Arb.int(0, 100_000)`, `checkAll(...)`).
- **Spring extension**: the artifact is **`io.kotest:kotest-extensions-spring`**, versioned **in lockstep with the KoTest runner** (use the same version; pin ≥ 6.2.0 for Spring Framework 7 / Boot 4 support). The old standalone `io.kotest.extensions:kotest-extensions-spring:1.3.0` is archived and pulls Spring 5 — do **not** use it on Boot 4. The import path is unchanged: `io.kotest.extensions.spring.SpringExtension`.
- **Assertion library**: `shouldBe`, `shouldNotBe`, `shouldThrow`, `assertSoftly`, `withClue` are stable. Only obscure assertions removed.

Run `./gradlew test --rerun-tasks` after the bump; address any deprecation warnings.

## File structure

One spec class per aggregate or use case. The convention `<UnitOfBehavior>Spec.kt`:

```text
src/test/kotlin/com/example/app/billing/
├── InvoiceSpec.kt              # aggregate behavior (pure JVM)
├── PayInvoiceUseCaseSpec.kt    # application service (pure JVM with mocks)
└── InvoiceJpaAdapterSpec.kt    # infrastructure (Spring slice)
```

Domain layer specs do not boot Spring (faster, isolation). Application layer specs use mocked ports. Infrastructure specs use `@SpringBootTest` or `@DataJpaTest` slices.

## BehaviorSpec syntax

A spec class extends `BehaviorSpec`. The DSL nests `given { when { then { } } }`. `when` is a Kotlin reserved word, so it must be backticked:

```kotlin
import io.kotest.core.spec.style.BehaviorSpec
import io.kotest.matchers.shouldBe

class InvoiceSpec : BehaviorSpec({

    given("an invoice with status DRAFT") {
        val invoice = Invoice(id = InvoiceId.new(), status = InvoiceStatus.DRAFT, amount = Money.of(100, "USD"))

        `when`("the invoice is finalized") {
            invoice.finalize()

            then("the status becomes FINALIZED") {
                invoice.status shouldBe InvoiceStatus.FINALIZED
            }

            then("a finalize timestamp is recorded") {
                invoice.finalizedAt shouldNotBe null
            }
        }

        `when`("the invoice is cancelled") {
            invoice.cancel(reason = "duplicate")

            then("the status becomes CANCELLED") {
                invoice.status shouldBe InvoiceStatus.CANCELLED
            }

            then("the reason is preserved") {
                invoice.cancellationReason shouldBe "duplicate"
            }
        }
    }
})
```

`given`, `when`, `then` blocks chain text labels into readable scenario names. Each `then` is one assertion (or one tightly related group). Multiple `then` blocks under one `when` share setup but each runs independently.

Aliases exist (`Given`, `When`, `Then` — capitalized) that don't require backticks; webstack convention is the lowercase form to match Gherkin.

## Matchers

KoTest assertions are infix, fluent, and chainable. Common ones:

```kotlin
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import io.kotest.matchers.nulls.shouldNotBeNull
import io.kotest.matchers.collections.shouldContain
import io.kotest.matchers.collections.shouldHaveSize
import io.kotest.matchers.string.shouldStartWith
import io.kotest.matchers.string.shouldContain as shouldContainSubstring
import io.kotest.matchers.types.shouldBeInstanceOf
import io.kotest.assertions.throwables.shouldThrow

result shouldBe 42
result shouldNotBe null
list shouldHaveSize 3
list shouldContain "alpha"
"hello world" shouldStartWith "hello"
parsed.shouldBeInstanceOf<UserDto>()

// `message` is String? — assert non-null first, then match the substring.
// (The collections and string `shouldContain` share a name, so the string one is aliased.)
shouldThrow<IllegalArgumentException> {
    Money.of(-100, "USD")
}.message.shouldNotBeNull() shouldContainSubstring "negative"
```

For Either / Result types, `shouldBeRight()` and `shouldBeLeft()` from kotest-assertions-arrow. For temporal values, `shouldBeBetween(from, to)`. For numerics, `shouldBeWithinPercentageOf(expected, percentage)`.

## Assertions library

Beyond matchers, the assertion library provides combinators:

```kotlin
import io.kotest.assertions.assertSoftly
import io.kotest.assertions.withClue

withClue("after finalization the audit log should record the actor") {
    invoice.auditLog.last().actorId shouldBe currentUserId
}

assertSoftly(invoice) {
    status shouldBe InvoiceStatus.FINALIZED
    finalizedAt shouldNotBe null
    auditLog shouldHaveSize 1
}
```

`withClue` adds context to a single assertion's failure message. `assertSoftly` collects failures so the report shows every mismatch in one run, not just the first. Use `assertSoftly` for assertion clusters about a single object (final state of an aggregate); avoid for assertions about different concerns.

## MockK integration

MockK is the idiomatic Kotlin mocking library. It supports relaxed mocks, coroutines, and final classes (Kotlin's default).

```kotlin
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.springframework.context.ApplicationEventPublisher

class PayInvoiceUseCaseSpec : BehaviorSpec({

    val invoiceRepository = mockk<InvoiceRepository>()
    val paymentGateway = mockk<PaymentGateway>()
    val publisher = mockk<ApplicationEventPublisher>(relaxed = true)
    val useCase = PayInvoiceUseCase(invoiceRepository, paymentGateway, publisher)

    given("an invoice that exists and a successful gateway") {
        val invoice = Invoice.draft(amount = Money.of(100, "USD"))
        every { invoiceRepository.findById(invoice.id) } returns invoice
        every { paymentGateway.charge(any()) } returns PaymentResult.Success(transactionId = "tx_123")

        `when`("the use case is executed") {
            val result = useCase.pay(invoice.id, cardToken = "tok_abc")

            then("the result is success") {
                result.shouldBeInstanceOf<PayInvoiceResult.Paid>()
            }

            then("the gateway was called with the invoice amount") {
                verify { paymentGateway.charge(match { it.amount == invoice.amount }) }
            }

            then("an InvoicePaid event was published") {
                verify { publisher.publishEvent(any<InvoicePaid>()) }
            }
        }
    }
})
```

Use `coEvery` and `coVerify` for `suspend` collaborators. Use `relaxed = true` when the mock has many irrelevant methods (publishers, loggers); use strict mocks for the system under test's primary collaborators so missing setups are caught.

### Mocking a bean: prefer pure unit tests, use `@MockkBean` only in slices

**Altitude matters.** The cheapest, fastest mocking is in a **pure-JVM unit test** — construct the application service directly with `mockk()` ports (as `PayInvoiceUseCaseSpec` above). No Spring context, no `@MockkBean`. This covers the bulk of behavior.

Reach for **`@MockkBean`** (springmockk) only when you genuinely need a Spring context with one collaborator replaced — typically a **controller web slice**, where Spring wires the controller but its application service should be mocked:

```kotlin
import com.ninja_squad.springmockk.MockkBean
import io.kotest.extensions.spring.SpringExtension
import io.mockk.every
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.web.servlet.MockMvc

@SpringBootTest
@AutoConfigureMockMvc
class InvoiceControllerSpec : BehaviorSpec() {
    @MockkBean private lateinit var payInvoice: PayInvoiceUseCase   // Spring bean → MockK mock
    @Autowired private lateinit var mockMvc: MockMvc

    init {
        extension(SpringExtension)
        given("a payable invoice") {
            every { payInvoice.pay(any(), any()) } returns PayInvoiceResult.Paid(/* … */)
            // … perform POST /api/invoices/{id}/pay, assert 200 + body
        }
    }
}
```

(Use the `BehaviorSpec()` + `init { }` form, not the lambda-constructor form, so `@MockkBean` / `@Autowired` fields can live on the class.)

**springmockk 5.x naming (Spring Boot 4)** — Boot 4 removed `@MockBean`/`@SpyBean`, so springmockk was rewritten onto Spring's Bean Override framework:

- `@MockkBean` — unchanged.
- `@SpykBean` → **`@MockkSpyBean`**.
- `@MockkBean(classes = [...])` → `@MockkBean(types = [...])`.

If you don't need a MockK mock specifically, Spring's own `@MockitoBean` works too (Mockito); webstack standardizes on MockK for Kotlin ergonomics (coroutines, `final`/`object` mocking).

## Spring integration

Domain specs run pure JVM (fastest). Application service specs typically also run pure JVM with MockK ports. Infrastructure specs that hit JPA, beans, or controllers boot Spring through KoTest's Spring extension:

```kotlin
import io.kotest.core.spec.style.BehaviorSpec
import io.kotest.extensions.spring.SpringExtension
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest

@SpringBootTest
class InvoiceJpaAdapterSpec(
    @Autowired private val adapter: InvoiceJpaAdapter,
) : BehaviorSpec({
    extension(SpringExtension)

    given("an empty database") {
        `when`("an invoice is saved") {
            val saved = adapter.save(Invoice.draft(Money.of(50, "USD")))

            then("it is retrievable by id") {
                adapter.findById(saved.id) shouldBe saved
            }
        }
    }
})
```

`extension(SpringExtension)` is mandatory for the application context to bind. For controller slices use `@WebMvcTest`; for JPA-only `@DataJpaTest` (faster than full `@SpringBootTest`).

## Integration testing with TestContainers

For tests that need real Postgres semantics — JSONB columns, partial indexes, RLS policies, generated columns, dialect-sensitive queries — webstack's convention is **Spring Boot `@ServiceConnection`** (introduced in 3.1, standard since 4.0) over a Testcontainers `PostgreSQLContainer`. Flyway migrations apply against the container; the Spring app boots against the live DB; tests run; the container is torn down.

```kotlin
import io.kotest.core.spec.style.BehaviorSpec
import io.kotest.extensions.spring.SpringExtension
import io.kotest.matchers.shouldBe
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.testcontainers.service.connection.ServiceConnection
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers

@Testcontainers
@SpringBootTest
class InvoiceQueryAdapterSpec(
    @Autowired private val adapter: InvoiceQueryAdapter,
) : BehaviorSpec({
    extension(SpringExtension)

    given("a Postgres container with Flyway-applied schema") {
        `when`("invoices are inserted then queried") {
            adapter.save(Invoice.draft(amount = Money.of(100, "USD")))
            adapter.save(Invoice.draft(amount = Money.of(200, "USD")))
            then("the count is 2") {
                adapter.countAll() shouldBe 2L
            }
        }
    }
}) {
    companion object {
        @Container
        @ServiceConnection
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")
    }
}
```

Dependencies (latest patches via Spring Boot's BOM):

```kotlin
testImplementation("org.springframework.boot:spring-boot-testcontainers")
testImplementation("org.testcontainers:postgresql")
testImplementation("org.testcontainers:junit-jupiter")
```

When NOT to use TestContainers:

- **Domain-only specs** (no Spring, no JPA): pure JVM is faster and isolation is perfect.
- **Pure controller slice tests**: `@WebMvcTest` mocks the persistence layer; no DB needed.
- **Local dev convenience**: TestContainers needs Docker running. CI must enable Docker; document this in README.

webstack's `build-be` skill Phase 4.5 enforces at least one TestContainers-backed spec per feature whose backend touches persistence — see `skills/build-be/SKILL.md`. Cross-reference: `docs/backend/jpa-patterns.md` "Verifying migrations with TestContainers" for the migration-test variant.

## Coroutine tests

Use `runTest` from kotlinx-coroutines-test for deterministic time control. KoTest also exposes `coroutineScope { }` and `runBlocking { }` directly inside `then` blocks since each `then` is itself a `suspend` lambda:

```kotlin
import kotlinx.coroutines.test.runTest

`when`("the async operation runs") {
    // runTest returns a TestResult, not the lambda's value — assert inside the block.
    then("the result is success") {
        runTest {
            val result = useCase.processAsync(invoice.id)
            result.shouldBeInstanceOf<Success>()
        }
    }
}
```

For mocked suspend functions: `coEvery { mock.suspendFn() } returns value`. Verify with `coVerify { ... }`.

## Property-based testing

`io.kotest:kotest-property` provides generators (`Arb.int()`, `Arb.string()`) for randomized inputs. Useful for laws and invariants:

```kotlin
import io.kotest.property.Arb
import io.kotest.property.arbitrary.int
import io.kotest.property.checkAll

class MoneySpec : BehaviorSpec({
    given("addition is associative") {
        `when`("three random USD amounts are added in different groupings") {
            then("results are equal") {
                checkAll(Arb.int(0, 1_000_000), Arb.int(0, 1_000_000), Arb.int(0, 1_000_000)) { a, b, c ->
                    val left = (Money.of(a, "USD") + Money.of(b, "USD")) + Money.of(c, "USD")
                    val right = Money.of(a, "USD") + (Money.of(b, "USD") + Money.of(c, "USD"))
                    left shouldBe right
                }
            }
        }
    }
})
```

Property tests catch edge cases example-based tests miss (overflow, empty inputs, Unicode boundaries). Reserve them for invariants and pure functions; example-based BehaviorSpec remains the default for use-case scenarios.

## webstack convention

- **Domain layer specs are pure JVM.** No `@SpringBootTest`, no MockK on Spring beans. The aggregate is constructed directly with test data; assertions check state and events.
- **Application layer specs use MockK ports.** Each port (repository, gateway, publisher) is mocked. The use case under test is constructed via its primary constructor with the mocks. No Spring context.
- **Infrastructure layer specs may boot Spring slices.** `@DataJpaTest` for JPA adapters, `@WebMvcTest` for controllers, full `@SpringBootTest` only when several layers must integrate.
- **One scenario, one `given`.** Tests with five branching `when`s under a single `given` are split into multiple `given` blocks for readability.
- **`assertSoftly` for state-cluster assertions.** `withClue` for context on a single check.
- **Property-based reserved for invariants.** Use `forAll` / `checkAll` for monoids, identities, idempotence, parser round-trips. Not for general use-case tests.

See `shared/templates/kotest-spec-template.md` for the canonical scaffold.

## Sources

- KoTest framework docs: https://kotest.io/docs/framework/testing-styles.html
- KoTest assertions: https://kotest.io/docs/assertions/assertions.html
- KoTest Spring extension: https://kotest.io/docs/extensions/spring.html
- MockK: https://mockk.io/
- KoTest property-based: https://kotest.io/docs/proptest/property-based-testing.html
- KoTest releases: https://github.com/kotest/kotest/releases

Last verified: 2026-06-22 (KoTest 6.x stable).
