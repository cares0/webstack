# Backend caching (Spring Cache + Caffeine)

> Reference for build-be SubAgent and backend-implementer.
> In-memory cache pattern with Spring Cache abstraction + Caffeine for webstack's single-VM backend.

## What is webstack BE caching

webstack backend caching uses Spring's **Cache abstraction** — a unified `@Cacheable`/`@CacheEvict`/`@CachePut` annotation model backed by **Caffeine** as the in-process store. The abstraction decouples caching from business logic: the same annotations work with any `CacheManager` implementation (Caffeine today, Redis if needed later).

Three annotations cover the full lifecycle:

| Annotation | When the method executes | Effect on cache |
|---|---|---|
| `@Cacheable` | Only on cache miss | Stores return value; returns stored value on hit |
| `@CachePut` | Always | Updates cache with latest return value; useful for mutations that also need a refreshed read view |
| `@CacheEvict` | Always (or before, if `beforeInvocation=true`) | Removes one entry or the entire cache region |

Spring Boot 4.0 auto-configures `CaffeineCacheManager` when both libraries are on the classpath. Activate with `@EnableCaching` on a dedicated `@Configuration` class.

## Why Caffeine in-memory

webstack targets a **single OCI A1 VM** (Ampere ARM, Oracle Free Tier). Caffeine is the right fit:

- **No external process** — Redis requires a second VM or managed service plus network overhead. Caffeine is in-JVM with zero network RTT.
- **Sub-microsecond latency** — heap reference lookup; orders of magnitude faster than a Redis round-trip even on localhost.
- **Near-optimal hit rate** — W-TinyLFU eviction (window + frequency + recency), achieving 95%+ hit rates at smaller cache sizes than plain LRU.
- **No serialization** — objects are stored as live Java references; no encode/decode overhead.
- **Operationally transparent** — heap usage appears in standard JVM metrics (`jvm.memory.used`); no separate process to monitor.

