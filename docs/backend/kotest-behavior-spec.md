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
    testImplementation("io.kotest:kotest-runner-junit5:5.9.1")
    testImplementation("io.kotest:kotest-assertions-core:5.9.1")
    testImplementation("io.kotest:kotest-property:5.9.1")
    testImplementation("io.kotest.extensions:kotest-extensions-spring:1.3.0")
    testImplementation("io.mockk:mockk:1.13.13")
    testImplementation("org.springframework.boot:spring-boot-starter-test") {
        exclude(group = "org.junit.vintage", module = "junit-vintage-engine")
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Pin to a current KoTest 5.x; refresh quarterly. The Spring extension wires `@SpringBootTest` into KoTest's lifecycle; without it, the application context does not boot for KoTest specs.

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
import io.kotest.matchers.collections.shouldContain
import io.kotest.matchers.collections.shouldHaveSize
import io.kotest.matchers.string.shouldStartWith
import io.kotest.matchers.types.shouldBeInstanceOf
import io.kotest.assertions.throwables.shouldThrow

result shouldBe 42
result shouldNotBe null
list shouldHaveSize 3
list shouldContain "alpha"
"hello world" shouldStartWith "hello"
parsed.shouldBeInstanceOf<UserDto>()

shouldThrow<IllegalArgumentException> {
    Money.of(-100, "USD")
}.message shouldContain "negative"
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

class PayInvoiceUseCaseSpec : BehaviorSpec({

    val invoiceRepository = mockk<InvoiceRepository>()
    val paymentGateway = mockk<PaymentGateway>()
    val publisher = mockk<DomainEventPublisher>(relaxed = true)
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
                verify { publisher.publish(any<InvoicePaid>()) }
            }
        }
    }
})
```

Use `coEvery` and `coVerify` for `suspend` collaborators. Use `relaxed = true` when the mock has many irrelevant methods (publishers, loggers); use strict mocks for the system under test's primary collaborators so missing setups are caught.

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

## Coroutine tests

Use `runTest` from kotlinx-coroutines-test for deterministic time control. KoTest also exposes `coroutineScope { }` and `runBlocking { }` directly inside `then` blocks since each `then` is itself a `suspend` lambda:

```kotlin
import kotlinx.coroutines.test.runTest

`when`("the async operation runs") {
    val result = runTest {
        useCase.processAsync(invoice.id)
    }

    then("the result is success") {
        result.shouldBeInstanceOf<Success>()
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
