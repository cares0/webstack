# REST API design (OpenAPI 3.1)

> Reference for build-be SubAgent and feature-architect SubAgent and contract-drift-detective SubAgent.
> Resource modelling, status codes, naming, pagination, ETag, idempotency, error format for webstack's OpenAPI 3.1 + Spring Boot backend.

## What is webstack REST design

webstack REST design is **contract-first**: the OpenAPI 3.1 YAML document is the single source of truth, authored before any backend or frontend code is written. Both ends derive from the contract — the frontend generates TypeScript types via `@hey-api/openapi-ts`, and the backend is verified at runtime by `contract-drift-detective` comparing the springdoc-emitted spec against `.webstack/contracts/<feature>.yaml`.

The design surface covered here spans:

- **Resource modelling** — how to name, structure, and nest URI paths.
- **HTTP semantics** — correct status codes, method selection, idempotency, caching.
- **Naming** — URI segment convention, JSON field convention, plural vs. singleton resources.
- **Pagination** — cursor-based keyset pagination with `Link` headers.
- **ETag and conditional requests** — optimistic concurrency via `If-Match` / `412`.
- **Idempotency** — `Idempotency-Key` header for safe POST mutations.
- **Error format** — ProblemDetail (RFC 9457) uniform envelope.
- **Versioning** — URI-prefix strategy; see `docs/backend/api-versioning.md` for full detail.

webstack chooses OpenAPI 3.1 (not 3.0) because 3.1 is a strict superset of JSON Schema 2020-12. Standard validators, Zod, and `@hey-api/openapi-ts` consume it directly without dialect translation. See `shared/methodologies/api-first.md` for the full rationale.

## Why this approach

The rules in this document are the HTTP-level expression of the contract-first principle documented in `shared/methodologies/api-first.md`. That methodology defines the workflow; this document defines the design constraints that make the contract trustworthy:

**Uniformity lowers cognitive load.** When every endpoint uses the same status codes, the same error envelope, the same pagination shape, and the same field naming convention, a developer joining any feature can read the contract and know what to expect without feature-specific documentation.

**Contract integrity.** webstack's `contract-drift-detective` agent diffs the live springdoc spec against the contract YAML. Drift is detected only if the contract was precise in the first place — sloppy HTTP semantics (200 for errors, inconsistent status codes) produce false-negative drift checks.

**Frontend type safety.** `@hey-api/openapi-ts` generates TypeScript types and Zod schemas from the OpenAPI 3.1 contract. Correct schema modelling in the contract means correct types in the frontend. A 404 documented as a 200 with a nullable body generates a union type that forces null-checks everywhere instead of a clean error path.

**Security by design.** Correct 401/403 codes are not cosmetic — frontend routing and middleware intercept them. A 200 returned for an unauthenticated request bypasses the frontend's authentication guard entirely.

## Resource modelling

Resources are **nouns** expressed as URI path segments. Actions are expressed through HTTP method choice or, when necessary, as sub-resource nouns.

### Collection and item URIs

```
GET    /v1/orders           → list orders (collection)
POST   /v1/orders           → create an order
GET    /v1/orders/{orderId} → get one order (item)
PUT    /v1/orders/{orderId} → replace an order
PATCH  /v1/orders/{orderId} → partial update
DELETE /v1/orders/{orderId} → delete an order
```

Nesting expresses ownership or containment:

```
GET    /v1/users/{userId}/orders         → orders owned by a user
POST   /v1/users/{userId}/orders         → create an order for a user
GET    /v1/users/{userId}/orders/{orderId}
```

Keep nesting to two levels maximum. `/v1/a/{aid}/b/{bid}/c/{cid}` is difficult to read and cache. If you need a third level, consider a top-level collection filtered by a query parameter.

### Actions as sub-resources (POST)

When a state transition cannot be expressed cleanly with a CRUD method, use a sub-resource noun and POST:

```
POST /v1/orders/{orderId}/cancellations   → cancel an order
POST /v1/orders/{orderId}/confirmations   → confirm an order
POST /v1/invoices/{invoiceId}/void        → void an invoice
```

