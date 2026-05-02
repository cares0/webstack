# Domain-Driven Design (DDD)

> Sources:
>
> - Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (Blue Book, 2003)
> - Vaughn Vernon, *Implementing Domain-Driven Design* (Red Book, 2013)

## Strategic DDD

### Ubiquitous Language

Domain experts and developers share **one** vocabulary — captured in code, tests, docs. If the domain expert says "shipment", the code says `Shipment`, not `OrderItemDelivery`. Mismatched language signals an unrefined model.

### Bounded Context

A bounded context is a boundary within which a particular domain model is consistent. The same word can mean different things in different contexts:

- `Customer` in `Sales` context: prospect with conversion data.
- `Customer` in `Billing` context: account with payment history.

Each bounded context owns its model. Inter-context communication via published interfaces (anti-corruption layer or open host).

### Context Map

Documents how bounded contexts relate (Shared Kernel, Customer/Supplier, Conformist, Anti-Corruption Layer, Open Host Service, Published Language).

In webstack: each `feature` maps to one or more bounded contexts. `feature-architect` SubAgent proposes the bounded context for a new feature based on existing `.webstack/contracts/` and aggregates.

## Tactical DDD

### Entity

Identity-defined object. Two entities with the same field values are not the same — `User#1` ≠ `User#2`.

```kotlin
class User(val id: UserId, var email: Email, var displayName: String) {
    fun changeEmail(newEmail: Email) {
        require(newEmail != email) { "email unchanged" }
        this.email = newEmail
    }
}
```

### Value Object

Identity-less, defined by its attributes. Immutable. `Email("a@b.com")` == `Email("a@b.com")`.

```kotlin
@JvmInline
value class Email(val value: String) {
    init {
        require(value.matches(Regex("^[^@]+@[^@]+\\..+$"))) { "invalid email" }
    }
}
```

### Aggregate

Cluster of entities/VOs bounded by an **invariant**. One root entity gates all access. Persistence is per aggregate. Within an aggregate: strong consistency. Across: eventual.

```kotlin
class Order(val id: OrderId, val customerId: CustomerId) {
    private val _lines = mutableListOf<OrderLine>()
    val lines: List<OrderLine> get() = _lines.toList()

    fun addLine(productId: ProductId, qty: Int) {
        require(qty > 0)
        _lines.add(OrderLine(productId, qty))
    }
}
```

### Domain Event

Something significant happened. Past tense. Immutable record.

```kotlin
data class OrderPlaced(
    val orderId: OrderId,
    val customerId: CustomerId,
    val occurredAt: Instant
)
```

### Repository

Aggregate-level persistence interface. Defined in domain, implemented in infrastructure.

```kotlin
interface OrderRepository {
    fun save(order: Order)
    fun findById(id: OrderId): Order?
    fun findByCustomer(customerId: CustomerId): List<Order>
}
```

### Domain Service

Logic that doesn't belong to an entity or VO (often coordinates aggregates).

```kotlin
class TransferFundsService(
    private val accounts: AccountRepository
) {
    fun transfer(from: AccountId, to: AccountId, amount: Money) {
        val source = accounts.findById(from) ?: error("source not found")
        val target = accounts.findById(to) ?: error("target not found")
        source.withdraw(amount)
        target.deposit(amount)
        accounts.save(source); accounts.save(target)
    }
}
```

## DDD in webstack — what `build-be` enforces

1. Domain layer has **no** Spring/JPA/Jackson imports. Pure Kotlin.
2. One aggregate per package: `domain/<aggregate>/{Entity,Vo,Repo,Event,Service}.kt`.
3. Repository interface in domain, implementation in infrastructure.
4. Application service orchestrates aggregates via repositories. No domain logic in application.
5. Controller (infrastructure adapter) translates HTTP ↔ application service input/output. No domain logic in controller.

## When NOT to apply DDD

DDD's overhead — aggregate boundaries, repository ports, value objects, domain events, ubiquitous language discipline — only pays off when the domain has genuine complexity. Mismatched application of DDD slows MVP throughput without any of the long-term benefits.

Skip DDD (or apply it sparingly) when:

- **CRUD-only services** with no behavior — anemic model is fine. A "save row, read row, edit row, delete row" admin tool gets nothing from aggregates.
- **Single-actor utilities** without invariants worth defending. A todo list app for one user has no concurrency edge cases that an aggregate root would prevent.
- **Throwaway prototypes** with a known short lifespan. The value of DDD shows up at refactor time; if there is no refactor, there is no payoff.
- **First feature of a product where the domain isn't understood yet.** "DDD before discovery" produces fictional aggregates that need rework once real users land. Build the simplest thing, learn the domain, then introduce DDD where complexity warrants.

For webstack's target — a **1-person greenfield project aspiring to public marketplace usage** — DDD/Hexagonal/Modulith carries non-trivial boilerplate cost (3-4 abstraction layers per BC, mapping code at every boundary, ubiquitous language reviews). The trade-off: a project that **does** scale to a marketplace will have already paid the refactor cost upfront, and the architecture is set up for multiple developers and bounded contexts. webstack accepts the cost on purpose.

If you are 100% sure the project will stay 1-person + 1-domain forever, you can run thinner: a single Modulith module with conventional `@Service` + `@Repository` Spring code, no separate domain layer, JPA entities used directly. webstack's `feature-architect` SubAgent will flag the cost up-front during the initial feature mapping; the user can choose "thin" vs "full DDD" per feature in webstack v2 (v1 always emits full DDD).

The honest framing: full DDD is **insurance against future complexity**. If the future is certain to stay simple, you don't need the insurance.

## References

- Evans, *Domain-Driven Design*, Addison-Wesley (2003).
- Vernon, *Implementing Domain-Driven Design*, Addison-Wesley (2013).
- Vernon, "Effective Aggregate Design" (3-part article).
- https://martinfowler.com/bliki/BoundedContext.html

Last verified: 2026-04-26.
