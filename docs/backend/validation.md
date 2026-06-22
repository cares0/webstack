# Validation (Bean Validation 3.1 + domain invariants)

> Reference for build-be SubAgent and backend-implementer.
> Two-layer validation: jakarta-validation at HTTP boundary, invariants enforced in domain objects.

## What is webstack validation

webstack applies validation at two distinct layers:

**Layer 1 — HTTP boundary (jakarta-validation 3.1).** Request DTOs carry `@NotNull`, `@NotBlank`, `@Email`, `@Size`, and similar constraints. Spring MVC triggers validation when a controller parameter carries `@Valid` or `@Validated`. A failed constraint throws `MethodArgumentNotValidException`, mapped to a structured `ProblemDetail` by `ValidationExceptionHandler` (see `docs/backend/error-handling.md`).

**Layer 2 — Domain invariants (pure Kotlin).** Aggregates, entities, and value objects enforce invariants in constructors, factory functions, and command methods via `require` and `check`. No jakarta annotation touches the domain layer. A domain object can never exist in an invalid state regardless of how it was created.

The two layers are **complementary, not redundant**. The boundary rejects malformed input early; the domain enforces business rules. When domain invariants are violated, `DomainException` subclasses propagate to module-scoped `@RestControllerAdvice` handlers — the same pipeline in `docs/backend/error-handling.md`.

## Why two layers

**Domain invariants are the object's responsibility.** If `Order` requires `totalAmount > 0`, that rule lives in `Order` — not in a controller or service. Any caller — HTTP, Kafka consumer, test — gets enforcement for free.

**HTTP boundary validation is format enforcement.** `@NotBlank` on a DTO says "the HTTP contract requires a non-empty string here." It carries no domain meaning; it exists to fail fast before touching the application layer.

**Separation keeps the domain portable.** `init { require(...) }` runs in any JVM context. Jakarta annotations in domain code require a Bean Validation runtime and violate the hexagonal boundary (`shared/methodologies/hexagonal.md`).

**Different failure modes.** Boundary failures are user errors — 400 with field-level `violations`. Domain failures are business rule violations — 400, 409, or 422 via `DomainException` subclasses. `MethodArgumentNotValidException` and `DomainException` are distinct things mapped by distinct handlers.

## webstack convention — HTTP boundary

### DTO placement

DTOs live in `<module>/infrastructure/http/<resource>/`. They are data carriers for a single HTTP interaction and have no behaviour. Domain entities never appear as controller parameters or response bodies.

```text
billing/
└── infrastructure/
    └── http/
        └── invoice/
            ├── CreateInvoiceRequest.kt    ← input DTO (jakarta annotations here)
            ├── UpdateInvoiceRequest.kt
            └── InvoiceResponse.kt         ← output DTO (no constraints needed)
```

### Annotating a request DTO

```kotlin
// billing/infrastructure/http/invoice/CreateInvoiceRequest.kt
data class CreateInvoiceRequest(
    @field:NotBlank @field:Size(max = 255) val recipientName: String,
    @field:NotBlank @field:Email           val recipientEmail: String,
    @field:NotNull  @field:Positive        val amountCents: Long?,
    @field:Size(max = 1000)                val notes: String? = null,
)
```

> **Kotlin note:** Always use `@field:` use-site target (e.g., `@field:NotNull`). Without it, Kotlin places the annotation on the constructor parameter, not the backing field. Hibernate Validator inspects fields by default and will silently skip any constraint missing the `@field:` target.

### Controller with `@Valid`

```kotlin
@RestController
@RequestMapping("/invoices")
class BillingController(private val createInvoice: CreateInvoiceUseCase) {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun create(@RequestBody @Valid request: CreateInvoiceRequest): InvoiceResponse =
        InvoiceResponse.from(createInvoice.execute(request.toCommand()))
}
```

`@Valid` triggers Bean Validation on the `@RequestBody`. Any failing constraint throws `MethodArgumentNotValidException` before the controller body executes.