The sub-resource represents the event or state transition, not the entity being mutated. This keeps the URI noun-based, allows idempotency keys on the POST, and produces clean audit-log semantics. Prefer the plural form (`/cancellations`) when the sub-resource is a first-class entity with its own lifecycle; use the singular noun (`/cancel` → `/void`) only for one-shot state transitions with no retrievable artifact.

**Never use verb URIs:**

```
# Wrong
POST /v1/getOrder
POST /v1/cancelOrder
GET  /v1/fetchUserOrders
```

### Singleton resources

A singleton resource is a single instance scoped to its parent, addressable without an ID:

```
GET  /v1/users/{userId}/profile    → the profile of a user (one per user)
PUT  /v1/users/{userId}/profile    → replace the profile
```

Use the singular noun (no `{id}` segment) for singletons.

### OpenAPI 3.1 path item example

```yaml
# .webstack/contracts/order.yaml (excerpt)
paths:
  /v1/orders:
    post:
      operationId: placeOrder
      tags: [orders]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PlaceOrderRequest'
      responses:
        '201':
          description: Order placed successfully.
          headers:
            Location:
              schema:
                type: string
                format: uri
              description: URI of the created order.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          $ref: '#/components/responses/BadRequest'
        '422':
          $ref: '#/components/responses/UnprocessableEntity'

  /v1/orders/{orderId}:
    get:
      operationId: getOrder
      tags: [orders]
      parameters:
        - $ref: '#/components/parameters/OrderId'
      responses:
        '200':
          description: Order found.
          headers:
            ETag:
              schema:
                type: string
              description: Strong ETag for conditional updates.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          $ref: '#/components/responses/NotFound'
```

### Kotlin controller

```kotlin
// order/infrastructure/http/OrderController.kt
@RestController
@RequestMapping("/v1/orders")
class OrderController(
    private val placeOrder: PlaceOrderUseCase,
    private val getOrder: GetOrderUseCase,
) {
    @PostMapping
    fun place(
        @Valid @RequestBody req: PlaceOrderRequest,
        @RequestHeader(value = "Idempotency-Key", required = false) idempotencyKey: String?,
    ): ResponseEntity<OrderResponse> {
        val order = placeOrder(req.toCommand(), idempotencyKey)
        return ResponseEntity
            .created(URI.create("/v1/orders/${order.orderId}"))
            .body(order.toResponse())
    }

    @GetMapping("/{orderId}")
    fun get(@PathVariable orderId: String): ResponseEntity<OrderResponse> {
        val order = getOrder(orderId)
        return ResponseEntity.ok()
            .eTag("\"${order.version}\"")
            .body(order.toResponse())
    }
}
```

## HTTP status codes

The table below covers all 16 codes used in webstack APIs. Return the **most specific** applicable code; never substitute a generic 200 for a more precise success code, and never use 200 for an error condition.

