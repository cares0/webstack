# Error handling (RFC 7807 ProblemDetail)

> Reference for build-be SubAgent and backend-implementer.
> Spring 6 ProblemDetail + global @RestControllerAdvice + domain exception → HTTP mapping for webstack's Spring Boot 3.4 + Kotlin stack.

## What is webstack error handling

webstack uses **`ProblemDetail`** — Spring 6's first-class implementation of **RFC 9457** ("Problem Details for HTTP APIs", July 2023), which obsoletes RFC 7807 (2016). The two specifications are backward-compatible: Spring 6's `ProblemDetail` implements both, and clients that speak RFC 7807 continue to work without change.

A problem detail response is a JSON document with a well-known media type and a fixed set of top-level fields. Inconsistent error shapes — `{"error": "not found"}` here, `{"message": "Order not found"}` there — collapse into a uniform, machine-readable envelope:

```json
{
  "type": "https://api.example.com/errors/ORDER_NOT_FOUND",
  "title": "Order not found",
  "status": 404,
  "detail": "No order with id 'ord-42abc' exists in this account.",
  "instance": "/orders/ord-42abc"
}
```

### RFC 9457 standard fields

| Field | Description |
|-------|-------------|
| `type` | URI identifying the problem category. Defaults to `"about:blank"`. Should be dereferenceable. |
| `title` | Short human-readable summary. SHOULD NOT change between occurrences of the same type. |
| `status` | HTTP status code, mirroring the response status line. |
| `detail` | Occurrence-specific explanation to help the caller resolve the issue. Not a stack trace. |
| `instance` | URI for this specific occurrence. Spring sets it automatically to the request path. |

Additional fields are **extension members** (e.g., `violations`). RFC 9457 requires clients to ignore unrecognised extensions. The response `Content-Type` is `application/problem+json`. Jackson's `ProblemDetailJacksonMixin` handles serialisation automatically.

## Why ProblemDetail

**Standardised format.** Every error response from every endpoint shares the same envelope. Front-end and mobile clients parse one schema for all error cases.

**springdoc auto-exposure.** `spring.mvc.problemdetails.enabled=true` registers a `ResponseEntityExceptionHandler` for all built-in MVC exceptions. springdoc-openapi 2.x generates accurate error schemas from `ProblemDetail` return types without extra annotations.

**FE–BE common format.** The generated TypeScript SDK (`src/shared/api/generated/`) exposes a `ProblemDetail` type for uniform error display — no per-endpoint error parsing on the front end.

**`MessageSource` integration.** Spring resolves `title` and `detail` field values through `MessageSource`, enabling locale-aware messages without string literals in code.

**Content negotiation.** Jackson prioritises `application/problem+json` automatically. No explicit `produces` annotation needed.

## webstack convention

### File placement

Per the DDD/Hexagonal convention (see `shared/methodologies/hexagonal.md`), exception handlers are **secondary adapters in the `infrastructure/http/` layer of the module that owns the domain exception**:

```text
com.example.app/
├── billing/
│   ├── domain/
│   │   └── invoice/
│   │       └── InvoiceNotFoundException.kt   ← domain exception, pure Kotlin
│   └── infrastructure/
│       └── http/
│           ├── BillingController.kt
│           └── BillingExceptionHandler.kt    ← @RestControllerAdvice, scoped to billing
├── order/
│   ├── domain/
│   │   └── order/
│   │       └── OrderConflictException.kt
│   └── infrastructure/
│       └── http/
│           ├── OrderController.kt
│           └── OrderExceptionHandler.kt
└── shared/
    └── infrastructure/
        └── http/
            └── GlobalExceptionHandler.kt     ← catch-all for unknown RuntimeException
```

Each `@RestControllerAdvice` is scoped to the exception types it handles using `basePackages` or `assignableTypes`. Unknown exceptions fall through to `GlobalExceptionHandler`.

