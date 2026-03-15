# Concurrency patterns

This document explains each race condition the codebase addresses, the technique chosen, the tradeoffs made, and the alternatives that were considered. The goal is to make the reasoning explicit, not just the outcome.

---

## 1. Key generation — TOCTOU

**The bug without a fix**

A naïve implementation would check whether a key exists before inserting:

```
Thread A: SELECT key='ABC' → not found
Thread B: SELECT key='ABC' → not found      ← slips in before A inserts
Thread A: INSERT key='ABC' → success
Thread B: INSERT key='ABC' → duplicate key / silent overwrite
```

This is a TOCTOU race (Time-Of-Check Time-Of-Use): the check and the action are two separate, non-atomic steps. Another thread can change the world between them.

**Current approach** (`keygen.py`, `url_service.py:create`)

Skip the check entirely. Generate a random key and attempt the insert directly. The database's `UNIQUE` constraint is the authoritative arbiter — it enforces uniqueness atomically at the storage level. On `IntegrityError` (collision), roll back and retry with exponential backoff.

```python
for attempt in range(max_retries):
    try:
        key = keygen.generate_random_key(size=6)
        self.db.add(models.URL(target_url=target_url, key=key, ...))
        await self.db.commit()
        return db_url
    except IntegrityError:
        await self.db.rollback()
        await asyncio.sleep(0.01 * (2 ** attempt))  # 10ms, 20ms, 40ms...
```

The key space is `36^6 ≈ 2.2 billion`. At 1 million stored URLs, the birthday-paradox collision probability is ~0.02%, so retries are rare.

**Alternatives considered**

| Approach | How | Tradeoff |
|---|---|---|
| Current (optimistic insert) | Try insert, catch collision | Correct and fast; rare retries on a full key space |
| Pre-generated pool | Redis `SPOP` from a set of pre-generated keys | Zero retry latency, no DB roundtrip for uniqueness; requires a background refill worker |
| Counter + base-62 encode | Encode the auto-increment `id` as a short string | Guaranteed unique with no retries; keys are sequential and guessable (enumeration attack exposes all active URLs) |

---

## 2. Click counter — lost update

**The bug without a fix**

```
Thread A: SELECT clicks = 5
Thread B: SELECT clicks = 5    ← reads the same value
Thread A: UPDATE clicks = 6    (5 + 1)
Thread B: UPDATE clicks = 6    (5 + 1, not 7)
→ one click is lost
```

With `n` concurrent requests, up to `n-1` increments are lost. This is the classic read-modify-write problem.

**Previous approach — atomic SQL** *(legacy, replaced by Redis buffering)*

The first fix pushed the increment into the database engine itself:

```python
.values(clicks=models.URL.clicks + 1)
# emits: UPDATE urls SET clicks = clicks + 1 WHERE id = ?
```

The entire read-add-write happens atomically inside the database. No Python code touches the intermediate value. The DB holds a row-level lock only for the duration of that single statement. This is correct and still lives in `url_service.py:increment_clicks`, but it is no longer called on the redirect path — it was superseded by the Redis approach below.

**Current approach — Redis buffered counter** (`infrastructure/click_buffer.py`)

The SQL increment is no longer on the redirect hot path. Instead:

```
Redirect request:   ZINCRBY clicks:leaderboard 1 {url_id}   # ~ns, in memory
Background task:    every 30s → UPDATE urls SET clicks = clicks + N (batch)
```

`ZINCRBY` is atomic by design — Redis is single-threaded for command execution, so the increment is never lost regardless of concurrency. The flush uses an atomic `RENAME` to avoid losing clicks that arrive during the flush window:

```
RENAME clicks:leaderboard → clicks:leaderboard:flushing   (atomic, O(1))
```

New clicks land on the fresh `clicks:leaderboard` key while the old one is being drained into SQL. No click is ever caught between the two.

**Tradeoffs of buffering**

- **Durability**: up to 30 seconds of clicks live only in Redis. An unclean crash loses them unless an RDB snapshot covers the window (configured in `docker-compose.yml` with `--save 30 1`).
- **Accuracy**: the admin endpoint adds `ZSCORE clicks:leaderboard url_id` (the buffered delta) to `db_url.clicks` (the flushed total), so it always shows the real-time count.
- **Throughput**: Redis handles millions of `ZINCRBY`s per second vs. thousands of SQL `UPDATE`s. The redirect path becomes effectively read-only from the database's perspective.

---

## 3. SELECT FOR UPDATE — pessimistic row lock *(legacy, removed)*

> **Status**: this approach was explored and removed. It is documented here because the tradeoffs are instructive, and it was a real intermediate step before the Redis buffering approach.

**The race condition it was solving**

Before the Redis buffering was added, the redirect path did two SQL operations:

```
Thread A: SELECT url WHERE key='ABC'   → found, is_active=True
Thread B: DELETE url WHERE key='ABC'   → sets is_active=False, commits
Thread A: UPDATE clicks = clicks + 1   → writes to a logically dead row
```