### `MethodArgumentNotValidException` → ProblemDetail

`spring.mvc.problemdetails.enabled=true` (set in `application.yml`) registers Spring's built-in `ResponseEntityExceptionHandler`, which converts `MethodArgumentNotValidException` to a 400 ProblemDetail. webstack overrides this in `ValidationExceptionHandler` to add a `violations` extension array with per-field messages (see `docs/backend/error-handling.md` — _Validation error mapping_ section for the full handler implementation and example response shape).

The front-end SDK exposes `violations` as an optional field on `ProblemDetail`, giving React Hook Form inline error display without custom parsing.

### Enabling Bean Validation

Add `spring-boot-starter-validation` to `build.gradle.kts`; it includes Hibernate Validator 9.x and auto-configures `LocalValidatorFactoryBean`. No manual bean declaration needed.

## Validation groups

Validation groups allow the same DTO to carry different constraint sets for different operations. The common case in webstack is reusing a DTO for `POST` (create — all fields required) and `PATCH` (update — only provided fields validated).

### Define marker interfaces

```kotlin
// shared/infrastructure/http/ValidationGroups.kt
interface ValidationGroups {
    interface Create
    interface Update
}
```

### Apply groups to DTO fields

```kotlin
data class InvoiceRequest(
    @field:NotBlank(groups = [ValidationGroups.Create::class]) @field:Size(max = 255)
    val recipientName: String? = null,

    @field:NotBlank(groups = [ValidationGroups.Create::class]) @field:Email
    val recipientEmail: String? = null,

    @field:NotNull(groups = [ValidationGroups.Create::class]) @field:Positive
    val amountCents: Long? = null,
)
```

Fields annotated with a group constraint are only validated when that group is active. Fields with no group annotation belong to `Default` and are always validated (unless the group sequence excludes `Default`).

### Use `@Validated` in the controller

```kotlin
@PostMapping
fun create(
    @RequestBody @Validated(ValidationGroups.Create::class) request: InvoiceRequest,
): InvoiceResponse = InvoiceResponse.from(createInvoice.execute(request.toCreateCommand()))

@PatchMapping("/{id}")
fun update(
    @PathVariable id: String,
    @RequestBody @Validated(ValidationGroups.Update::class) request: InvoiceRequest,
): InvoiceResponse = InvoiceResponse.from(updateInvoice.execute(id, request.toUpdateCommand()))
```

`@Validated(Create::class)` activates the `Create` group plus `Default`. `@Valid` activates `Default` only.

## Conditional and cross-field validation

### `@AssertTrue` method (simple cross-field check)

Use `@AssertTrue` on a boolean method in the DTO when the rule involves two or more fields:

```kotlin
data class DateRangeRequest(
    @field:NotNull val startDate: LocalDate?,
    @field:NotNull val endDate: LocalDate?,
) {
    @AssertTrue(message = "endDate must be after startDate")
    fun isEndAfterStart(): Boolean =
        startDate == null || endDate == null || !endDate.isBefore(startDate)
}
```

Use an `is`-prefixed boolean getter so Bean Validation reads it as a `valid`/`isValid`-style property. The violation path will be `endAfterStart` (the property name derived from the `is`-getter, class-level); map it to a friendlier name in `ValidationExceptionHandler` if needed.

### Custom `ConstraintValidator` (reusable cross-field rule)

For rules that recur across multiple DTOs, implement a class-level `ConstraintValidator`. The annotation declares `@Constraint(validatedBy = [...])`, and the validator class implements `ConstraintValidator<A, T>`:

