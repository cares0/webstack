# Hexagonal Architecture (Ports & Adapters)

> Source: Alistair Cockburn, "Hexagonal Architecture" (2005). https://alistair.cockburn.us/hexagonal-architecture/

## The Core Idea

Application core (domain) is isolated from external concerns (HTTP, DB, message queues, UI). External concerns plug into the core via **ports** (interfaces). **Adapters** translate between port contracts and external technologies.

```
                  ┌──────────────────────┐
   HTTP Request──▶│ HTTP Adapter         │──▶ Port (use case interface)
                  └──────────────────────┘            │
                                                      ▼
                              ┌──────────────────────────────┐
                              │      DOMAIN (pure)           │
                              │   ┌──────────────────────┐   │
                              │   │ Application Service  │   │
                              │   │   (use case impl)    │   │
                              │   └──────────────────────┘   │
                              │   ┌──────────────────────┐   │
                              │   │ Aggregates / VOs     │   │
                              │   └──────────────────────┘   │
                              └──────────────────────────────┘
                                                      ▲
                                                      │
                  ┌──────────────────────┐            │
   Database  ◀───│ JPA Adapter          │◀── Port (Repository interface)
                  └──────────────────────┘
```

## Ports

**Driving ports** (input): use case interfaces called by primary adapters (HTTP controllers, message consumers, CLI).
**Driven ports** (output): SPI for secondary adapters (repositories, external service clients, event publishers).

## Adapters

**Primary adapters** drive the application: REST controller, GraphQL resolver, CLI command.
**Secondary adapters** are driven by the application: JPA repository implementation, HTTP client, Kafka publisher.

## Why this in webstack

1. **Domain testability** — domain runs without Spring container. KoTest BehaviorSpec for aggregates is pure JVM.
2. **Swap infrastructure freely** — JPA → jOOQ, Kafka → SQS, REST → gRPC, all without touching domain.
3. **Contract-first alignment** — OpenAPI contract maps to driving ports. Drift detected by `contract-drift-detective`.

## Spring + Kotlin package mapping (build-be enforces)

webstack composes Hexagonal with **Spring Modulith**: each top-level package below the application root is a Modulith module that maps 1:1 to a DDD bounded context (e.g., `billing`, `catalog`, `order`). The hexagonal layers — `domain/`, `application/`, `infrastructure/` — live **inside** each module, not at the top level. This keeps cross-module communication via published events and the Modulith verifier enforces the boundary.

```
src/main/kotlin/com/<org>/<project>/
├── <Project>Application.kt          # @SpringBootApplication
├── billing/                         # module = bounded context (Modulith)
│   ├── package-info.java            # @ApplicationModule(displayName="Billing")
│   ├── domain/                      # Pure — no Spring, no JPA, no Jackson
│   │   └── <aggregate>/
│   │       ├── <Entity>.kt          # aggregate root
│   │       ├── <Vo>.kt              # value objects
│   │       ├── <Repo>.kt            # port (driven)
│   │       ├── <Event>.kt           # domain events (public — cross-module subscribers read this)
│   │       └── <Service>.kt         # domain service (if needed)
│   ├── application/                 # use cases — orchestrate aggregates within this BC
│   │   └── <usecase>/
│   │       ├── <UseCase>UseCase.kt  # port (driving) — interface
│   │       ├── <UseCase>Service.kt  # impl, @Service @Transactional
│   │       └── <UseCase>Command.kt  # input DTO (no Jackson here)
│   └── infrastructure/              # adapters — Modulith treats this as private to billing
│       ├── http/
│       │   ├── <Resource>Controller.kt   # primary adapter
│       │   └── <Resource>Dto.kt          # Jackson-bound — translate to/from domain
│       ├── persistence/
│       │   ├── <Aggregate>JpaRepo.kt     # secondary adapter
│       │   └── <Aggregate>Entity.kt      # JPA-bound — translate to/from domain
│       └── config/
│           └── <Bean>Config.kt           # Spring wiring scoped to this module
├── catalog/                         # another bounded context, same internal shape
│   ├── package-info.java
│   ├── domain/...
│   ├── application/...
│   └── infrastructure/...
└── order/                           # another bounded context
    ├── package-info.java
    ├── domain/...
    ├── application/...
    └── infrastructure/...
```

