#!/usr/bin/env python3
"""Seed a development database with synthetic data.

Everything here is invented. No real emergency, person or location is
represented, and the script refuses to run against a production environment.

    python database/seeds/seed_development.py [--reset]
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Environment, get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    Dispatch,
    Hospital,
    InboundPatientNotice,
    Incident,
    IncidentCategory,
    IncidentMedia,
    IncidentStatusHistory,
    IncidentStatus,
    RefreshToken,
    Resource,
    ResourceStatus,
    ResourceType,
    User,
    UserRole,
)
from app.services.priority import PriorityInput, calculate_priority  # noqa: E402
from app.utils.codes import generate_reference_code  # noqa: E402
from app.utils.geo import to_ewkt, validate_coordinates  # noqa: E402
from app.utils.time import utcnow  # noqa: E402

#: Obvious, uniform and only ever accepted outside production.
SEED_PASSWORD = "raksha-development-only"

SEED_USERS: list[tuple[str, str, UserRole]] = [
    ("citizen@raksha.example", "Asha Ramanathan", UserRole.CITIZEN),
    ("citizen2@raksha.example", "Vikram Prasad", UserRole.CITIZEN),
    ("responder@raksha.example", "Meera Nair", UserRole.RESPONDER),
    ("dispatcher@raksha.example", "Karthik Subramanian", UserRole.DISPATCHER),
    ("hospital@raksha.example", "Dr Lakshmi Iyer", UserRole.HOSPITAL_OPERATOR),
    ("admin@raksha.example", "Ravi Menon", UserRole.ADMIN),
]

#: (category, description, people_affected, trapped, medical, danger, status)
SEED_INCIDENTS: list[
    tuple[IncidentCategory, str, int | None, bool, bool, bool, IncidentStatus]
] = [
    (
        IncidentCategory.FLOOD,
        "Five people are trapped inside a house on the ground floor and the "
        "water is rising fast. Two of them are elderly.",
        5,
        True,
        True,
        True,
        IncidentStatus.REPORTED,
    ),
    (
        IncidentCategory.FIRE,
        "Thick smoke is coming from a first-floor flat. Neighbours are "
        "evacuating but we cannot see inside the building.",
        12,
        False,
        False,
        True,
        IncidentStatus.UNDER_REVIEW,
    ),
    (
        IncidentCategory.ROAD_ACCIDENT,
        "Two cars have collided at the junction. One driver appears to be "
        "stuck in the vehicle and is not moving much.",
        3,
        True,
        True,
        False,
        IncidentStatus.ASSIGNED,
    ),
    (
        IncidentCategory.MEDICAL,
        "An elderly man has collapsed at the bus stand and is struggling to "
        "breathe. A crowd has gathered around him.",
        1,
        False,
        True,
        True,
        IncidentStatus.RESPONDER_EN_ROUTE,
    ),
    (
        IncidentCategory.BUILDING_COLLAPSE,
        "Part of a boundary wall has come down after the rain. It fell onto "
        "the pavement where people usually walk.",
        2,
        False,
        False,
        False,
        IncidentStatus.RECEIVED,
    ),
    (
        IncidentCategory.GAS_LEAK,
        "There is a strong smell of gas near the shops on the main road. "
        "Nobody appears to be hurt yet.",
        None,
        False,
        False,
        True,
        IncidentStatus.PRIORITIZED,
    ),
    (
        IncidentCategory.LANDSLIDE,
        "Mud and rocks have slipped onto the hill road and blocked it "
        "completely. No vehicles can get through.",
        None,
        False,
        False,
        False,
        IncidentStatus.RECEIVED,
    ),
    (
        IncidentCategory.ELECTRICAL_HAZARD,
        "A power line has come down across the lane and is sparking. We have "
        "kept children away from it.",
        None,
        False,
        False,
        True,
        IncidentStatus.REPORTED,
    ),
    (
        IncidentCategory.MISSING_PERSON,
        "A twelve-year-old has not returned from school. Last seen near the "
        "canal three hours ago.",
        1,
        False,
        False,
        False,
        IncidentStatus.UNDER_REVIEW,
    ),
    (
        IncidentCategory.OTHER,
        "A large tree has fallen across the road after the storm. Traffic is "
        "backing up but nobody seems to be injured.",
        None,
        False,
        False,
        False,
        IncidentStatus.RESOLVED,
    ),
]

#: (call sign, name, type, offset from CENTRE in degrees, capabilities, crew, operated by the seeded responder)
SEED_RESOURCES: list[
    tuple[str, str, ResourceType, tuple[float, float], list[str], int, bool]
] = [
    (
        "AMB-01",
        "Egmore Ambulance 1",
        ResourceType.AMBULANCE,
        (0.020, -0.010),
        ["advanced_life_support"],
        3,
        True,
    ),
    (
        "AMB-02",
        "Adyar Ambulance 2",
        ResourceType.AMBULANCE,
        (-0.045, 0.012),
        ["basic_life_support"],
        2,
        False,
    ),
    (
        "FIRE-01",
        "Fire Station Anna Nagar",
        ResourceType.FIRE_ENGINE,
        (0.030, -0.040),
        ["fire_suppression", "rescue_cutting"],
        5,
        False,
    ),
    (
        "RES-01",
        "Urban Search & Rescue Team",
        ResourceType.RESCUE_TEAM,
        (-0.010, 0.030),
        ["structural_rescue", "first_aid"],
        6,
        False,
    ),
    (
        "BOAT-01",
        "Flood Rescue Boat, Cooum",
        ResourceType.RESCUE_BOAT,
        (0.005, 0.020),
        ["water_rescue"],
        4,
        False,
    ),
    (
        "POL-01",
        "Traffic Police Patrol",
        ResourceType.POLICE_UNIT,
        (-0.020, -0.025),
        ["traffic_control"],
        2,
        False,
    ),
]

#: (code, name, offset from CENTRE, total beds, free beds, ICU total, ICU free, specialties)
SEED_HOSPITALS: list[
    tuple[str, str, tuple[float, float], int, int, int, int, list[str]]
] = [
    (
        "GH-CHN",
        "General Hospital, Chennai",
        (0.012, 0.002),
        220,
        34,
        40,
        5,
        ["trauma", "burns", "cardiac"],
    ),
    (
        "RH-ADY",
        "Riverside Hospital, Adyar",
        (-0.050, 0.015),
        120,
        18,
        16,
        2,
        ["trauma", "paediatrics"],
    ),
    (
        "CH-ANA",
        "Community Hospital, Anna Nagar",
        (0.032, -0.035),
        60,
        9,
        6,
        0,
        ["general"],
    ),
]

#: Scattered around the configured default centre so the map is not one dot.
CENTRE = (13.0827, 80.2707)
SPREAD_DEGREES = 0.08


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing incidents and seed users before seeding.",
    )
    parser.add_argument(
        "--seed", type=int, default=20260101, help="Random seed, for repeatability."
    )
    return parser


def assert_not_production() -> None:
    settings = get_settings()
    if settings.environment in (Environment.PRODUCTION, Environment.STAGING):
        raise SystemExit(
            f"Refusing to seed synthetic data into '{settings.environment}'. "
            "This script is for development only."
        )


def reset(session: Session) -> None:
    """Remove seeded data. Order respects the foreign keys."""
    session.execute(delete(AuditLog))
    session.execute(delete(InboundPatientNotice))
    session.execute(delete(Dispatch))
    session.execute(delete(IncidentStatusHistory))
    session.execute(delete(IncidentMedia))
    session.execute(delete(Incident))
    session.execute(
        delete(Resource).where(
            Resource.call_sign.in_([row[0] for row in SEED_RESOURCES])
        )
    )
    session.execute(
        delete(Hospital).where(Hospital.code.in_([row[0] for row in SEED_HOSPITALS]))
    )
    session.execute(delete(RefreshToken))
    session.execute(
        delete(User).where(User.email.in_([email for email, _, _ in SEED_USERS]))
    )
    session.commit()


def seed_users(session: Session) -> dict[UserRole, User]:
    created: dict[UserRole, User] = {}
    for email, full_name, role in SEED_USERS:
        existing = session.scalars(select(User).where(User.email == email)).first()
        if existing:
            created.setdefault(role, existing)
            continue

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(SEED_PASSWORD),
            role=role,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        created.setdefault(role, user)

    session.commit()
    return created


def seed_incidents(session: Session, users: dict[UserRole, User]) -> int:
    reporter = users[UserRole.CITIZEN]
    dispatcher = users.get(UserRole.DISPATCHER)
    now = utcnow()
    created = 0

    for index, row in enumerate(SEED_INCIDENTS):
        category, description, affected, trapped, medical, danger, status = row

        latitude = CENTRE[0] + random.uniform(-SPREAD_DEGREES, SPREAD_DEGREES)
        longitude = CENTRE[1] + random.uniform(-SPREAD_DEGREES, SPREAD_DEGREES)
        coords = validate_coordinates(latitude, longitude)
        reported_at = now - timedelta(minutes=random.randint(5, 600))

        incident = Incident(
            reference_code=generate_reference_code(),
            reported_by_id=reporter.id,
            category=category,
            description=description,
            latitude=coords.latitude,
            longitude=coords.longitude,
            geom=to_ewkt(coords),
            location_accuracy_m=random.choice([8, 15, 40, 120]),
            address_text=f"Sector {index + 1}, Development Area",
            status=status,
            people_affected=affected,
            people_trapped=trapped,
            medical_required=medical,
            immediate_danger=danger,
            created_at=reported_at,
        )

        scored = calculate_priority(
            PriorityInput(
                category=incident.category,
                people_affected=affected,
                people_trapped=trapped,
                medical_required=medical,
                immediate_danger=danger,
                reported_at=reported_at,
            ),
            now=now,
        )
        incident.priority_score = scored.score
        incident.priority_band = scored.band
        incident.priority_factors = scored.factors_as_json()

        if status is IncidentStatus.RESOLVED:
            incident.resolved_at = now

        session.add(incident)
        session.flush()

        session.add(
            IncidentStatusHistory(
                incident_id=incident.id,
                from_status=None,
                to_status=IncidentStatus.REPORTED,
                changed_by_id=reporter.id,
                note="Report submitted by the reporter.",
            )
        )
        if status is not IncidentStatus.REPORTED and dispatcher is not None:
            session.add(
                IncidentStatusHistory(
                    incident_id=incident.id,
                    from_status=IncidentStatus.REPORTED,
                    to_status=status,
                    changed_by_id=dispatcher.id,
                    note="Seeded state for development.",
                )
            )
        created += 1

    session.commit()
    return created


def seed_resources(session: Session, users: dict[UserRole, User]) -> int:
    """A small, obviously invented fleet. The first unit is operated by the seeded
    responder, so the responder application has something to be assigned."""
    responder = users.get(UserRole.RESPONDER)
    created = 0
    for call_sign, name, kind, offset, capabilities, crew, operated in SEED_RESOURCES:
        if session.scalars(
            select(Resource).where(Resource.call_sign == call_sign)
        ).first():
            continue
        coords = validate_coordinates(CENTRE[0] + offset[0], CENTRE[1] + offset[1])
        session.add(
            Resource(
                call_sign=call_sign,
                name=name,
                resource_type=kind,
                status=ResourceStatus.AVAILABLE,
                latitude=coords.latitude,
                longitude=coords.longitude,
                geom=to_ewkt(coords),
                capabilities=capabilities,
                crew_size=crew,
                operator_id=responder.id if operated and responder else None,
            )
        )
        created += 1
    session.commit()
    return created


def seed_hospitals(session: Session, users: dict[UserRole, User]) -> int:
    """Hospitals, the first maintained by the seeded hospital operator."""
    operator = users.get(UserRole.HOSPITAL_OPERATOR)
    created = 0
    for index, row in enumerate(SEED_HOSPITALS):
        code, name, offset, total, free, icu_total, icu_free, specialties = row
        if session.scalars(select(Hospital).where(Hospital.code == code)).first():
            continue
        coords = validate_coordinates(CENTRE[0] + offset[0], CENTRE[1] + offset[1])
        session.add(
            Hospital(
                code=code,
                name=name,
                latitude=coords.latitude,
                longitude=coords.longitude,
                geom=to_ewkt(coords),
                total_beds=total,
                available_beds=free,
                icu_total=icu_total,
                icu_available=icu_free,
                accepting_emergencies=True,
                specialties=specialties,
                managed_by_id=operator.id if index == 0 and operator else None,
                capacity_updated_at=utcnow(),
            )
        )
        created += 1
    session.commit()
    return created


def main() -> None:
    args = build_argument_parser().parse_args()
    assert_not_production()
    random.seed(args.seed)

    with Session(get_engine()) as session:
        if args.reset:
            reset(session)
            print("Cleared existing incidents and seed users.")

        users = seed_users(session)
        print(f"Seeded {len(SEED_USERS)} users (password: {SEED_PASSWORD})")

        count = seed_incidents(session, users)
        print(f"Seeded {count} synthetic incidents around {CENTRE}.")

        print(
            f"Seeded {seed_resources(session, users)} new resources (the first is operated by the seeded responder)."
        )
        print(
            f"Seeded {seed_hospitals(session, users)} new hospitals (the first is maintained by the seeded hospital operator)."
        )

    print("\nSign in with any of:")
    for email, _, role in SEED_USERS:
        print(f"  {email:<34} {role.value}")


if __name__ == "__main__":
    main()
