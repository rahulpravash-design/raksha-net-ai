# RAKSHA NET AI — Performance (Phase 17)

What was measured, what was changed because of it, and what these numbers do
**not** show. Targets are `PRD.md` §8: **NFR-01** report submission p95 < 500 ms
and **NFR-02** control-centre queue load p95 < 1.5 s with 500 open incidents.

## 1. Read this first

Every figure here comes from one machine (4 cores) running the load generator,
the API and PostgreSQL together, with one API process unless stated. That makes
the numbers **useful for comparing a change before and after, and for finding
algorithmic faults**, and **not evidence of production capacity**. The two PRD
targets are met in this environment with a wide margin; that is a statement
about this environment. It is not a statement that NFR-01/02 are met in
production, and no deployment has been load-tested.

## 2. Method

- **Data:** `database/seeds/seed_load.py` — 100,000 incidents (500 open, the rest
  spread over a year), 70,000 dispatches, 200 resources, in a database named
  `*_load`. The seeder refuses any other database name.
- **Load:** `scripts/loadtest.py` — closed loop, N workers per scenario for a
  fixed time, `httpx` + asyncio (no new dependency; `TESTING.md` had suggested
  Locust). 8 workers, 10 s per scenario unless stated.
- **Server:** `uvicorn app.main:app` with `RAKSHA_RATE_LIMIT_ENABLED=false`
  (otherwise the 12-reports-a-minute limit is what is being measured).
- **"Dashboard"** is what the control centre really does on each refresh: the open
  queue (50 per page, by priority) and the stats summary, fetched together.
- **Plans:** `EXPLAIN (ANALYZE, BUFFERS)` on the hot queries.

### Reproduce

```bash
createdb raksha_net_ai_load && psql raksha_net_ai_load -c "CREATE EXTENSION postgis"
POSTGRES_DB=raksha_net_ai_load alembic upgrade head              # from backend/
POSTGRES_DB=raksha_net_ai_load PYTHONPATH=backend:. python database/seeds/seed_load.py
POSTGRES_DB=raksha_net_ai_load RAKSHA_RATE_LIMIT_ENABLED=false uvicorn app.main:app   # from backend/
python scripts/loadtest.py --email load-dispatcher@raksha.example \
    --password raksha-load-test-only --citizen-email load-citizen@raksha.example --assert-nfr
```

## 3. Results against the targets

| Target | Measured p95 | Target |
|---|---|---|
| NFR-02 control-centre queue load (500 open) | 282.5 ms | 1,500 ms |
| NFR-01 report submission | 179.6 ms | 500 ms |

At one worker one dashboard refresh costs about 23 ms and one report about 15 ms
(measured at concurrency 1), so the margin is large and the earlier fear that the
queue needed caching was not borne out.

### Baseline: 8 workers, before any change

The last column is p95 after adding the `incidents.created_at` index (§4.1).

| Scenario | rps | p50 ms | p95 ms | p99 ms | p95 after index |
|---|---|---|---|---|---|
| `dashboard` | 39.9 | 191.7 | 282.5 | 321.4 | 261.1 |
| `queue_search` | 88.6 | 86.1 | 133.5 | 172.4 | 132.8 |
| `queue_history` | 22.9 | 340.5 | 480.9 | 572.6 | 170.3 |
| `bbox` | 114.1 | 67.5 | 92.8 | 151.9 | 128.7 |
| `nearby` | 112.7 | 68.2 | 93.9 | 155.9 | 95.0 |
| `report` | 58.1 | 133.7 | 179.6 | 212.6 | 178.6 |
| `response_time` | 24.2 | 331.3 | 426.6 | 452.9 | 452.8 |
| `resolution_time` | 49.1 | 161.9 | 224.7 | 260.3 | 229.7 |
| `category_breakdown` | 126.2 | 62.1 | 91.7 | 123.3 | 103.1 |
| `resource_utilization` | 72.7 | 107.9 | 156.4 | 186.1 | 162.7 |
| `hotspots` | 23.0 | 346.3 | 449.5 | 508.0 | 464.0 |
| `response_time_30d` | 55.3 | 140.5 | 212.7 | 237.0 | 168.6 |
| `category_breakdown_30d` | 115.8 | 67.2 | 97.6 | 145.6 | 86.1 |
| `hotspots_30d` | 109.0 | 70.9 | 108.3 | 146.9 | 99.3 |

Run-to-run noise is roughly ±20%: an index that a query cannot use moved some
rows by that much. Treat differences smaller than that as no change.

## 4. What the measurements changed

### 4.1 `incidents(created_at)` index — kept (migration 0013)

A deep page of the newest-first history (`sort=-created_at`) scanned all 100k rows
and sorted them on disk (`Sort Method: external merge Disk`). With the index it
reads in order: **p95 481 → 170 ms, throughput 23 → 81 rps**. The report path did
not slow down (180 → 179 ms), so the write cost is not measurable here.

All-time analytics cannot use it (they aggregate the whole table by definition);
**windowed** analytics gain a little (`response_time_30d` 213 → 169 ms).

Checked and **rejected**: an index on `dispatches(created_at)`. It improved the
windowed resource-utilisation query by about 10 ms (p95 81 vs 91 ms) on a query
that takes 10 ms in the database. Not worth carrying.

A `bbox` reading of +39% after the index looked like a regression. Repeating it
three times each way gave 96–102 ms with the index and 87–102 ms without: the
ranges overlap. It was noise.