| Code | Meaning | webstack usage |
|------|---------|----------------|
| **200 OK** | Request succeeded; response body contains the result. | `GET`, `PUT`, `PATCH` responses; also `POST` when the response is not a new resource (e.g., auth token exchange). RFC 9110 §15.3.1 |
| **201 Created** | Resource created; `Location` header points to the new resource. | `POST` to a collection when a new entity is persisted. Always include `Location`. RFC 9110 §15.3.2 |
| **204 No Content** | Request succeeded; no response body. | `DELETE`, `PUT` / `PATCH` when the caller does not need the updated representation. RFC 9110 §15.3.5 |
| **301 Moved Permanently** | Resource permanently at a new URI; clients should update bookmarks. | Resource renames or path restructuring between versions. Rare in APIs; prefer `410` if the resource is gone. RFC 9110 §15.4.2 |
| **302 Found** | Temporary redirect; original URI remains canonical. | OAuth2 flows, temporary maintenance redirects. RFC 9110 §15.4.3 |
| **304 Not Modified** | Resource unchanged since the conditional request's validator. | `GET` with `If-None-Match` or `If-Modified-Since`; caching. RFC 9110 §15.4.5 |
| **400 Bad Request** | Request syntax is malformed or structurally invalid. | Missing required fields, type mismatches, unparseable JSON. Use `422` for syntactically valid but semantically invalid input. RFC 9110 §15.5.1 |
| **401 Unauthorized** | Authentication required and not provided or invalid. | Missing/expired/invalid JWT or API key. Response must include a `WWW-Authenticate` challenge. RFC 9110 §15.5.2 |
| **403 Forbidden** | Authenticated but not authorised for the requested operation. | Insufficient role or scope. Do not reveal whether the resource exists. RFC 9110 §15.5.4 |
| **404 Not Found** | Resource does not exist (or must not be revealed to this caller). | Item not found by ID. Also use when `403` would reveal existence. RFC 9110 §15.5.5 |
| **409 Conflict** | Request conflicts with current resource state. | Duplicate creation, business-rule violation (e.g., order already shipped). Map `ConflictException` here. RFC 9110 §15.5.10 |
| **410 Gone** | Resource existed but has been permanently deleted. | Hard-deleted records where clients should remove stored references. RFC 9110 §15.5.11 |
| **412 Precondition Failed** | `If-Match` ETag did not match; optimistic concurrency failed. | Concurrent update conflict; client must re-fetch and retry. RFC 9110 §15.5.13 |
| **422 Unprocessable Content** | Request is syntactically valid but semantically erroneous. | Bean Validation failures (`@NotBlank`, `@Size`, business-rule violations in request body). Return `violations` extension in ProblemDetail. RFC 9110 §15.5.21 |
| **429 Too Many Requests** | Rate limit exceeded. | Include `Retry-After` header (seconds or HTTP-date). Zalando guideline: use with `RateLimit-*` headers. |
| **500 Internal Server Error** | Unexpected server failure. | Unhandled `RuntimeException`; caught by `GlobalExceptionHandler`. Never expose stack trace. RFC 9110 §15.6.1 |

### 400 vs 422

Use **400** when the request is structurally invalid (JSON parse error, missing required header, wrong `Content-Type`). Use **422** when the JSON parses and deserialises successfully but the field values violate a constraint (`amount` is negative, `email` is malformed). Spring Boot's `spring.mvc.problemdetails.enabled=true` maps `MethodArgumentNotValidException` to 400 by default; webstack overrides this to 422 for field-level validation errors via `ValidationExceptionHandler` (see `docs/backend/error-handling.md`).

## Naming

### URI path segments

- **kebab-case**, lowercase, ASCII: `/sales-orders`, `/line-items`, `/payment-methods`.
- **Plural nouns** for collections: `/users`, `/orders`, `/invoices`.
- **Singular nouns** for singleton sub-resources: `/users/{id}/profile`, `/orders/{id}/status`.
- **No verbs**: `/getUser`, `/cancelOrder`, `/fetchInvoices` are all wrong.
- Path parameters use camelCase or lowerCamelCase: `{orderId}`, `{userId}`, `{lineItemId}`.

```yaml
# Correct
/v1/sales-orders/{orderId}/line-items

# Wrong
/v1/salesOrders/{order_id}/lineItems
/v1/getSalesOrders
```

### JSON field names

Spring Boot's default Jackson configuration serialises Kotlin/Java properties as **camelCase**. webstack keeps this default:

```json
{
  "orderId": "ord-abc123",
  "totalCents": 15000,
  "currencyCode": "KRW",
  "createdAt": "2026-05-03T09:00:00Z",
  "lineItems": [
    { "productId": "prod-1", "quantity": 2, "unitPriceCents": 7500 }
  ]
}
```

**Do not** use snake_case in JSON responses (that is Zalando's convention for their own APIs, not webstack's). webstack follows Spring Boot's Jackson default of camelCase for consistency with the TypeScript SDK, which expects camelCase by default from `@hey-api/openapi-ts`.

```yaml
# OpenAPI schema field names (camelCase)
components:
  schemas:
    OrderResponse:
      type: object
      required: [orderId, status, totalCents]
      properties:
        orderId:
          type: string
        status:
          type: string
          enum: [PENDING, CONFIRMED, SHIPPED, CANCELLED]
        totalCents:
          type: integer
          format: int64
        createdAt:
          type: string
          format: date-time
```

### Query parameter names