Trade-off: in-process caches are not shared across JVM instances. On a single VM this is never a concern. For multi-instance deployments see [Distributed alternative (Redis)](#distributed-alternative-redis).

## webstack convention

### Dependencies

```kotlin
// build.gradle.kts
implementation("org.springframework.boot:spring-boot-starter-cache")
implementation("com.github.ben-manes.caffeine:caffeine") // version managed by the Spring Boot BOM
```

### `@EnableCaching` and basic `CacheManager`

```kotlin
// shared/infrastructure/config/CacheConfig.kt
@Configuration
@EnableCaching
class CacheConfig {

    @Bean
    fun cacheManager(): CaffeineCacheManager = CaffeineCacheManager(
        "userOrders", "productDetail", "pricingRules",          // fixed cache names
    ).apply {
        setCaffeine(Caffeine.newBuilder().maximumSize(1_000)
            .expireAfterWrite(Duration.ofMinutes(10)).recordStats())
    }
}
```

Passing cache names to the `CaffeineCacheManager` constructor (or `setCacheNames(...)`) **fixes the set of caches and disables dynamic creation** — a `@Cacheable` referencing an unlisted name fails instead of silently creating a cache. The `setCaffeine(...)` spec then applies to those fixed names; it is not a fallback for as-yet-unseen names. (To keep dynamic creation while still customising the builder, omit the names and only call `setCaffeine(...)`.) `recordStats()` is required for Micrometer exposure (see [Observability](#observability)). For per-region TTL, use [Multiple caches with per-region TTL](#multiple-caches-with-per-region-ttl) below instead.

### `@Cacheable` — read-through

```kotlin
@Service
@Transactional(readOnly = true)
class GetUserOrdersService(private val orderRepository: OrderRepository) : GetUserOrdersUseCase {

    @Cacheable(cacheNames = ["userOrders"], key = "#userId.value", sync = true)
    override fun execute(userId: UserId): List<OrderSummary> =
        orderRepository.findAllByUserId(userId)
}
```

- **`key = "#userId.value"`** — SpEL resolves to the value object's inner UUID string. Avoids relying on `hashCode`/`equals` of the wrapper.
- **`sync = true`** — thundering herd protection: on a cold cache miss, only one thread loads the value; others wait. Without it, all threads hit the DB simultaneously.

### `@CacheEvict` — explicit invalidation

```kotlin
@Service
@Transactional
class CancelOrderService(...) : CancelOrderUseCase {

    @CacheEvict(cacheNames = ["userOrders"], key = "#command.userId.value")
    override fun execute(command: CancelOrderCommand): Order {
        val order = orderRepository.findById(command.orderId) ?: error("Order not found")
        order.cancel()
        orderRepository.save(order)
        eventPublisher.publishEvent(OrderCancelled(order.id, order.userId, Instant.now()))
        return order
    }
}
```

Eviction fires _after the method returns_ (`beforeInvocation=false` by default), **not on transaction commit** — Spring Cache is not transaction-aware by default, so a rollback _after_ the method returns still leaves the entry evicted. If you need eviction tied to commit, set `isTransactionAware = true` on the `CaffeineCacheManager` bean (it wraps each cache in a `TransactionAwareCacheDecorator`, deferring writes/evictions to after commit). webstack's default is the non-transaction-aware manager: an eviction on a transaction that ultimately rolls back is harmless (the next read simply reloads from the DB).

### `@CachePut` — write-through

`@CachePut` always executes the method and updates the cache. Use it when the mutated value is already computed. `#result` is a SpEL expression for the return value:

```kotlin
@CachePut(cacheNames = ["productDetail"], key = "#result.id.value")
@Transactional
fun updateProductDescription(command: UpdateProductDescriptionCommand): ProductDetail {
    val product = productRepository.findById(command.productId) ?: error("Product not found")
    product.updateDescription(command.newDescription)
    productRepository.save(product)
    return ProductDetail.from(product)
}
```

### Multiple caches with per-region TTL

Use `registerCustomCache` per region; `setCaffeine(...)` is the fallback spec for any unregistered name:

```kotlin
@Bean
fun cacheManager(): CaffeineCacheManager {
    val manager = CaffeineCacheManager()
    fun build(size: Long, ttl: Duration) =
        Caffeine.newBuilder().maximumSize(size)
            .expireAfterWrite(ttl).recordStats().build<Any, Any>()

    manager.registerCustomCache("userOrders",   build(2_000, Duration.ofMinutes(5)))
    manager.registerCustomCache("productDetail", build(500,  Duration.ofHours(1)))
    manager.registerCustomCache("pricingRules",  build(100,  Duration.ofHours(4)))
    // fallback
    manager.setCaffeine(Caffeine.newBuilder().maximumSize(500)
        .expireAfterWrite(Duration.ofMinutes(10)).recordStats())
    return manager
}
```

## Cache key naming

### Convention

Region name pattern: `<module>::<concept>` (e.g., `order::userOrders`, `billing::invoiceDetail`, `shared::countryCodes`). String names have no automatic namespace separation — module prefixing prevents silent region collisions.

Key expression: SpEL resolving to the minimum identifying value. Always use `.value` (the inner UUID/string) rather than the wrapper object — `hashCode` is not stable across JVM restarts.

| Region name | Key expression | Notes |
|---|---|---|
| `order::userOrders` | `#userId.value` | Single ID |
| `catalog::productDetail` | `#productId.value` | Single ID |
| `billing::invoiceDetail` | `#userId.value + ':' + #invoiceId.value` | Composite |
| `shared::pricingRules` | `#tier.name()` | Enum to string |

```kotlin
// BAD  — hashCode() may differ across JVM restarts
@Cacheable(cacheNames = ["order::userOrders"], key = "#userId")

// GOOD
@Cacheable(cacheNames = ["order::userOrders"], key = "#userId.value")
```

## TTL / maxSize tuning

### Starting defaults

| Cache region | `maximumSize` | `expireAfterWrite` | Rationale |
|---|---|---|---|
| User-scoped list queries | 2 000 | 5 min | Invalidated on mutation; short TTL as safety net |
| Entity detail (single record) | 500 | 1 hour | Relatively stable; explicit eviction on write |
| Reference / lookup data | 100 | 4 hours | Changes rarely; low cardinality |
| Computed aggregates (reports) | 50 | 30 min | Expensive to compute; acceptable staleness |

These are starting points. Tune based on measured hit ratio and heap impact.

### Heap fraction guideline

Caffeine stores live Java references; heap cost depends on object graph size. On OCI A1 free-tier (6–8 GB JVM heap): keep total entries ≤ 1–2% of heap. At 2 KB per entry, 5 000 entries ≈ 10 MB — negligible. Large lists (200 items × nested data) can be 50–200 KB per entry; reduce `maximumSize` or cache IDs and resolve detail in a second lookup.

### Hit ratio measurement

Target ≥ 0.80 hit rate per region. Read via Micrometer in production (see [Observability](#observability)) or directly in dev:

```kotlin
val stats = (cacheManager.getCache("userOrders") as CaffeineCache).nativeCache.stats()
// stats.hitRate() < 0.50 → key cardinality too high, TTL too short, or not worth caching
// stats.evictionCount() >> stats.loadCount() → maximumSize too small
```

### `expireAfterWrite` vs `expireAfterAccess`

`expireAfterWrite` — entry expires N duration after it was written, regardless of reads. Use this for all application caches.

`expireAfterAccess` — resets expiry on every read; hot entries never expire, stale data persists indefinitely. Use only for session stores or rate-limit counters where idle eviction is the goal.

## Modulith event-driven invalidation

`@CacheEvict` on the mutation method covers the same-module case. When a cached value in module A depends on data owned by module B, module A subscribes to B's public domain event via `@ApplicationModuleListener` and calls `cacheManager.getCache(...).evict(...)` directly.

See `docs/backend/modulith-events-patterns.md` for full event patterns.

Example: the order module invalidates `userOrders` when `OrderPaid` is published:

```kotlin
// order/OrderCacheInvalidationListener.kt
@Component
class OrderCacheInvalidationListener(private val cacheManager: CacheManager) {
    private val log = LoggerFactory.getLogger(javaClass)

    @ApplicationModuleListener
    fun on(event: OrderPaid) {
        cacheManager.getCache("userOrders")?.evict(event.userId.value)
        log.debug("Evicted userOrders for userId={}", event.userId.value)
    }
}
```

Example: billing module subscribes to `OrderPaid` (a public event in the order module root) and invalidates its own region:

```kotlin
// billing/BillingCacheInvalidationListener.kt
@Component
class BillingCacheInvalidationListener(private val cacheManager: CacheManager) {

    @ApplicationModuleListener
    fun on(event: OrderPaid) {                        // OrderPaid is public in order module root
        cacheManager.getCache("billing::invoiceDetail")?.evict(event.orderId.value)
    }
}
```

`OrderPaid` is importable by billing because it sits at the order module root (permitted in `allowedDependencies`). Cross-module imports of `application/` or `infrastructure/` types remain forbidden by the Modulith verifier. Use `cacheManager.getCache(name).evict(key)` directly — `@CacheEvict` on listener methods is fragile due to AOP proxy wrapping.

## Distributed alternative (Redis)

On a single-VM deployment Caffeine is correct. Switch to Redis when:

- **Multiple JVM instances** (Kubernetes `replicas: 2+`) — `@CacheEvict` in one instance does not evict from others.
- **Persistence across restarts** — Caffeine is always empty after a JVM restart; Redis can persist to disk.
- **Shared data across services** — sidecar or microservice processes need the same cached data.

### Spring Cache abstraction stays the same

Switching requires only a dependency and `CacheManager` swap — no annotation changes in service code:

```kotlin
// build.gradle.kts
implementation("org.springframework.boot:spring-boot-starter-data-redis")
// remove: com.github.ben-manes.caffeine:caffeine
```

```yaml
# application.yml
spring:
  cache:
    type: redis
  data:
    redis:
      host: "${REDIS_HOST:localhost}"
      port: 6379
```

```kotlin
// CacheConfig.kt — replace CaffeineCacheManager with RedisCacheManager
@Bean
fun cacheManager(connectionFactory: RedisConnectionFactory): RedisCacheManager {
    val defaultCfg = RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10))
        .serializeValuesWith(
            RedisSerializationContext.SerializationPair.fromSerializer(
                GenericJacksonJsonRedisSerializer()
            )
        )
    return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaultCfg)
        .withCacheConfiguration("userOrders", defaultCfg.entryTtl(Duration.ofMinutes(5)))
        .build()
}
```

Service annotations are unchanged — only the `CacheManager` bean is replaced.

**Serialization:** Caffeine stores live references; Redis requires serialization. On Spring Boot 4 (Jackson 3) use `GenericJacksonJsonRedisSerializer` (the Jackson 2 `GenericJackson2JsonRedisSerializer` is deprecated) with all-`val` data classes; the Kotlin module (`tools.jackson.module:jackson-module-kotlin`) is auto-registered, and the serializer builds its mapper via `JsonMapper.Builder`.

## Observability

### Micrometer cache metrics

`recordStats()` feeds Micrometer's `CaffeineStatsCounter` automatically when `spring-boot-actuator` is on the classpath. Key meters under `cache.*`:

| Metric | Tags | Meaning |
|---|---|---|
| `cache.gets` | `name`, `result=hit/miss` | Hit and miss counts per region |
| `cache.puts` | `name` | Entries written |
| `cache.evictions` | `name` | Entries evicted by size or TTL |
| `cache.size` | `name` | Current entry count |

Micrometer normalises dots to underscores on Prometheus export (`cache.gets` → `cache_gets_total`). See `docs/backend/observability.md` for the full Grafana setup.

### Hit/miss ratio in PromQL

```promql
# Hit ratio for userOrders cache (last 5 minutes)
sum(rate(cache_gets_total{name="userOrders", result="hit"}[5m]))
  /
sum(rate(cache_gets_total{name="userOrders"}[5m]))
```

Alert when hit ratio drops below 0.7 for a warm region — a sudden drop signals a key-space change or an invalidation storm.

### Grafana dashboard panels

| Panel | PromQL sketch |
|---|---|
| Hit ratio by region | `rate(cache_gets_total{result="hit"}[5m]) / rate(cache_gets_total[5m])` |
| Evictions/sec | `rate(cache_evictions_total[5m])` |
| Cache size | `cache_size` |
| Miss (load) rate | `rate(cache_gets_total{result="miss"}[5m])` |

Link to the broader board in `docs/backend/observability.md`.

## Anti-patterns

**1. Missing `@CacheEvict` after mutation.** The most common defect: a mutation saves to DB without evicting the cache; subsequent reads return stale data until TTL. Always pair `@Cacheable` reads with `@CacheEvict` (or `@CachePut`) on every mutation. Use `@Caching` to group multiple evictions on a single method.

**2. Caching every method.** `@Cacheable` on fast in-memory methods adds heap pressure with no benefit. Cache only at DB or external-call boundaries. If the method runs in under 1 ms without caching, do not cache it.

**3. Key too broad — memory explosion.** `key = "'all'"` on a list query stores the full result under one key. Any record change evicts everything; the next load fetches everything. Prefer per-record keys. For lists that grow deep, use cursor pagination instead of caching (see `docs/backend/performance-and-db.md`).

**4. Shared mutable cache values.** Caffeine stores references, not copies. Mutating a cached `MutableList` mutates the cache. Use immutable types (`data class` with `val` fields, `List` not `MutableList`) for all cached values.

**5. Missing cross-module eviction via events.** Module A caches data derived from module B. Module B publishes an update event — but module A has no `@ApplicationModuleListener` calling `cache.evict(...)`. Result: stale data persists until TTL. Apply the pattern from [Modulith event-driven invalidation](#modulith-event-driven-invalidation).

**6. `expireAfterAccess` for application data.** Hot entries never expire under `expireAfterAccess` — stale data can persist indefinitely. Use `expireAfterWrite` for a predictable maximum staleness bound.

**7. Omitting `recordStats()`.** Without it, Micrometer has no hit/miss data and the cache is a black box. Always add `.recordStats()` to every Caffeine builder — overhead is negligible (a few `AtomicLong` increments per operation).

## Sources

- **Spring Framework Reference — Cache Abstraction:** https://docs.spring.io/spring-framework/reference/integration/cache.html — _authoritative_
- **Spring Boot Reference — Caching:** https://docs.spring.io/spring-boot/reference/io/caching.html — _authoritative_
- **Caffeine GitHub — ben-manes/caffeine:** https://github.com/ben-manes/caffeine — _community: Ben Manes, Caffeine author_
- **Caffeine Wiki — Population, Eviction, Statistics:** https://github.com/ben-manes/caffeine/wiki — _community: Ben Manes, Caffeine author_

Last verified: 2026-06-22 (Spring Boot 4.0.X / Caffeine 3.X / Kotlin 2.X).