```kotlin
// 1. Annotation
@Target(AnnotationTarget.CLASS)
@Retention(AnnotationRetention.RUNTIME)
@Constraint(validatedBy = [DateRangeValidator::class])
annotation class ValidDateRange(
    val message: String = "endDate must be after startDate",
    val groups: Array<KClass<*>> = [],
    val payload: Array<KClass<out Payload>> = [],
)

// 2. Validator — return true for nulls; pair with @NotNull on individual fields
class DateRangeValidator : ConstraintValidator<ValidDateRange, DateRangeRequest> {
    override fun isValid(v: DateRangeRequest?, ctx: ConstraintValidatorContext): Boolean =
        v?.startDate == null || v.endDate == null || !v.endDate.isBefore(v.startDate)
}

// 3. Apply to DTO
@ValidDateRange
data class DateRangeRequest(
    @field:NotNull val startDate: LocalDate?,
    @field:NotNull val endDate: LocalDate?,
)
```

Spring's `SpringConstraintValidatorFactory` (auto-configured by `LocalValidatorFactoryBean`) allows `@Autowired` injection in validators.

## Domain invariants

Domain objects live in `<module>/domain/<aggregate>/` and are **pure Kotlin** — no Spring, JPA, Jackson, or jakarta imports. Invariants are enforced in `init` blocks, factory functions, and command methods.

### Value object `init` block

```kotlin
// billing/domain/invoice/Money.kt
@JvmInline
value class Money(val amountCents: Long) {
    init {
        require(amountCents >= 0) { "amount must be non-negative, was $amountCents" }
    }
}
```

Any attempt to construct `Money(-1)` — from a controller, a test, a Kafka consumer — throws `IllegalArgumentException`. The same pattern applies to every value object (`Email`, `InvoiceId`, etc.).

### Aggregate factory validation

Use a private constructor + `companion object` factory to guarantee that the invariant always runs:

```kotlin
// billing/domain/invoice/Invoice.kt
class Invoice private constructor(
    val id: InvoiceId,
    val recipientEmail: Email,
    val amount: Money,
    val status: InvoiceStatus,
) {
    companion object {
        fun create(id: InvoiceId, recipientEmail: Email, amount: Money): Invoice {
            require(amount.amountCents > 0) { "invoice amount must be positive" }
            return Invoice(id, recipientEmail, amount, InvoiceStatus.DRAFT)
        }
    }

    fun markAsSent(): Invoice {
        check(status == InvoiceStatus.DRAFT) { "only DRAFT invoices can be sent, was $status" }
        // Not a data class (the private ctor guards the invariant factory), so there is no
        // generated copy(). Construct the next state via the private constructor explicitly.
        return Invoice(id, recipientEmail, amount, InvoiceStatus.SENT)
    }
}
```

- `require(cond) { msg }` — input precondition. Throws `IllegalArgumentException`.
- `check(cond) { msg }` — state consistency. Throws `IllegalStateException`.

### Application service bridges the layers

The application service constructs domain objects from command values; domain invariants fire automatically on construction. It does not repeat validation.

```kotlin
@Service
@Transactional
class CreateInvoiceService(
    private val invoiceRepository: InvoiceRepository,
    private val idGenerator: InvoiceIdGenerator,
) : CreateInvoiceUseCase {

    override fun execute(command: CreateInvoiceCommand): Invoice =
        invoiceRepository.save(
            Invoice.create(
                id = idGenerator.next(),
                recipientEmail = Email(command.recipientEmail), // domain invariant fires here
                amount = Money(command.amountCents),            // domain invariant fires here
            )
        )
}
```

The `@Valid` DTO confirmed non-null, correctly formatted input. Domain value objects confirm semantics. Two layers — zero duplication.

### Domain exceptions vs `IllegalArgumentException`

Use `require`/`check` for programming errors (caller passed an impossible value). For violations with business meaning, throw a `DomainException` subclass so the `@RestControllerAdvice` maps the right HTTP status (see `docs/backend/error-handling.md` — _Domain exception hierarchy_):

```kotlin
fun markAsPaid(): Invoice {
    if (status == InvoiceStatus.PAID)
        throw ConflictException("INVOICE_ALREADY_PAID", "Invoice ${id.value} is already paid.")
    // ...
}
```

## Konform / Arrow Either alternative