Use **camelCase** for query parameters to match field names: `?pageSize=20&afterCursor=xxx&sortBy=createdAt`.

## Pagination

webstack **prefers cursor-based pagination** for all collection endpoints. Offset pagination is permitted only for small, bounded, rarely-updated lists (e.g., reference data tables with < 1 000 items where position-shift risk is acceptable).

### Why cursor over offset

Offset pagination (`LIMIT n OFFSET k`) re-executes the full sort on every page and suffers from position-shift: if a row is inserted before the current offset, the last item of page N is repeated as the first item of page N+1 (or an item is skipped). Keyset cursor pagination seeks directly to the last-seen row using an indexed column, making it O(1) in the database and stable in the face of concurrent writes.

### Cursor format

The cursor is a **base64url-encoded** JSON object containing the keyset position. This makes it opaque to the caller (preventing cursor manipulation) while keeping it URL-safe and human-inspectable for debugging.

Keyset example for `(createdAt DESC, orderId ASC)`:

```json
{ "createdAt": "2026-05-02T14:23:11Z", "orderId": "ord-abc123" }
```

Base64url-encoded: `eyJjcmVhdGVkQXQiOiIyMDI2LTA1LTAyVDE0OjIzOjExWiIsIm9yZGVySWQiOiJvcmQtYWJjMTIzIn0`

The cursor must be treated as opaque by clients. Never parse or construct cursors manually; use the `next` cursor returned by the server.

### Request parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `integer` | Page size. Default `20`, max `100`. |
| `afterCursor` | `string` | Opaque cursor from the previous page's `next` field. Omit for the first page. |
| `sortBy` | `string` | Field to sort by. Default `createdAt`. |
| `sortDir` | `string` | `asc` or `desc`. Default `desc`. |

### Response shape

```yaml
components:
  schemas:
    OrderPage:
      type: object
      required: [items, pagination]
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderResponse'
        pagination:
          $ref: '#/components/schemas/CursorPaginationMeta'

    CursorPaginationMeta:
      type: object
      required: [limit, hasMore]
      properties:
        limit:
          type: integer
        hasMore:
          type: boolean
        nextCursor:
          type: string
          nullable: true
          description: >
            Base64url-encoded opaque cursor. Present when hasMore is true.
            Pass as afterCursor in the next request.
        totalCount:
          type: integer
          nullable: true
          description: >
            Total item count. Omitted when computation is expensive (large tables).
```

Example response:

```json
{
  "items": [ /* ... */ ],
  "pagination": {
    "limit": 20,
    "hasMore": true,
    "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTA1LTAyVDE0OjIzOjExWiIsIm9yZGVySWQiOiJvcmQtYWJjMTIzIn0"
  }
}
```

### Link header (RFC 8288)

In addition to the `pagination` body field, webstack includes a `Link` header for RFC 8288 / RFC 5988 compliant clients:

```
Link: </v1/orders?afterCursor=eyJ...&limit=20>; rel="next"
```

The `rel="next"` relation is registered in the IANA Link Relation Types registry. The URL in the `Link` header is fully-formed and immediately usable — the client need not construct it. When there is no next page, the `Link` header is absent (not an empty string).

```kotlin
// order/infrastructure/http/OrderController.kt
@GetMapping
fun list(
    @RequestParam(defaultValue = "20") limit: Int,
    @RequestParam(required = false) afterCursor: String?,
): ResponseEntity<OrderPage> {
    val page = listOrders(ListOrdersQuery(limit, afterCursor))
    val response = ResponseEntity.ok()
    if (page.pagination.hasMore) {
        val nextUrl = "/v1/orders?limit=$limit&afterCursor=${page.pagination.nextCursor}"
        response.header("Link", "<$nextUrl>; rel=\"next\"")
    }
    return response.body(page)
}
```

### Offset pagination (limited use)

When offset pagination is unavoidable, use `page` (0-based) and `size` parameters. Always cap `size` at 100. Include `totalElements` and `totalPages` in the response. Do not mix offset and cursor pagination in the same collection endpoint.

## ETag + conditional requests

ETags enable **optimistic concurrency** — they let a client verify that the server's copy of a resource has not changed since the client last read it, before submitting an update.