This is a phantom write: incrementing click counts on a URL that no longer exists. Not catastrophic, but inconsistent.

`SELECT FOR UPDATE` (`url_service.py:get_by_key_with_lock`) acquires an exclusive row lock at read time. Any concurrent transaction that tries to modify or delete the same row blocks until Thread A's transaction commits.

Lock lifespan: `SELECT FOR UPDATE` → `UPDATE clicks` → `COMMIT`

**Why it was the wrong tradeoff at scale**

The lock spans two database round-trips. During that 2–5ms window, every other request for the same URL queues. For a viral link receiving thousands of concurrent hits, throughput is bounded by `1 / lock_hold_time` — a serialisation queue, not a throughput ceiling.

SQLite makes this worse: it uses file-level locking, not row-level. Every write locks the entire database, serialising concurrent reads to *different* URLs.

**Why the lock is no longer needed**

The redirect path now does:

```python
db_url = await service.get_by_key(url_key)          # plain SELECT, no lock
await request.app.state.click_buffer.increment(...)  # Redis ZINCRBY
return RedirectResponse(db_url.target_url)
```

There is no SQL write following the read. The worst case is: URL is deactivated between the `SELECT` and the `ZINCRBY`. The Redis entry accumulates a click for a deactivated `url_id`. On the next flush, `UPDATE urls SET clicks = clicks + N WHERE id = ?` either updates an inactive row harmlessly or affects 0 rows if it was hard-deleted. No corruption either way.

**Alternatives to pessimistic locking**

| Strategy | Mechanism | Best when |
|---|---|---|
| Pessimistic (`SELECT FOR UPDATE`) | Exclusive lock at read time; others block | Conflicts are frequent; correctness is critical |
| Optimistic (version counter) | `UPDATE ... WHERE version = ?`; retry on 0 rows affected | Conflicts are rare; you want no lock held between reads and writes |
| Remove the lock (current) | Accept phantom write on deactivated rows | The write after the read is idempotent or harmless — which is true here |
| Redis cache + async write | Reads never touch SQL at all | Read-heavy workloads; can tolerate eventual consistency on deletes |

---

## 4. SQL lock queue vs. message queue

A common misconception: if the database queues operations behind a lock, why add a message queue?

The SQL lock queue is not a queue in any useful sense — it is a **blocking wait**. When 1,000 requests hit a locked row, 1,000 HTTP connections stay open, 1,000 DB connections are held, and every one of them waits for the lock to release. If any client has a timeout shorter than the lock hold time, it errors out before the lock ever releases.

A message queue (Kafka, RabbitMQ, SQS) is genuinely async: the producer writes a message and **immediately returns**. Work happens later, at whatever rate the consumer can sustain. The HTTP response completes in microseconds regardless of DB speed.

Redis `ZINCRBY` is a simpler version of the same principle: it is the buffer. The response is immediate; the SQL write happens in batch, asynchronously.

| | SQL lock "queue" | Redis buffer (this codebase) | Message queue |
|---|---|---|---|
| HTTP response time | Blocked until DB write | Immediate | Immediate |
| DB writes per N clicks | N | 1 per flush interval | 1 per batch |
| Burst handling | Connections pile up | Redis absorbs | Queue absorbs |
| Persistence | Durable | Configurable (RDB/AOF) | Durable |
| Cross-service fan-out | No | No | Yes |

Message queues add value over Redis when multiple independent services need to react to the same event (analytics, billing, recommendations). Redis buffering is sufficient when only one system needs the count.

---

## 5. Index on `clicks` — write amplification

The `urls` table has indexes on `key` (unique lookup on redirect), `secret_key` (admin lookup), and `target_url`. Adding a B-tree index on `clicks` would support `ORDER BY clicks DESC` for top-N queries.

**The cost**

A B-tree index must stay sorted. Every `UPDATE clicks = clicks + N` requires:

1. Locate and delete the old entry (`clicks=5, ptr=row42`) from the B-tree
2. Insert a new entry (`clicks=6, ptr=row42`) at its new sorted position

This doubles the write I/O for every click update. The `key` index avoids this because key values never change after insert. `clicks` changes on every redirect — it is exactly the anti-pattern B-tree indexes are ill-suited for.

**Comparison**

| | `key` index | `clicks` index |
|---|---|---|
| Write frequency | Once at insert | Every redirect |
| Value stability | Never changes | Changes constantly |
| Selectivity | Perfect (unique) | Low (many rows share similar counts) |
| Read benefit | Every redirect lookup | Analytics queries only |

**Better alternatives for top-N**

- **Redis sorted set (current)**: `ZINCRBY` maintains ordering as a side effect. `ZREVRANGE leaderboard 0 9` returns top-10 in O(log N + K). No SQL write amplification.
- **Periodic aggregation**: Run `SELECT key, clicks ORDER BY clicks DESC LIMIT 100` on a read replica every minute and cache the result. One analytical query serves thousands of reads.
- **Partial index**: Index only `WHERE clicks > threshold`. Smaller index, but still causes write amplification for popular URLs.