### Module-scoped `@RestControllerAdvice`

```kotlin
// billing/infrastructure/http/BillingExceptionHandler.kt
@RestControllerAdvice
class BillingExceptionHandler {

    @ExceptionHandler(InvoiceNotFoundException::class)
    fun handleNotFound(ex: InvoiceNotFoundException): ProblemDetail =
        ProblemDetail.forStatus(HttpStatus.NOT_FOUND).apply {
            type = URI.create("https://api.example.com/errors/INVOICE_NOT_FOUND")
            title = "Invoice not found"
            detail = ex.message
        }

    @ExceptionHandler(InvoiceDuplicateException::class)
    fun handleConflict(ex: InvoiceDuplicateException): ProblemDetail =
        ProblemDetail.forStatus(HttpStatus.CONFLICT).apply {
            type = URI.create("https://api.example.com/errors/INVOICE_DUPLICATE")
            title = "Invoice already exists"
            detail = ex.message
        }
}
```

### Domain exception → HTTP status mapping table

webstack maps the sealed `DomainException` hierarchy (see [Domain exception hierarchy](#domain-exception-hierarchy)) to HTTP status codes consistently:

| Domain exception class | HTTP status | Typical `type` path |
|------------------------|-------------|---------------------|
| `ValidationException` | 400 Bad Request | `/errors/<CODE>` |
| `NotFoundException` | 404 Not Found | `/errors/<CODE>` |
| `ConflictException` | 409 Conflict | `/errors/<CODE>` |
| `UnauthorizedException` | 401 Unauthorized | `/errors/<CODE>` |
| `ForbiddenException` | 403 Forbidden | `/errors/<CODE>` |

The catch-all `GlobalExceptionHandler` maps any unknown `RuntimeException` to 500 Internal Server Error, logs the full stack trace (the only place stack traces are logged), and returns a generic ProblemDetail without a `detail` value to avoid leaking internals.

### Global catch-all handler

```kotlin
// shared/infrastructure/http/GlobalExceptionHandler.kt
@RestControllerAdvice
class GlobalExceptionHandler {
    private val log = LoggerFactory.getLogger(javaClass)

    @ExceptionHandler(Exception::class)
    fun handleUnexpected(ex: Exception): ProblemDetail {
        log.error("Unhandled exception", ex)
        return ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR).apply {
            type = URI.create("https://api.example.com/errors/INTERNAL_ERROR")
            title = "An unexpected error occurred"
        }
    }
}
```

### Spring Boot auto-configuration

Enable Spring Boot's built-in ProblemDetail handling for all Spring MVC exceptions:

```yaml
# application.yml
spring:
  mvc:
    problemdetails:
      enabled: true
```

This registers a `ResponseEntityExceptionHandler` (order 0) that converts all Spring MVC exceptions (`MethodArgumentNotValidException`, `HttpRequestMethodNotSupportedException`, etc.) into ProblemDetail responses. Module-scoped handlers that need higher precedence use `@Order(Ordered.HIGHEST_PRECEDENCE)`.

## Domain exception hierarchy

Domain exceptions live in `<module>/domain/<aggregate>/` and are **pure Kotlin** — no Spring, JPA, or Jackson imports. The HTTP status code is assigned by the exception handler adapter, never by the domain class.

### Base sealed hierarchy

```kotlin
// shared/domain/DomainException.kt
sealed class DomainException(open val code: String, message: String) : RuntimeException(message)

class ValidationException(override val code: String, message: String) : DomainException(code, message)
class NotFoundException(override val code: String, message: String) : DomainException(code, message)
class ConflictException(override val code: String, message: String) : DomainException(code, message)
class UnauthorizedException(override val code: String, message: String) : DomainException(code, message)
class ForbiddenException(override val code: String, message: String) : DomainException(code, message)
```

### Module-specific exceptions

Individual aggregates throw typed subclasses, making the error code part of the type. File placement: `billing/domain/invoice/InvoiceNotFoundException.kt`.

```kotlin
class InvoiceNotFoundException(invoiceId: String) : NotFoundException(
    code = "INVOICE_NOT_FOUND",
    message = "No invoice with id '$invoiceId' exists.",
)
```

Domain aggregates throw these exceptions directly from business rule checks. The exception propagates through the application service (`@Transactional`) and is caught by `BillingExceptionHandler` in the HTTP adapter layer. The domain never imports `HttpStatus` or any HTTP-layer class.

## Error code catalog

Error codes are collected in a dedicated reference file `errors/error-codes.md` (alongside the module that owns them, or in a top-level `docs/errors/` directory for cross-module visibility). Each entry records the code, `type` URI, default message, and which module emits it.

### `type` URI convention

Pattern: `https://api.<domain>/errors/<ERROR_CODE>` (e.g., `https://api.example.com/errors/INVOICE_NOT_FOUND`).

The URI should be dereferenceable in production (a GET returns human-readable error documentation). In local development it need not resolve — the `type` field is a stable identifier regardless.

Each catalog entry records: `type` URI, HTTP status, owning module, English message template, and Korean message template.

## Locale messages

Spring resolves `ProblemDetail` message fields through `MessageSource`. The `detail` field and optionally the `title` field are looked up at runtime using keys of the form `error.<CODE>`.

### Message key convention

```
error.<ERROR_CODE>=<message template>
```

### `messages.properties` (English — default)

```properties
# src/main/resources/messages.properties
error.INVOICE_NOT_FOUND=No invoice with id ''{0}'' exists.
error.INVOICE_DUPLICATE=Invoice ''{0}'' has already been created.
error.VALIDATION_FAILED=Request validation failed. See violations for details.
error.INTERNAL_ERROR=An unexpected error occurred. Please try again later.
```

Add a matching `messages_ko.properties` file with the same keys and Korean values for each error code. The file follows the same `error.<CODE>` key convention.

### `MessageSource` injection in an exception handler

```kotlin
// billing/infrastructure/http/BillingExceptionHandler.kt
@RestControllerAdvice
class BillingExceptionHandler(private val messageSource: MessageSource) {

    @ExceptionHandler(InvoiceNotFoundException::class)
    fun handleNotFound(ex: InvoiceNotFoundException, locale: Locale): ProblemDetail {
        val msg = messageSource.getMessage("error.${ex.code}", arrayOf(ex.resourceId), ex.message, locale)
        return ProblemDetail.forStatus(HttpStatus.NOT_FOUND).apply {
            type = URI.create("https://api.example.com/errors/${ex.code}")
            title = "Invoice not found"
            detail = msg
        }
    }
}
```

Spring resolves `locale` from the `Accept-Language` request header via `LocaleContextHolder`. The `MessageSource` bean is auto-configured by Spring Boot; files in `src/main/resources/` are picked up automatically. Pass `Locale` as a parameter to `@ExceptionHandler` methods — no extra configuration needed.

## Validation error mapping

`MethodArgumentNotValidException` is thrown by Spring when a `@Valid`-annotated request body fails Bean Validation constraints (`@NotBlank`, `@Size`, `@Pattern`, etc.). webstack maps it to a ProblemDetail with a custom `violations` extension array.

### Violations extension

```kotlin
// shared/infrastructure/http/ValidationExceptionHandler.kt
data class FieldViolation(val field: String, val message: String)

@RestControllerAdvice
class ValidationExceptionHandler(private val messageSource: MessageSource) {

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidation(ex: MethodArgumentNotValidException, locale: Locale): ProblemDetail {
        val violations = ex.bindingResult.allErrors.map { error ->
            val field = if (error is FieldError) error.field else error.objectName
            FieldViolation(field = field, message = messageSource.getMessage(error, locale))
        }
        return ProblemDetail.forStatus(HttpStatus.BAD_REQUEST).apply {
            type = URI.create("https://api.example.com/errors/VALIDATION_FAILED")
            title = "Validation failed"
            detail = "One or more fields failed validation. See violations."
            setProperty("violations", violations)
        }
    }
}
```

`ProblemDetail.setProperty("violations", violations)` adds `violations` as a top-level extension member. Jackson's `ProblemDetailJacksonMixin` unwraps the internal `properties` map and renders extension members as top-level JSON fields — no custom serialiser needed.

Example response:

```json
{
  "type": "https://api.example.com/errors/VALIDATION_FAILED",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields failed validation. See violations.",
  "instance": "/invoices",
  "violations": [
    { "field": "amount", "message": "must be greater than 0" },
    { "field": "recipientEmail", "message": "must be a well-formed email address" }
  ]
}
```

The generated TypeScript SDK exposes `violations` as an optional field on `ProblemDetail`, giving the front end per-field error messages for inline form validation. The Zod schema at `src/features/<feature>/model/schema.ts` mirrors constraints client-side; the server-side `violations` is the safety net for bypassed validation.

## Anti-patterns

### 1. `e.printStackTrace()` in exception handlers

Stack traces written to stdout are unstructured and may leak internal class names to observers. Log with `log.error("...", ex)` exactly once — in `GlobalExceptionHandler.handleUnexpected`. All other handlers log at `warn` or lower without the full trace.

### 2. Throwing `RuntimeException` directly from domain code

An untyped `throw RuntimeException("invoice not found")` is caught as an unexpected error, returns 500, and generates a misleading alert. Domain exceptions must extend the `DomainException` hierarchy so handlers can map the correct status and error code.

### 3. try-catch blocks in controllers

Controllers (`@RestController`) do not catch exceptions. The `@RestControllerAdvice` chain is the designed interception point. Adding try-catch in a controller handler bypasses the uniform error format, breaks test assertions, and duplicates logic. Let exceptions propagate; add or adjust the relevant advice if an endpoint needs special treatment.

### 4. `ResponseEntity<String>` for error responses

Returning `ResponseEntity<String>` with a hand-crafted JSON string produces `Content-Type: application/json`, not `application/problem+json`, and bypasses Jackson's serialisation pipeline. Clients cannot parse the error as `ProblemDetail`. Always return `ProblemDetail` (or a subclass) from `@ExceptionHandler` methods.

### 5. HTTP status on domain objects

Domain classes are pure Kotlin. Importing `org.springframework.http.HttpStatus` in a domain exception couples the domain to HTTP transport and prevents reuse in non-HTTP contexts (scheduled jobs, consumers, CLI). HTTP status mapping belongs exclusively in the infrastructure adapter.

### 6. One monolithic `@RestControllerAdvice` for all modules

A single global handler must import every domain exception type, coupling all modules. Per-module handlers keep the exception dependency graph module-local.

## Sources

- **Spring Framework — Errors, REST, and Problem Details:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html — _authoritative_
- **RFC 9457 — Problem Details for HTTP APIs (IETF, July 2023):** https://datatracker.ietf.org/doc/html/rfc9457 — _authoritative_
- **RFC 7807 — Problem Details for HTTP APIs (IETF, March 2016, obsoleted by RFC 9457):** https://datatracker.ietf.org/doc/html/rfc7807 — _authoritative_
- **Spring Boot Reference — Spring MVC error handling:** https://docs.spring.io/spring-boot/reference/web/spring-mvc.html — _authoritative_
- **Maciej Walkowiak, "Problem Details (RFC 7807) with Spring Boot 3":** https://maciejwalkowiak.com/blog/problem-details-spring-boot-3/ — _community: Maciej Walkowiak_

Last verified: 2026-05-04 (Spring Boot 3.4.X / Spring 6.1.X / Kotlin 2.X / RFC 7807 + RFC 9457).