### Weak vs strong ETags

| Type | Format | Semantics |
|------|--------|-----------|
| **Strong** | `"abc123"` (quoted string) | Byte-for-byte identical representations have the same ETag. Safe for byte-range requests and caching intermediaries. |
| **Weak** | `W/"abc123"` (W/ prefix) | Semantically equivalent representations (e.g., same logical content, different whitespace) may share an ETag. Not usable for byte-range requests. |

webstack uses **strong ETags** derived from the aggregate's optimistic-lock version (JPA `@Version` or a domain-level `version` field). The ETag value is the version integer or a SHA-256 hash of the serialised representation, wrapped in double quotes.

### Reading a resource with ETag

```http
GET /v1/orders/ord-abc123 HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
ETag: "42"
Content-Type: application/json

{ "orderId": "ord-abc123", "status": "PENDING", ... }
```

### Conditional update (If-Match)

The client sends back the ETag it received. The server rejects the update with `412` if the ETag no longer matches:

```http
PUT /v1/orders/ord-abc123/status HTTP/1.1
Content-Type: application/json
If-Match: "42"

{ "status": "CONFIRMED" }
```

Server response when ETag matches (concurrent modification did not occur):

```http
HTTP/1.1 200 OK
ETag: "43"
```

Server response when ETag does not match (another client already updated the resource):

```http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/errors/PRECONDITION_FAILED",
  "title": "Precondition failed",
  "status": 412,
  "detail": "The resource was modified since your last read. Re-fetch and retry."
}
```

The client must re-fetch (`GET`) to obtain the current state and ETag, reconcile any conflicts, then re-submit.

### Spring Boot implementation

```kotlin
// order/infrastructure/http/OrderController.kt
@PutMapping("/{orderId}/status")
fun updateStatus(
    @PathVariable orderId: String,
    @Valid @RequestBody req: UpdateOrderStatusRequest,
    @RequestHeader("If-Match") ifMatch: String,
): ResponseEntity<OrderResponse> {
    val currentETag = "\"${getOrder(orderId).version}\""
    if (ifMatch != currentETag) {
        throw PreconditionFailedException(orderId)  // maps to 412 in OrderExceptionHandler
    }
    val updated = updateOrderStatus(orderId, req.toCommand())
    return ResponseEntity.ok()
        .eTag("\"${updated.version}\"")
        .body(updated.toResponse())
}
```

### Cache validation (If-None-Match)

For read-heavy endpoints, the client may send `If-None-Match` with the stored ETag:

```http
GET /v1/orders/ord-abc123 HTTP/1.1
If-None-Match: "42"

HTTP/1.1 304 Not Modified
ETag: "42"
```

Spring's `ResponseEntity.ok().eTag(...)` builder handles `If-None-Match` evaluation automatically when the controller returns an `ETag` header; no manual comparison is needed for `304` responses.

### OpenAPI 3.1 declaration

```yaml
# Declare ETag on the GET response
/v1/orders/{orderId}:
  get:
    responses:
      '200':
        headers:
          ETag:
            required: true
            schema:
              type: string
              pattern: '^"[^"]+"$'
            description: Strong ETag. Pass in If-Match for conditional updates.

# Declare If-Match on the PUT operation
  put:
    parameters:
      - name: If-Match
        in: header
        required: true
        schema:
          type: string
        description: >
          ETag from a prior GET. Request is rejected with 412 if the
          resource has been modified since the ETag was issued.
```

## Idempotency

**Idempotency** means repeating a request produces the same result as sending it once. GET, HEAD, PUT, DELETE, OPTIONS are idempotent by the HTTP specification (RFC 9110 §9.2.2). POST is **not** — submitting the same POST twice creates two resources by default.

webstack provides server-side idempotency for POST mutation endpoints via the `Idempotency-Key` header, following the Stripe pattern.

### Idempotency-Key header

| Property | Value |
|----------|-------|
| Header name | `Idempotency-Key` |
| Recommended format | UUID v4 (`550e8400-e29b-41d4-a716-446655440000`) |
| Max length | 255 characters |
| Scope | One (endpoint + method + client) combination |
| Storage window | 24 hours from first request |