A `clicks` index is worth the cost only if analytics queries are frequent and the write overhead is acceptable. At high redirect volume, the Redis sorted set is strictly better.

---

## 6. Redis persistence and data loss bounds

Redis is in-memory by default. Three persistence strategies apply to the buffered click counts:

| Mode | Mechanism | Max data loss |
|---|---|---|
| No persistence | Pure memory | All buffered clicks on restart |
| RDB snapshot (`--save 30 1`) | Dump to disk if ≥1 key changed in 30s | ~30s of clicks (configured in `docker-compose.yml`) |
| AOF (`appendfsync everysec`) | Append every write to a log file | ~1s of clicks |

The RDB interval is intentionally aligned with `CLICK_FLUSH_INTERVAL` (30s). On a clean shutdown, the lifespan finaliser runs a forced flush before closing connections, so the data loss window is zero for normal restarts. The RDB snapshot protects against unclean crashes (OOM kill, power loss).

For click counts used in analytics, ~30s of potential loss is acceptable. For financially significant counts (pay-per-click billing), AOF with `fsync=always` or a message queue with at-least-once delivery guarantees would be required.

---

## 7. Rate limiter — INCR atomicity and TTL enforcement

### Bug 1: Non-atomic check-then-increment

**The bug in the original GET → check → SETEX/INCR pattern**

```
Request A: GET key → 9    (9 < limit=10, passes check)
                           ← race window: B reads before A increments
Request B: GET key → 9    (9 < limit=10, passes check)
Request A: INCR key → 10  ✓ allowed
Request B: INCR key → 11  ✓ also allowed — limit silently exceeded
```

`GET → check → INCR` involves two separate Redis round-trips. Both requests read the same count (9), both pass the `>= limit` check, and both increment — silently exceeding the limit by 1.

**Fix: INCR-first pattern** (`infrastructure/rate_limiter.py`)

```python
count = await redis.incr(key)   # atomic: returned count is the gate
if count == 1:
    await redis.expire(key, window_seconds)
if count > max_requests:
    raise HTTPException(429)
```

`INCR` is atomic. The returned count is the count *after* the increment, and it is the check value. No two concurrent requests can observe the same post-increment count.

### Bug 2: Counter with no TTL

**The bug**

With the old pattern, `SETEX` set the TTL only when the key was *new* (when `GET` returned `None`). For existing keys, only `INCR` was called — no TTL update. If the key happened to expire between the `GET` (which returned a value) and the subsequent `INCR`, the `INCR` created a new key with **no TTL**. That counter would then persist indefinitely, permanently rate-limiting the user.

**Fix**

`INCR` returns `1` when it creates a new key (the key did not exist before). The check `if count == 1: await redis.expire(key, window)` sets the TTL immediately on every new key.

The remaining edge case — crash between `INCR` and `EXPIRE` — would leave the key without a TTL. Eliminating this entirely would require a Lua script or `MULTI/EXEC`. The current implementation accepts this as a one-in-a-million edge case.

---

## 8. Click flush — durability and crash recovery

### Bug 1: `finally: delete` discards clicks on DB failure

**The bug in the original flush**

```python
try:
    entries = await self.redis.zrange(_FLUSH_KEY, ...)
    for url_id, delta in entries:
        await db.execute(...)
    await db.commit()          # raises on transient DB error
finally:
    await self.redis.delete(_FLUSH_KEY)   # runs anyway — clicks permanently lost
```

If `db.commit()` raised (transient error, connection drop, disk full), the `finally` block still deleted `_FLUSH_KEY`. The click data in that batch was gone with no log entry and no recovery path.

**Fix**

Delete `_FLUSH_KEY` only after a confirmed successful commit:

```python
await db.commit()
await self.redis.delete(key)  # only reached on success
```

If `commit()` raises, the key persists. The next `flush_to_db` call recovers it via Bug 2's fix.

### Bug 2: Stranded `_FLUSH_KEY` after an unclean crash

**The bug**

`RENAME _LEADERBOARD_KEY → _FLUSH_KEY` is atomic, but the subsequent `db.commit()` is not. If the process was killed between these two steps, `_FLUSH_KEY` was left stranded.

On the next `flush_to_db` call, `RENAME` would silently overwrite the stale `_FLUSH_KEY` with fresh data — discarding the stranded clicks permanently.

**Fix: stale-key recovery** (`infrastructure/click_buffer.py:flush_to_db`)

```python
async def flush_to_db(self, db):
    if await self.redis.exists(_FLUSH_KEY):
        # Stale key from previous crashed flush — recover it before starting
        # a new window. Without this, RENAME would overwrite it silently.
        await self._drain_to_db(_FLUSH_KEY, db)

    await self.redis.rename(_LEADERBOARD_KEY, _FLUSH_KEY)
    await self._drain_to_db(_FLUSH_KEY, db)
```

By draining the stale key before the `RENAME`, no click data is overwritten. Combined with Bug 1's fix, `_FLUSH_KEY` only persists when `db.commit()` failed, so the recovery path is only triggered on actual failures.
