#!/usr/bin/env python3
"""Seed a *load-test* database with a large synthetic dataset.

    python database/seeds/seed_load.py [--incidents 100000] [--open 500]

Sized for ``docs/TESTING.md`` section 8: 100k incidents, of which 500 are open
(the population NFR-02 is stated against). The rest are historical, spread over
a year, most with a dispatch, so the analytics queries see realistic volume.

Rows are inserted in bulk SQL rather than through the services, for speed. That
also means the priority factors, audit rows and status history the real write
path produces are absent: this dataset is for measuring *read* queries, not for
exercising business rules.

It refuses to run unless the database name ends in ``_load``, so it cannot be
pointed at a development or production database by accident.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_engine
from app.models import User, UserRole
from sqlalchemy import text
from sqlalchemy.orm import Session

LOAD_PASSWORD = "raksha-load-test-only"
USERS = [
    ("load-citizen@raksha.example", "Load Citizen", UserRole.CITIZEN),
    ("load-dispatcher@raksha.example", "Load Dispatcher", UserRole.DISPATCHER),
    ("load-admin@raksha.example", "Load Admin", UserRole.ADMIN),
]

# One statement per population, with static SQL (no string building).
_INSERT_OPEN = text("""
INSERT INTO incidents (
    id, reference_code, reported_by_id, category, description,
    latitude, longitude, geom, status, severity, priority_score, priority_band,
    priority_overridden, people_affected, people_trapped, medical_required,
    immediate_danger, created_at, updated_at
)
SELECT gen_random_uuid(),
       'RKS-' || upper(substr(md5('open' || g::text), 1, 12)),
       :citizen,
       (ARRAY['FLOOD','FIRE','ROAD_ACCIDENT','MEDICAL','BUILDING_COLLAPSE',
              'MISSING_PERSON','LANDSLIDE','GAS_LEAK','OTHER'])[1 + floor(random()*9)::int]::incident_category,
       'Synthetic load-test report number ' || g::text,
       p.lat, p.lon,
       ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
       (ARRAY['REPORTED','RECEIVED','UNDER_REVIEW','PRIORITIZED','ASSIGNED',
              'RESPONDER_EN_ROUTE','ON_SCENE'])[1 + floor(random()*7)::int]::incident_status,
       (ARRAY['CRITICAL','HIGH','MODERATE','LOW'])[1 + floor(random()*4)::int]::severity_level,
       p.score,
       (CASE WHEN p.score >= 75 THEN 'CRITICAL' WHEN p.score >= 50 THEN 'HIGH'
             WHEN p.score >= 25 THEN 'MEDIUM' ELSE 'LOW' END)::priority_band,
       false, 1 + floor(random()*10)::int, random() < 0.2, random() < 0.3, random() < 0.3,
       now() - (random() * interval '3 days'),
       now()
FROM generate_series(1, :n) AS g
CROSS JOIN LATERAL (
    SELECT round((12.90 + random()*0.30 + g*0)::numeric, 6) AS lat,
           round((80.15 + random()*0.20 + g*0)::numeric, 6) AS lon,
           floor(random()*101 + g*0)::int AS score
) AS p
""")

_INSERT_CLOSED = text("""
INSERT INTO incidents (
    id, reference_code, reported_by_id, category, description,
    latitude, longitude, geom, status, severity, priority_score, priority_band,
    priority_overridden, people_affected, people_trapped, medical_required,
    immediate_danger, resolved_at, closed_at, created_at, updated_at
)
SELECT gen_random_uuid(),
       'RKS-' || upper(substr(md5('closed' || g::text), 1, 12)),
       :citizen,
       (ARRAY['FLOOD','FIRE','ROAD_ACCIDENT','MEDICAL','BUILDING_COLLAPSE',
              'MISSING_PERSON','LANDSLIDE','GAS_LEAK','OTHER'])[1 + floor(random()*9)::int]::incident_category,
       'Synthetic historical report number ' || g::text,
       p.lat, p.lon,
       ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
       p.status::incident_status,
       (ARRAY['CRITICAL','HIGH','MODERATE','LOW'])[1 + floor(random()*4)::int]::severity_level,
       p.score,
       (CASE WHEN p.score >= 75 THEN 'CRITICAL' WHEN p.score >= 50 THEN 'HIGH'
             WHEN p.score >= 25 THEN 'MEDIUM' ELSE 'LOW' END)::priority_band,
       false, 1 + floor(random()*10)::int, random() < 0.2, random() < 0.3, random() < 0.3,
       CASE WHEN p.status IN ('RESOLVED','CLOSED') THEN p.created + (random()*interval '10 hours') END,
       CASE WHEN p.status = 'CLOSED' THEN p.created + interval '12 hours' END,
       p.created,
       p.created