The client generates a fresh UUID per logical operation attempt. On retry, the **same UUID** is sent. The server deduplicates on the key and returns the stored response — including 5xx errors captured from the first attempt.

Do not use PII (email address, national ID) as an idempotency key value.

### Server-side deduplication

On receiving a POST with `Idempotency-Key`:

1. **Look up** the key in the idempotency store (Redis or a dedicated DB table).
2. **If found and completed**: return the stored status code + body. Do not re-execute.
3. **If found and in-flight**: return `409 Conflict` (concurrent duplicate). The client should wait and retry.
4. **If not found**: execute, persist key + result atomically, return result.
5. **If request body differs from stored body**: return `409 Conflict` — accidental misuse guard (Stripe pattern).

The idempotency record expires after 24 hours. After expiry, the same key is treated as a new request.

```kotlin
// shared/application/IdempotencyService.kt
@Service
class IdempotencyService(private val store: IdempotencyStore) {

    fun <T> execute(key: String?, request: Any, block: () -> T): T {
        if (key == null) return block()

        store.findByKey(key)?.let { record ->
            if (record.requestHash != request.toHash()) {
                throw IdempotencyConflictException(key)   // 409
            }
            @Suppress("UNCHECKED_CAST")
            return record.response as T
        }

        return block().also { result ->
            store.save(IdempotencyRecord(key, request.toHash(), result))
        }
    }
}
```

### OpenAPI 3.1 declaration

```yaml
# Reusable parameter in components
components:
  parameters:
    IdempotencyKey:
      name: Idempotency-Key
      in: header
      required: false
      schema:
        type: string
        maxLength: 255
        example: 550e8400-e29b-41d4-a716-446655440000
      description: >
        Client-generated UUID v4. When provided, the server deduplicates
        this request for 24 hours. Identical key + identical body returns
        the original response. Identical key + different body returns 409.

# Reference in POST operations
paths:
  /v1/orders:
    post:
      parameters:
        - $ref: '#/components/parameters/IdempotencyKey'
```

## Error format

webstack uses **ProblemDetail** (RFC 9457, Spring 7 native) as the uniform error envelope for all HTTP error responses. Full detail — including the domain exception hierarchy, `@RestControllerAdvice` placement, `violations` extension, and `MessageSource` locale integration — is in `docs/backend/error-handling.md`.

### Minimum error response shape

```json
{
  "type": "https://api.example.com/errors/ORDER_NOT_FOUND",
  "title": "Order not found",
  "status": 404,
  "detail": "No order with id 'ord-abc123' exists.",
  "instance": "/v1/orders/ord-abc123"
}
```

`Content-Type: application/problem+json` (not `application/json`).

### Error code catalog

Error codes are uppercase strings embedded in the `type` URI:

```
https://api.example.com/errors/<ERROR_CODE>
```

Each bounded context maintains its own catalog (`docs/errors/<module>-error-codes.md`). Cross-module visibility is achieved by aggregating into `docs/errors/`. Each entry records: code, type URI, HTTP status, owning module, English message template.

### Validation error (422) with violations extension

```json
{
  "type": "https://api.example.com/errors/VALIDATION_FAILED",
  "title": "Validation failed",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/v1/orders",
  "violations": [
    { "field": "totalCents", "message": "must be greater than 0" },
    { "field": "currencyCode", "message": "must be a valid ISO 4217 code" }
  ]
}
```

The `violations` array is a ProblemDetail extension member (RFC 9457 §3.1). The TypeScript SDK exposes `violations` as an optional field on `ProblemDetail`; the frontend uses it for inline form validation.

### OpenAPI 3.1 reusable error responses

```yaml
components:
  responses:
    BadRequest:
      description: Request is malformed or structurally invalid.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    NotFound:
      description: Resource not found.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    UnprocessableEntity:
      description: Validation failed.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetailWithViolations'
    Conflict:
      description: Resource state conflict.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    PreconditionFailed:
      description: ETag mismatch; re-fetch and retry.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'

  schemas:
    ProblemDetail:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri

    ProblemDetailWithViolations:
      allOf:
        - $ref: '#/components/schemas/ProblemDetail'
        - type: object
          properties:
            violations:
              type: array
              items:
                type: object
                required: [field, message]
                properties:
                  field:
                    type: string
                  message:
                    type: string
```