### Konform

[Konform](https://github.com/konform-kt/konform) is a type-safe, zero-dependency, multiplatform Kotlin validation DSL. It expresses constraints as property references (`CreateInvoiceCommand::amountCents { minimum(1) }`) rather than annotations, returns a typed `Valid`/`Invalid` result, and works on Kotlin/JS and Kotlin/Native where jakarta-validation is unavailable.

**When to consider:** you want to validate **commands** inside the application layer with a richer accumulated-error structure, or the code must run outside the JVM.

**Default is jakarta-validation.** Konform adds a dependency and a second validation idiom. Use it only when the standard jakarta approach cannot express the rule cleanly or multiplatform support is required.

### Arrow Either

[Arrow](https://arrow-kt.io/) `Either<E, A>` accumulates typed errors without exceptions — `Left` carries the error, `Right` carries the value. Useful when a functional pipeline must collect multiple validation errors before reporting.

**Caution:** bridging Arrow with Spring's `@RestControllerAdvice` exception pipeline requires explicit `getOrElse { throw ... }` calls. Introduce Arrow only if the team already uses it and is comfortable with functional idioms.

## Anti-patterns

### 1. if-else validation in controllers

Checking request fields inside a controller method bypasses the uniform `ProblemDetail` pipeline, produces inconsistent error shapes, and scatters logic across handlers. Annotate the DTO with constraints, add `@Valid` to the parameter, and let `ValidationExceptionHandler` handle failures.

### 2. Returning `Boolean` from a validation method

A `Boolean` return forces every call site to decide what to do with `false`. Domain rules that fail should throw a typed `DomainException` (business violations) or use `require` (programming errors). The caller should never gate on a boolean.

### 3. Jakarta annotations on domain objects

```kotlin
// BAD
class Invoice(
    @field:Email val recipientEmail: String,   // ← jakarta in domain layer
) { ... }
```

Jakarta annotations couple the domain to the Bean Validation runtime and violate the Hexagonal boundary. Use `init { require(...) }` or a value object instead.

### 4. Missing `@field:` use-site target in Kotlin DTOs

`@NotBlank val field: String` places the annotation on the constructor parameter, not the backing field — Hibernate Validator silently skips it. Always write `@field:NotBlank val field: String`.

### 5. Duplicating domain rules as jakarta constraints

`@field:Min(1)` on a DTO field and `require(amountCents > 0)` in `Money` express the same numeric threshold. The DTO constraint is _format validation_ (early rejection of bad input); the domain invariant is the _canonical rule_. They can coexist, but if the DTO constraint merely mirrors the domain invariant, consider whether it adds value or just creates a maintenance burden when the threshold changes.

### 6. Validation logic in the persistence adapter

A repository `save` method that checks `invoice.amountCents <= 0` fires only on the JPA path — not in-memory fakes used in unit tests, not event-sourced rehydration. By the time an aggregate reaches the repository, its construction invariants already guarantee consistency. Move the check to the aggregate if it is missing.

## Sources

- **Spring Framework — Bean Validation:** https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html — _authoritative_
- **Hibernate Validator 9.x Reference Guide:** https://docs.hibernate.org/validator/9.0/reference/en-US/html_single/ — _authoritative_
- **Jakarta Bean Validation 3.1 Specification:** https://jakarta.ee/specifications/bean-validation/3.1/ — _authoritative_
- **Spring Framework — Validation error responses (ProblemDetail):** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html — _authoritative_
- **Konform — Kotlin validation library (GitHub):** https://github.com/konform-kt/konform — _community: konform-kt_
- **Maciej Walkowiak, "Bean Validation with Kotlin and Spring Boot":** https://maciejwalkowiak.com/blog/spring-boot-validation-kotlin/ — _community: Maciej Walkowiak_

Last verified: 2026-06-22 (Spring Boot 4.0.X / Hibernate Validator 9.X / jakarta-validation 3.1.X / Kotlin 2.X).