### 4.2 Overload deadlock — fixed (the important one)

Raising the load did not just slow the API down, it **collapsed** it. At 64
workers (128 dashboard requests in flight):

| | completed | errors | p95 |
|---|---|---|---|
| Before | 31 | 56 | **31,230 ms** |
| After | 361 | 0 | 1,793 ms |

The errors were `QueuePool limit of size 10 overflow 20 reached, connection timed
out, timeout 30.00`, returned to the client as **500 Internal Server Error after a
30-second hang**.

Cause: a request holds a database connection after its auth check while it waits
for a worker thread to run the endpoint body (and again during cleanup). With more
requests in flight than connections, every worker thread blocks waiting for a
connection, and the requests that hold connections cannot get a thread to finish.
Neither side can proceed until the pool times out. **This was a hypothesis until
tested:** with a pool large enough not to run out, the same load completed
normally, which is what confirmed it. (It then hit PostgreSQL's own 100-connection
limit, which is a separate constraint, §5.)

This would have been triggered by a real surge — many dispatchers refreshing at
once, or a flood of reports in a disaster — which is the one time the platform
must not seize up.

Changes:

- `ConcurrencyLimitMiddleware`: at most `RAKSHA_MAX_CONCURRENT_REQUESTS` (24) requests
  are worked on per process, below both the pool (30) and the thread pool (40), so
  an admitted request can always get what it needs. A surge **queues** for up to
  `RAKSHA_MAX_CONCURRENT_WAIT_SECONDS` (3 s), then is refused with **`503
  SERVICE_BUSY` and `Retry-After`**. Health probes are exempt.
- `RAKSHA_DB_POOL_TIMEOUT` 30 s → 5 s, and pool exhaustion is mapped to the same
  `503` rather than a `500`.

After the fix, 0 errors at 8, 32, 64 and 128 workers; latency grows in proportion
to load, which is the correct behaviour (p95 at 128 workers, i.e. 256 requests in
flight: 4.3 s for the dashboard).

### 4.3 Throughput ceiling and worker processes

Throughput is flat at about 38 dashboards/s (about 57 reports/s) from 8 to 128
workers: one Python process is the limit, not the database. Scaling processes
(32 workers, 4 cores shared with the generator):

| API processes | report rps | dashboard rps |
|---|---|---|
| 1 | 56 | 37 |
| 2 | 103 | 48 |
| 3 | 172 | 53 |

Reports scale almost linearly. The dashboard scales less, probably because the
single Python load generator becomes the bottleneck parsing 50-row responses;
this setup cannot separate the two.

### 4.4 Caching — measured, deliberately not added

Redis caching of the queue or map is **not** implemented. Both are far inside their
targets without it, and a cache on the live queue adds an invalidation problem on
the one screen that must never show stale data during an incident. All-time
analytics (the slowest reads, p95 about 450 ms at 100k rows) are the only
plausible candidate, with a short TTL; revisit only if a real deployment measures
it mattering. Prefer calling analytics with `since`/`until`: for the heavy ones a 30-day
window is much cheaper than all-time (response time about 2×, hotspots about 4×;
the category breakdown, already cheap, did not change).

### 4.5 The first measurements were wrong

The first seeder gave every historical incident the same location, score, status
and date: in PostgreSQL an uncorrelated `LATERAL` subquery is evaluated **once**,
so `random()` inside it never varied per row. The same bug put all 200 resources
in one place and all dispatches on one resource. The first set of results (which
looked fine) was discarded, the seeder fixed and verified (362 distinct dates,
84,610 distinct latitudes, all 200 resources used), and everything re-measured.
The lesson, for any bulk generator: check that the data actually varies before
believing a number computed from it.

## 5. Capacity guidance for deployment

- **Connections:** each API process may open `RAKSHA_DB_POOL_SIZE +
  RAKSHA_DB_MAX_OVERFLOW` (30) connections. `processes × 30` must stay under
  PostgreSQL's `max_connections` (default 100) with headroom for migrations and
  admin sessions: **three processes per default-configured database.** More needs
  a larger `max_connections` or a pooler such as PgBouncer.
- **Cap vs pool:** keep `RAKSHA_MAX_CONCURRENT_REQUESTS` below the pool total and
  below the worker-thread count (40). Raising either without the other brings the
  deadlock back.
- **Rate limiting** falls back to per-process counters when Redis is not
  reachable, so with several processes each enforces its own limit.
- Clients and any proxy should honour `Retry-After` on `503`.

## 6. Not shown, and open

- **Production capacity.** Nothing here. Run `scripts/loadtest.py` against a
  production-shaped deployment with the load generator on a separate machine.
- **Sporadic `ReadError` with several API processes.** One to two of ~370 requests
  in 2-worker runs failed with a dropped connection; the server logged nothing and
  a single process never did it. Probably a keep-alive reuse race, unconfirmed.
  A proxy that retries idempotent requests would absorb it; it should be
  understood before relying on multiple processes.
- **Write path under contention** beyond report submission (dispatch, status
  changes) was not load-tested.
- **Analytics at larger scale** grows linearly with table size (full scans). At
  millions of incidents the answer is windowing, summary tables or partitioning,
  not an index.
- **Partitioning and read replicas** (Phase 17's other items) are deployment
  decisions; nothing was built or measured.
