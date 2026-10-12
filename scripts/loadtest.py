#!/usr/bin/env python3
"""Closed-loop load test for the RAKSHA NET AI API (Phase 17).

    scripts/loadtest.py --base-url http://localhost:8000 \
        --email load-dispatcher@raksha.example --password raksha-load-test-only \
        --citizen-email load-citizen@raksha.example [--assert-nfr]

Runs against a server you have already started, with a database seeded by
``database/seeds/seed_load.py``. The API must be started with
``RAKSHA_RATE_LIMIT_ENABLED=false``, or the 12-reports-a-minute limit is what
you will be measuring.

What this is and is not. Each scenario runs N workers in a closed loop for a
fixed time, so it measures latency under that much concurrency. It does not
model a real arrival pattern, and when the client, API and database share one
machine (as in a development sandbox) the figures are *relative* evidence for
comparing a change before and after. They are not a statement about production
capacity, and meeting a target here does not mean it is met there.

Only ``httpx`` is needed, which the backend already uses for its tests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

#: PRD section 8. Only these two have a stated target.
NFR_P95_MS = {
    "report": 500.0,  # NFR-01: report submission p95
    "dashboard": 1500.0,  # NFR-02: control-centre queue load p95, 500 open incidents
}

LAT = (12.90, 13.20)
LON = (80.15, 80.35)


@dataclass
class Sample:
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    first_error: str | None = None
    #: HTTP status -> count, for requests the server answered with an error.
    statuses: dict[int, int] = field(default_factory=dict)


@dataclass
class Context:
    client: httpx.AsyncClient
    citizen: httpx.AsyncClient | None


Scenario = Callable[[Context], Awaitable[None]]


def _ok(response: httpx.Response) -> None:
    response.raise_for_status()


def _viewport() -> dict[str, float]:
    """A random map viewport roughly the size a dispatcher would have open."""
    lat = random.uniform(LAT[0], LAT[1] - 0.06)
    lon = random.uniform(LON[0], LON[1] - 0.06)
    return {
        "min_lat": lat,
        "min_lon": lon,
        "max_lat": lat + 0.06,
        "max_lon": lon + 0.06,
    }


async def dashboard(ctx: Context) -> None:
    """One control-centre refresh: the open queue and the stats, together."""
    queue, stats = await asyncio.gather(
        ctx.client.get(
            "/api/v1/incidents",
            params={"open_only": "true", "sort": "priority", "page_size": 50},
        ),
        ctx.client.get("/api/v1/incidents/stats/summary"),
    )
    _ok(queue)
    _ok(stats)


async def queue_search(ctx: Context) -> None:
    _ok(
        await ctx.client.get(
            "/api/v1/incidents",
            params={"open_only": "true", "q": "report number 1", "page_size": 50},
        )
    )


async def queue_history(ctx: Context) -> None:
    """A deep page of the *whole* table, as a back-office review would."""
    _ok(
        await ctx.client.get(
            "/api/v1/incidents",
            params={
                "sort": "-created_at",
                "page": random.randint(1, 3000),
                "page_size": 25,
            },
        )
    )


async def bbox(ctx: Context) -> None:
    _ok(
        await ctx.client.get(
            "/api/v1/geo/incidents/bbox", params={**_viewport(), "open_only": "true"}
        )
    )


async def nearby(ctx: Context) -> None:
    _ok(
        await ctx.client.get(
            "/api/v1/geo/incidents/nearby",
            params={
                "latitude": random.uniform(*LAT),
                "longitude": random.uniform(*LON),
                "radius_km": 5,
            },
        )
    )


async def report(ctx: Context) -> None:
    if ctx.citizen is None:
        raise RuntimeError("the report scenario needs --citizen-email")
    _ok(
        await ctx.citizen.post(
            "/api/v1/incidents",
            json={
                "category": random.choice(
                    ["FLOOD", "FIRE", "MEDICAL", "ROAD_ACCIDENT"]
                ),
                "description": "Load test: people are trapped and water is rising fast.",
                "latitude": round(random.uniform(*LAT), 6),
                "longitude": round(random.uniform(*LON), 6),
                "people_affected": random.randint(1, 8),
                "people_trapped": random.random() < 0.3,
                "medical_required": random.random() < 0.3,
                "immediate_danger": random.random() < 0.3,
            },
        )
    )


def _get(path: str, **params: object) -> Scenario:
    async def run(ctx: Context) -> None:
        _ok(await ctx.client.get(path, params=params))

    return run


def _windowed(path: str, days: int = 30) -> Scenario:
    """An analytics call restricted to the last ``days`` days, as a dashboard would."""

    async def run(ctx: Context) -> None:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        _ok(await ctx.client.get(path, params={"since": since}))

    return run


SCENARIOS: dict[str, Scenario] = {
    "dashboard": dashboard,
    "queue_search": queue_search,
    "queue_history": queue_history,
    "bbox": bbox,
    "nearby": nearby,
    "report": report,
    "response_time": _get("/api/v1/analytics/response-time"),
    "resolution_time": _get("/api/v1/analytics/resolution-time"),
    "category_breakdown": _get("/api/v1/analytics/category-breakdown"),
    "resource_utilization": _get("/api/v1/analytics/resource-utilization"),
    "hotspots": _get("/api/v1/analytics/hotspots"),
    "response_time_30d": _windowed("/api/v1/analytics/response-time"),
    "category_breakdown_30d": _windowed("/api/v1/analytics/category-breakdown"),
    "hotspots_30d": _windowed("/api/v1/analytics/hotspots"),
    "resource_utilization_30d": _windowed("/api/v1/analytics/resource-utilization"),
}


async def _login(base_url: str, email: str, password: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(
        base_url=base_url,
        timeout=60.0,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=200),
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    if response.status_code != 200:
        raise SystemExit(
            f"Login failed for {email}: {response.status_code} {response.text}"
        )
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


async def _worker(
    name: str, scenario: Scenario, ctx: Context, deadline: float, sample: Sample
) -> None:
    while time.perf_counter() < deadline:
        started = time.perf_counter()
        try:
            await scenario(ctx)
        except Exception as exc:  # noqa: BLE001 - a failed request is data, not a crash
            sample.errors += 1
            if isinstance(exc, httpx.HTTPStatusError):
                code = exc.response.status_code
                sample.statuses[code] = sample.statuses.get(code, 0) + 1
            sample.first_error = sample.first_error or f"{type(exc).__name__}: {exc}"
            continue
        sample.latencies_ms.append((time.perf_counter() - started) * 1000.0)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return float("nan")
    index = min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def summarise(name: str, sample: Sample, seconds: float) -> dict[str, object]:
    values = sorted(sample.latencies_ms)
    return {
        "scenario": name,
        "requests": len(values),
        "errors": sample.errors,
        "rps": round(len(values) / seconds, 1),
        "p50_ms": round(_percentile(values, 0.50), 1),
        "p95_ms": round(_percentile(values, 0.95), 1),
        "p99_ms": round(_percentile(values, 0.99), 1),
        "max_ms": round(values[-1], 1) if values else None,
        "error_statuses": dict(sample.statuses),
        "first_error": sample.first_error,
    }


async def main_async(args: argparse.Namespace) -> int:
    dispatcher = await _login(args.base_url, args.email, args.password)
    citizen = (
        await _login(args.base_url, args.citizen_email, args.password)
        if args.citizen_email
        else None
    )
    ctx = Context(client=dispatcher, citizen=citizen)

    names = args.scenarios or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")

    results: list[dict[str, object]] = []
    for name in names:
        if name == "report" and citizen is None:
            print("skipping 'report': pass --citizen-email", file=sys.stderr)
            continue
        sample = Sample()
        # Warm-up: one pass per worker, discarded, so connection setup and
        # cold caches do not pollute the first scenario.
        await asyncio.gather(
            *[SCENARIOS[name](ctx) for _ in range(min(args.concurrency, 4))],
            return_exceptions=True,
        )
        started = time.perf_counter()
        deadline = started + args.duration
        await asyncio.gather(
            *[
                _worker(name, SCENARIOS[name], ctx, deadline, sample)
                for _ in range(args.concurrency)
            ]
        )
        results.append(summarise(name, sample, time.perf_counter() - started))
        row = results[-1]
        print(
            f"{name:<22} n={row['requests']:<6} err={row['errors']:<4} "
            f"rps={row['rps']:<7} p50={row['p50_ms']:<8} p95={row['p95_ms']:<8} "
            f"p99={row['p99_ms']:<8} max={row['max_ms']}"
            + (
                f"  error_statuses={row['error_statuses']}"
                if row["error_statuses"]
                else ""
            )
        )

    await dispatcher.aclose()
    if citizen:
        await citizen.aclose()

    if args.json:
        payload = {
            "concurrency": args.concurrency,
            "duration_s": args.duration,
            "results": results,
        }
        await asyncio.to_thread(
            Path(args.json).write_text, json.dumps(payload, indent=2), encoding="utf-8"
        )

    failed = False
    for row in results:
        target = NFR_P95_MS.get(str(row["scenario"]))
        if target is None:
            continue
        verdict = "MET" if float(row["p95_ms"]) <= target and not row["errors"] else "MISSED"  # type: ignore[arg-type]
        print(
            f"NFR {row['scenario']}: p95 {row['p95_ms']} ms vs target {target:.0f} ms -> {verdict}"
        )
        failed = failed or verdict == "MISSED"
    print(
        "\nReminder: client, API and database share this machine. These are relative "
        "figures for comparing changes, not production capacity."
    )
    return 1 if (args.assert_nfr and failed) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True, help="a DISPATCHER or ADMIN account")
    parser.add_argument("--password", required=True)
    parser.add_argument("--citizen-email", help="enables the 'report' scenario")
    parser.add_argument(
        "--duration", type=float, default=15.0, help="seconds per scenario"
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--scenarios", nargs="*", help=f"any of: {', '.join(SCENARIOS)}"
    )
    parser.add_argument("--json", help="write results to this file")
    parser.add_argument(
        "--assert-nfr", action="store_true", help="exit 1 if a PRD target is missed"
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
