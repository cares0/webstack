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

```
src/main/kotlin/com/<org>/<project>/
├── domain/                          # Pure — no Spring, no JPA, no Jackson
│   └── <aggregate>/
│       ├── <Entity>.kt              # aggregate root
│       ├── <Vo>.kt                  # value objects
│       ├── <Repo>.kt                # port (driven)
│       ├── <Event>.kt               # domain events
│       └── <Service>.kt             # domain service (if needed)
├── application/                     # use cases — orchestrate aggregates
│   └── <usecase>/
│       ├── <UseCase>UseCase.kt      # port (driving) — interface
│       ├── <UseCase>Service.kt      # impl
│       └── <UseCase>Command.kt      # input DTO (no Jackson here)
└── infrastructure/                  # adapters
    ├── http/
    │   ├── <Resource>Controller.kt  # primary adapter
    │   └── <Resource>Dto.kt         # Jackson-bound — translate to/from domain
    ├── persistence/
    │   ├── <Aggregate>JpaRepo.kt    # secondary adapter
    │   └── <Aggregate>Entity.kt     # JPA-bound — translate to/from domain
    └── config/
        └── <Bean>Config.kt          # Spring wiring
```

## Common mistakes

- Importing `org.springframework.*` in `domain/` — domain pollution.
- Returning JPA entities from the application layer — leaks persistence to controller.
- Application service calling repositories directly without using a port abstraction — couples app to infrastructure.

## References

- Cockburn, "Hexagonal Architecture" (2005).
- Tom Hombergs, *Get Your Hands Dirty on Clean Architecture* (2019).
- https://www.baeldung.com/hexagonal-architecture-ddd-spring