## Versioning

webstack versions APIs using a URI prefix (`/v1/`, `/v2/`). Full detail — including breaking vs non-breaking change policy, `Deprecation` and `Sunset` headers, springdoc `GroupedOpenApi` configuration, and the sunset process — is in `docs/backend/api-versioning.md`.

### Summary

| Scope | Rule |
|-------|------|
| Breaking change | New URI prefix (`/v2/`). Old prefix continues until sunset. |
| Non-breaking additive change | No new prefix; bump `info.version` minor. |
| Deprecation | Add `Deprecation: @<epoch>` + `Sunset: <http-date>` response headers on day 1 of deprecation. |
| Minimum sunset window | 6 months public, 3 months internal. |
| Version-less endpoints | Forbidden. All public paths start with `/v1/` or later. |

The `contract-drift-detective` agent verifies each version group independently via springdoc's per-version API docs endpoints (`/v3/api-docs/v1`, `/v3/api-docs/v2`).

## webstack convention

### OpenAPI 3.1 schema authoring rules

1. **Use `$ref` everywhere.** Inline schemas beyond primitive types make contracts hard to read and break the TypeScript codegen's type deduplication. All request bodies, response bodies, and reusable parameters go in `components/`.

2. **`nullable` is a JSON Schema 2020-12 type union**, not a keyword.

   ```yaml
   # OpenAPI 3.1 — correct
   nextCursor:
     type: ["string", "null"]

   # OpenAPI 3.0 — wrong in 3.1
   nextCursor:
     type: string
     nullable: true
   ```

3. **Required fields are in the `required` array**, not on individual properties.

4. **Use `format`** for wire types: `int32`, `int64`, `float`, `double`, `date`, `date-time`, `uuid`, `uri`.

5. **Enums**: list all known values. Add an `UNKNOWN` or `OTHER` sentinel when the server may emit unlisted values (allows client forward-compatibility).

6. **`additionalProperties: false`** on request schemas to reject unknown fields. Omit or set `true` on response schemas for forward-compatibility (clients ignore unknown fields per the robustness principle).

7. **`operationId`**: required, unique across all operations, camelCase verb-noun: `placeOrder`, `getOrder`, `listOrders`, `cancelOrder`, `updateOrderStatus`. The TypeScript SDK uses `operationId` as the function name.

8. **Document every non-200 response.** `contract-drift-detective` flags undocumented status codes as Critical drift.

### springdoc auto-exposure

springdoc-openapi 3.0.x (the Spring Boot 4 line) reads the live Spring MVC routing and Swagger/OpenAPI annotations to emit an OpenAPI 3.1 document at `/v3/api-docs`. Enable it:

```yaml
# application.yml
spring:
  mvc:
    problemdetails:
      enabled: true

springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
  show-actuator: false
```

Gradle dependency:

```kotlin
// Spring Boot 4 requires the springdoc 3.0.x line (2.x — incl. 2.8.x — targets Boot 3 only).
// Version in gradle/libs.versions.toml (see dependency-management.md §Backend version catalog).
implementation(libs.springdoc.webmvc.ui)
// Jackson 2 bridge: Boot 4 defaults to Jackson 3, but springdoc's swagger-core is still on
// Jackson 2. Without this the app fails to boot (ClassNotFoundException). Remove once
// swagger-core ships a Jackson 3 line (track swagger-core#4991).
implementation("org.springframework.boot:spring-boot-jackson2")
```

springdoc reads `@RestController`, `@RequestMapping`, `@Operation`, `@Parameter`, `@ApiResponse`, and `@Schema` annotations. Keep annotations minimal — the contract YAML is the source of truth. Use `@Operation` only to add `deprecated = true` or a summary that differs from the contract; avoid duplicating schema definitions already in the YAML.

### contract-drift-detective integration

The `contract-drift-detective` agent runs at P7 (post build-be). It fetches the live springdoc spec and diffs it against `.webstack/contracts/<feature>.yaml` with **oasdiff** (deterministic OpenAPI diff — breaking changes block the merge; runtime-only endpoints count as contract leakage). REST design violations it detects:

