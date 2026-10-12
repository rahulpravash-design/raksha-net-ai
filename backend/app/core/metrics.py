"""Prometheus metrics (Phase 18).

A private registry rather than the library's global one, so tests and the
application never see each other's state.

Cardinality is the thing to get right. HTTP series are labelled with the
**route template** (``/api/v1/incidents/{incident_id}``), never the raw path:
a raw path puts an incident id in a label and creates a new time series per
request. Requests that match no route share one ``unmatched`` label, so a
scanner probing random URLs cannot inflate the series count either.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

#: Seconds. Weighted to the 100 ms - 5 s range where the PRD targets (0.5 s,
#: 1.5 s) and the overload behaviour (queue wait up to 3 s) sit.
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0, 10.0)

HTTP_REQUESTS = Counter(
    "raksha_http_requests_total",
    "HTTP requests handled, by method, route template and status code.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "raksha_http_request_duration_seconds",
    "Time from arrival to response, including any wait for a free slot.",
    ["route"],
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)
HTTP_IN_FLIGHT = Gauge(
    "raksha_http_requests_in_flight",
    "Requests currently being handled by this process.",
    registry=REGISTRY,
)

# Overload signals. These are the ones that would have shown the Phase 17
# deadlock early: a rising queued/shed count means the API is saturated.
REQUESTS_QUEUED = Counter(
    "raksha_requests_queued_total",
    "Requests that had to wait for a free concurrency slot.",
    registry=REGISTRY,
)
REQUESTS_SHED = Counter(
    "raksha_requests_shed_total",
    "Requests refused with 503 because no slot freed in time.",
    registry=REGISTRY,
)
DB_POOL_EXHAUSTED = Counter(
    "raksha_db_pool_exhausted_total",
    "Requests that failed because no database connection became free.",
    registry=REGISTRY,
)

RATE_LIMIT_BACKEND_ERRORS = Counter(
    "raksha_rate_limit_backend_errors_total",
    "Times the shared rate-limit store (Redis) failed and counting fell back to "
    "this process alone. Limits are weaker while this is rising.",
    registry=REGISTRY,
)

# Gauges refreshed at scrape time.
DATABASE_UP = Gauge(
    "raksha_database_up",
    "1 if the last scrape could query the database, else 0.",
    registry=REGISTRY,
)
DB_POOL_SIZE = Gauge(
    "raksha_db_pool_size", "Configured connections kept open.", registry=REGISTRY
)
DB_POOL_CHECKED_OUT = Gauge(
    "raksha_db_pool_checked_out",
    "Connections in use right now.",
    registry=REGISTRY,
)
DB_POOL_OVERFLOW = Gauge(
    "raksha_db_pool_overflow",
    "Connections open beyond the configured pool size.",
    registry=REGISTRY,
)
INCIDENTS_OPEN = Gauge(
    "raksha_incidents_open", "Incidents not yet in a terminal status.", registry=REGISTRY
)
INCIDENTS_UNASSIGNED = Gauge(
    "raksha_incidents_unassigned_open",
    "Open incidents with nobody assigned.",
    registry=REGISTRY,
)

UNMATCHED_ROUTE = "unmatched"