FROM generate_series(1, :n) AS g
CROSS JOIN LATERAL (
    SELECT round((12.90 + random()*0.30 + g*0)::numeric, 6) AS lat,
           round((80.15 + random()*0.20 + g*0)::numeric, 6) AS lon,
           floor(random()*101 + g*0)::int AS score,
           (ARRAY['RESOLVED','CLOSED','CLOSED','CANCELLED','DUPLICATE','REJECTED'])[1 + floor(random()*6 + g*0)::int] AS status,
           now() - interval '4 days' - (random() * interval '361 days') - (g * interval '0 seconds') AS created
) AS p
""")

_INSERT_RESOURCES = text("""
INSERT INTO resources (
    id, call_sign, name, resource_type, status, latitude, longitude, geom,
    capabilities, is_active, created_at, updated_at
)
SELECT gen_random_uuid(), 'LOAD-' || g::text, 'Load unit ' || g::text,
       (ARRAY['AMBULANCE','FIRE_ENGINE','RESCUE_TEAM','POLICE_UNIT','RESCUE_BOAT'])[1 + floor(random()*5)::int]::resource_type,
       'AVAILABLE'::resource_status,
       p.lat, p.lon,
       ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
       '[]'::jsonb, true, now(), now()
FROM generate_series(1, :n) AS g
CROSS JOIN LATERAL (
    SELECT round((12.90 + random()*0.30 + g*0)::numeric, 6) AS lat,
           round((80.15 + random()*0.20 + g*0)::numeric, 6) AS lon
) AS p
""")

# A first dispatch for roughly 70% of incidents, minutes after the report.
_INSERT_DISPATCHES = text("""
INSERT INTO dispatches (
    id, incident_id, resource_id, approved_by_id, status, distance_km,
    estimated_minutes, created_at, updated_at
)
SELECT gen_random_uuid(), i.id, r.id, :approver,
       (CASE WHEN i.status IN ('RESOLVED','CLOSED') THEN 'COMPLETED'
             WHEN i.status IN ('CANCELLED','DUPLICATE','REJECTED') THEN 'CANCELLED'
             ELSE 'DISPATCHED' END)::dispatch_status,
       round((random()*20)::numeric, 2), 1 + floor(random()*40)::int,
       i.created_at + (random() * interval '30 minutes'),
       i.created_at + (random() * interval '30 minutes')
FROM incidents i
JOIN (
    SELECT id, row_number() OVER (ORDER BY id) AS n, count(*) OVER () AS total
    FROM resources
) AS r ON r.n = 1 + (abs(hashtext(i.id::text)) % r.total)
WHERE random() < 0.7
""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--incidents", type=int, default=100_000)
    parser.add_argument("--open", type=int, default=500, dest="open_count")
    parser.add_argument("--resources", type=int, default=200)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.postgres_db.endswith("_load"):
        print(
            f"Refusing to run: database '{settings.postgres_db}' does not end in "
            "'_load'. This seeder inserts a lot of synthetic data.",
            file=sys.stderr,
        )
        return 2
    if args.open_count > args.incidents:
        print("--open cannot exceed --incidents", file=sys.stderr)
        return 2

    engine = get_engine()
    with Session(engine) as session:
        session.execute(
            text(
                "TRUNCATE dispatches, resources, incident_status_history, "
                "incident_media, incident_analyses, notification_deliveries, "
                "notifications, inbound_patient_notices, incidents, audit_logs, "
                "refresh_tokens, users CASCADE"
            )
        )
        users = {}
        for email, name, role in USERS:
            user = User(
                email=email,
                full_name=name,
                hashed_password=hash_password(LOAD_PASSWORD),
                role=role,
            )
            session.add(user)
            users[role] = user
        session.flush()
        citizen = users[UserRole.CITIZEN].id
        approver = users[UserRole.DISPATCHER].id

        session.execute(_INSERT_RESOURCES, {"n": args.resources})
        session.execute(_INSERT_OPEN, {"n": args.open_count, "citizen": citizen})
        session.execute(
            _INSERT_CLOSED,
            {"n": args.incidents - args.open_count, "citizen": citizen},
        )
        session.execute(_INSERT_DISPATCHES, {"approver": approver})
        session.commit()

    # Fresh planner statistics, as a real deployment's autovacuum would give.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("ANALYZE"))

    with Session(engine) as session:
        counts = {
            "incidents": session.scalar(text("SELECT count(*) FROM incidents")),
            "open": session.scalar(
                text(
                    "SELECT count(*) FROM incidents WHERE status NOT IN "
                    "('RESOLVED','CLOSED','CANCELLED','DUPLICATE','REJECTED')"
                )
            ),
            "resources": session.scalar(text("SELECT count(*) FROM resources")),
            "dispatches": session.scalar(text("SELECT count(*) FROM dispatches")),
            "users": session.scalar(text("SELECT count(*) FROM users")),
        }
    print("Seeded:", counts)
    print(f"Sign in as load-dispatcher@raksha.example / {LOAD_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