| Violation | Severity |
|-----------|----------|
| Status code in implementation absent from contract | Critical |
| `operationId` mismatch | Critical |
| Required field missing from implementation schema | Critical |
| Field type mismatch | Important |
| Response header (ETag, Location, Link) absent from contract | Important |
| `deprecated: false` in runtime vs `true` in contract | Critical |

Pass the per-version URL:

```
springdoc_url: http://localhost:8080/v3/api-docs/v1
contract_path: .webstack/contracts/order-v1.yaml
```

## Anti-patterns

### 1. Verb URIs

```
# Wrong
POST /v1/getOrder
POST /v1/cancelOrder
GET  /v1/fetchUserOrders
GET  /v1/searchOrders?action=list
```

Resources are nouns. The HTTP method is the verb. Verb URIs double-encode the action and make routing, caching, and contract documentation inconsistent.

### 2. 200 OK with an error body

```json
HTTP/1.1 200 OK

{ "success": false, "error": "Order not found" }
```

This is the most dangerous anti-pattern. HTTP middleware (frontend auth guards, CDN caches, monitoring tools) inspects the status code, not the body. A 200 with an error body is cached as a successful response, bypasses auth guards, and poisons metrics. Always use the correct 4xx or 5xx code and return `application/problem+json`.

### 3. 200 for authentication failure

```json
HTTP/1.1 200 OK

{ "authenticated": false, "message": "Token expired" }
```

Authentication failures must return 401 with `WWW-Authenticate` header. Returning 200 makes the API impossible to protect with standard middleware.

### 4. Inconsistent pagination response shapes

Each collection endpoint returning a different pagination envelope (one with `data`/`meta`, another with `items`/`page`, another flat list) forces the frontend to write custom parsers per endpoint. webstack enforces `CursorPaginationMeta` across all paginated responses.

### 5. Query parameters for resource fields

```
# Wrong
GET /v1/orders?field_orderId=abc&field_status=PENDING
POST /v1/orders?totalCents=1500&currencyCode=KRW
```

Resource fields belong in the request body (`POST`/`PUT`/`PATCH`) or in the URI path (`GET` by ID). Query parameters are for filtering, sorting, pagination, and sparse fieldsets — not resource attributes.

### 6. snake_case in URI segments or JSON fields

webstack uses kebab-case URI segments and camelCase JSON fields. Mixing in snake_case (`/v1/sales_orders`, `total_cents`) creates inconsistency in logs, the OpenAPI contract, and the TypeScript SDK. It also conflicts with the Spring Jackson defaults that the TypeScript codegen expects.

### 7. Omitting the Location header on 201

A 201 Created response must include a `Location` header pointing to the created resource:

```
Location: /v1/orders/ord-abc123
```

Without it, the client cannot navigate to the new resource without a separate list+filter request.

### 8. ETag without If-Match enforcement

Publishing an `ETag` header on `GET` responses implies to clients that conditional updates are supported. If `PUT`/`PATCH` does not validate `If-Match`, concurrent writes silently overwrite each other. Either enforce `If-Match` on all mutating operations that emit ETags, or do not emit ETags.

## Sources

- **RFC 9110 — HTTP Semantics (IETF, June 2022):** https://datatracker.ietf.org/doc/html/rfc9110 — _authoritative_
- **OpenAPI Specification 3.1.0 (OpenAPI Initiative):** https://spec.openapis.org/oas/v3.1.0 — _authoritative; community: OpenAPI Initiative_
- **Stripe — Idempotent Requests:** https://docs.stripe.com/api/idempotent_requests — _community: Stripe_
- **Zalando RESTful API Guidelines:** https://opensource.zalando.com/restful-api-guidelines/ — _community: Zalando Engineering_
- **RFC 8288 — Web Linking (IETF, October 2017):** https://datatracker.ietf.org/doc/html/rfc8288 — _authoritative_

Last verified: 2026-06-22 (RFC 9110 / OpenAPI 3.1 / Spring Boot 4.0.X / springdoc 3.0.X).