Module-internal types (anything under `<module>/application/` or `<module>/infrastructure/`) are **private** to the module per Modulith conventions. Other modules can only depend on the module's public surface — typically the domain events and any application service interface that is explicitly part of the module's API. Cross-module communication is via `@ApplicationModuleListener` (transactional async event handlers), never via direct service calls into another module's `application/` or `infrastructure/`.

For projects that genuinely need only one bounded context, you can collapse to a single module — `src/main/kotlin/com/<org>/<project>/<the-module>/{domain,application,infrastructure}/`. Adding more BCs later means new sibling top-level packages, each with the same `package-info.java` + internal layered structure.

See `docs/backend/spring-modulith.md` for the verifier test, `@ApplicationModule` annotation details, and the event publication registry.

## Common mistakes

- Importing `org.springframework.*` in `<module>/domain/` — domain pollution; the verifier won't catch this on its own (it checks cross-module boundaries, not framework leakage), so keep it as a code-review rule.
- Returning JPA entities from the application layer — leaks persistence to the controller.
- Application service calling repositories directly without using a port abstraction — couples app to infrastructure.
- **Calling another module's application service directly** instead of publishing an event for it to subscribe to. The Modulith verifier flags this, but the design issue is upstream: cross-module synchronous calls reintroduce the coupling that the BC boundary was meant to remove.
- Splitting modules **by hexagonal layer** (a single `domain/` module + a single `application/` module + a single `infrastructure/` module). This inverts the model — modules are domain-shaped, layers live inside them.

## Pragmatism — when is the full layer cost worth it?

Hexagonal architecture, like DDD, has a setup cost: every aggregate gets a port + adapter pair, every external collaborator goes through an interface, mapping code shuttles data across layer boundaries. For a webstack-target project (1-person greenfield) the upfront cost is meaningful — typically 30-50% more code per feature than a "Spring service calls JPA repository directly" baseline.

The cost is justified when:

- **Multiple incoming channels.** REST + scheduled jobs + a CLI all driving the same use case. Each gets its own primary adapter; the use case stays single.
- **Multiple outgoing channels.** Persistence in JPA today, a queue tomorrow, a third-party HTTP client next quarter. Each is a secondary adapter; the domain is unaware.
- **Genuine domain logic with invariants.** Aggregate roots only earn their keep when there are rules to enforce — "an Invoice cannot be marked paid more than once", "an Order's total must equal the sum of its line items". For thin CRUD wrappers, the aggregate root just delegates to the repository; the abstraction adds nothing.
- **Test isolation matters.** Pure-domain unit tests run in milliseconds without Spring, JPA, or a Postgres container. If you need that speed (large test suites, fast feedback loops), Hexagonal's pure-domain layer is what enables it.
- **You expect to live with this codebase for >2 years.** The refactor cost from "Spring + JPA monolithic service" to "Hexagonal" grows roughly linearly with code size and is painful at any scale beyond toy. Investing upfront is cheaper than retrofitting.

The cost is **not** justified when:

- **The feature is a thin CRUD wrapper.** "Save user, fetch user, update user, delete user" with no business rules adds 5+ files for what should be 1.
- **The project is a throwaway prototype** with a known short lifespan and no plan for the second year.
- **There is exactly one incoming and one outgoing channel** and you are 100% sure that will stay true. (Most projects are wrong about this guess.)

For webstack's target — 1-person greenfield aiming for a public marketplace — Hexagonal is on. The architecture is the price of admission for the scale-out path. The `feature-architect` SubAgent flags the cost on each feature in webstack v2; v1 always emits full Hexagonal.

For a small CRUD-only feature inside a webstack project, the pragmatic shortcut is **collapsing the domain layer into the application service** for that one feature: the controller calls the application service, the service calls Spring Data JPA directly, no aggregate root or repository port. This is not idiomatic Hexagonal but it is honest about what the feature needs. Document the choice in `be-status.md` and revisit when business rules show up.

## References

- Cockburn, "Hexagonal Architecture" (2005).
- Tom Hombergs, *Get Your Hands Dirty on Clean Architecture* (2019).
- https://www.baeldung.com/hexagonal-architecture-ddd-spring

Last verified: 2026-04-26.
