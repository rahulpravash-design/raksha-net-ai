"""Resource business rules: inventory, status, and ranked recommendations.

Phase 10 is deliberately recommend-only. This service can tell a dispatcher
which units are nearest and best suited; it cannot send one. Dispatch is
Phase 11, and it requires a named human approver (``CLAUDE.md`` section 2,
rule 1).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.enums import (
    CATEGORY_RESOURCE_PREFERENCE,
    DISPATCH_ROLES,
    INCIDENT_VIEW_ROLES,
    OPERATIONAL_ROLES,
    ResourceStatus,
    ResourceType,
)
from app.models.resource import Resource
from app.models.user import User
from app.repositories.incident_repository import IncidentRepository
from app.repositories.resource_repository import ResourceRepository
from app.repositories.user_repository import UserRepository
from app.schemas.resource import (
    NearbyResource,
    ResourceCreate,
    ResourceRecommendation,
    ResourceRecommendations,
    ResourceStatsSummary,
    ResourceStatusChange,
    ResourceUpdate,
)
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.utils.geo import validate_coordinates
from app.utils.time import utcnow

logger = get_logger(__name__)

#: Average urban response speed used for the straight-line ETA estimate.
#: This is not routing: it ignores roads, traffic and terrain, and the API
#: labels every figure it produces as an estimate for exactly that reason.
ASSUMED_SPEED_KMH = 30.0
MIN_ESTIMATED_MINUTES = 1

#: Recommendation search widens in these steps until something is found.
RECOMMENDATION_RADII_KM: tuple[float, ...] = (5.0, 15.0, 40.0)
RECOMMENDATION_LIMIT = 10


def estimate_minutes(distance_km: float, speed_kmh: float = ASSUMED_SPEED_KMH) -> int:
    """A straight-line travel estimate, rounded up to whole minutes.

    Deliberately pessimistic in the only way it can be honest: it is a lower
    bound, because the real route is never shorter than the direct line.
    """
    if distance_km <= 0:
        return MIN_ESTIMATED_MINUTES
    minutes = (distance_km / speed_kmh) * 60.0
    return max(MIN_ESTIMATED_MINUTES, int(minutes + 0.999))


class ResourceService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = ResourceRepository(session)
        self.incidents = IncidentRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    # -- inventory ----------------------------------------------------------
    def create(
        self,
        payload: ResourceCreate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Resource:
        context = context or RequestContext()
        self._assert_dispatch_role(actor)

        if self.repo.get_by_call_sign(payload.call_sign) is not None:
            raise ConflictError(
                "A resource with that call sign already exists.",
                code="RESOURCE_CALL_SIGN_TAKEN",
            )

        coords = validate_coordinates(payload.latitude, payload.longitude, self.settings)
        resource = Resource(
            call_sign=payload.call_sign,
            name=payload.name,
            resource_type=payload.resource_type,
            status=ResourceStatus.AVAILABLE,
            base_address=payload.base_address,
            capabilities=payload.capabilities,
            crew_size=payload.crew_size,
            contact_phone=payload.contact_phone,
            operator_id=self._validated_operator(payload.operator_id),
            status_changed_at=utcnow(),
        )
        self.repo.set_location(resource, coords)
        self.repo.add(resource)

        self.audit.record(
            AuditAction.RESOURCE_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="resource",
            entity_id=resource.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "call_sign": resource.call_sign,
                "type": resource.resource_type.value,
            },
        )
        self.session.commit()
        self.session.refresh(resource)
        return resource

    def update(
        self,
        resource_id: uuid.UUID,
        payload: ResourceUpdate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Resource:
        context = context or RequestContext()
        self._assert_dispatch_role(actor)
        resource = self._get_or_404(resource_id)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise ValidationError("No fields were supplied to update.")

        latitude = changes.pop("latitude", None)
        longitude = changes.pop("longitude", None)
        if (latitude is None) != (longitude is None):
            raise ValidationError("Latitude and longitude must be supplied together.")
        if latitude is not None and longitude is not None:
            self.repo.set_location(
                resource, validate_coordinates(latitude, longitude, self.settings)
            )

        if "operator_id" in changes:
            changes["operator_id"] = self._validated_operator(changes["operator_id"])

        for field, value in changes.items():
            setattr(resource, field, value)

        self.audit.record(
            AuditAction.RESOURCE_UPDATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="resource",
            entity_id=resource.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"fields": sorted(changes)},
        )
        self.session.commit()
        self.session.refresh(resource)
        return resource

    def change_status(
        self,
        resource_id: uuid.UUID,
        payload: ResourceStatusChange,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Resource:
        """Set a unit's operational status.

        A dispatcher may set any unit's status; a responder may set only the
        status of a unit they operate — they are the person who actually knows
        where it is.
        """
        context = context or RequestContext()
        resource = self._get_or_404(resource_id)

        is_operator = (
            resource.operator_id is not None and resource.operator_id == actor.id
        )
        if actor.role not in DISPATCH_ROLES and not is_operator:
            raise NotFoundError("Resource not found.")

        if (payload.latitude is None) != (payload.longitude is None):
            raise ValidationError("Latitude and longitude must be supplied together.")
        if payload.latitude is not None and payload.longitude is not None:
            self.repo.set_location(
                resource,
                validate_coordinates(payload.latitude, payload.longitude, self.settings),
            )

        previous = resource.status
        resource.status = payload.status
        resource.status_changed_at = utcnow()

        self.audit.record(
            AuditAction.RESOURCE_STATUS_CHANGED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="resource",
            entity_id=resource.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "from": previous.value,
                "to": payload.status.value,
                "note": payload.note,
            },
        )
        self.session.commit()
        self.session.refresh(resource)
        return resource

    # -- reads --------------------------------------------------------------
    def get_for_user(self, resource_id: uuid.UUID, actor: User) -> Resource:
        self._assert_operational(actor)
        return self._get_or_404(resource_id)

    def list_for_user(
        self,
        actor: User,
        *,
        offset: int,
        limit: int,
        resource_types: Sequence[ResourceType] | None = None,
        statuses: Sequence[ResourceStatus] | None = None,
        active_only: bool = True,
        query: str | None = None,
    ) -> tuple[list[Resource], int]:
        self._assert_operational(actor)
        return self.repo.search(
            offset=offset,
            limit=limit,
            resource_types=resource_types,
            statuses=statuses,
            active_only=active_only,
            query=query,
        )

    def stats(self, actor: User) -> ResourceStatsSummary:
        self._assert_operational(actor)
        by_status = self.repo.count_by_status()
        rows, total = self.repo.search(offset=0, limit=1000)
        by_type: dict[str, int] = {}
        for resource in rows:
            by_type[resource.resource_type.value] = (
                by_type.get(resource.resource_type.value, 0) + 1
            )
        return ResourceStatsSummary(
            total_active=total, by_status=by_status, by_type=by_type
        )

    def find_nearby(
        self,
        actor: User,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        resource_types: Sequence[ResourceType] | None = None,
        available_only: bool = True,
        limit: int = 20,
    ) -> list[NearbyResource]:
        self._assert_operational(actor)
        coords = validate_coordinates(latitude, longitude, self.settings)
        capped = min(radius_km, self.settings.geo_max_search_radius_km)
        lat, lon = coords.as_floats

        rows = self.repo.find_nearby(
            latitude=lat,
            longitude=lon,
            radius_km=capped,
            resource_types=resource_types,
            available_only=available_only,
            limit=limit,
        )
        return [NearbyResource(**row) for row in rows]

    # -- recommendations ----------------------------------------------------
    def recommend_for_incident(
        self, incident_id: uuid.UUID, *, actor: User, limit: int = RECOMMENDATION_LIMIT
    ) -> ResourceRecommendations:
        """Rank nearby available units for an incident. Suggestions only.

        The search widens in steps rather than starting wide: the nearest
        suitable unit is almost always the right one, and a 40 km list of
        ambulances is noise when there is one two streets away.
        """
        if actor.role not in INCIDENT_VIEW_ROLES:
            raise ForbiddenError(
                "Only dispatch-side roles can rank units for an incident."
            )
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")

        preferred = CATEGORY_RESOURCE_PREFERENCE.get(incident.category, ())
        lat = float(incident.latitude)
        lon = float(incident.longitude)
        needed = self._needed_capabilities(incident)

        for radius in RECOMMENDATION_RADII_KM:
            capped = min(radius, self.settings.geo_max_search_radius_km)
            rows = self.repo.find_nearby(
                latitude=lat,
                longitude=lon,
                radius_km=capped,
                resource_types=None,
                available_only=True,
                limit=limit * 3,
            )
            if rows:
                items = self._rank(rows, preferred=preferred, needed=needed)[:limit]
                return ResourceRecommendations(
                    incident_id=incident.id,
                    searched_radius_km=capped,
                    items=items,
                )

        widest = min(RECOMMENDATION_RADII_KM[-1], self.settings.geo_max_search_radius_km)
        return ResourceRecommendations(
            incident_id=incident.id,
            searched_radius_km=widest,
            items=[],
            note=(
                f"No available resource was found within {widest:g} km. "
                "Widen the search manually or request mutual aid."
            ),
        )

    def _rank(
        self,
        rows: list[dict[str, object]],
        *,
        preferred: tuple[ResourceType, ...],
        needed: set[str],
    ) -> list[ResourceRecommendation]:
        scored: list[tuple[float, ResourceRecommendation]] = []

        for row in rows:
            nearby = NearbyResource(**row)  # type: ignore[arg-type]
            reasons: list[str] = []

            type_rank = (
                preferred.index(nearby.resource_type)
                if nearby.resource_type in preferred
                else len(preferred) + 1
            )
            type_match = nearby.resource_type in preferred
            if type_match:
                reasons.append(
                    f"{nearby.resource_type.value.replace('_', ' ').title()} "
                    "is a usual unit for this category"
                )

            matched = sorted(needed & {c.lower() for c in nearby.capabilities})
            if matched:
                reasons.append(f"Carries: {', '.join(matched)}")

            reasons.append(f"{nearby.distance_km:.1f} km away")

            # Suitability first, then distance. A closer unit that cannot do the
            # job is not a better recommendation than a suitable one further out.
            sort_key = (type_rank * 1000.0) - (len(matched) * 10.0) + nearby.distance_km
            scored.append(
                (
                    sort_key,
                    ResourceRecommendation(
                        resource=nearby,
                        rank=0,
                        type_match=type_match,
                        matched_capabilities=matched,
                        estimated_minutes=estimate_minutes(nearby.distance_km),
                        reasons=reasons,
                    ),
                )
            )

        scored.sort(key=lambda item: item[0])
        return [
            recommendation.model_copy(update={"rank": index + 1})
            for index, (_, recommendation) in enumerate(scored)
        ]

    @staticmethod
    def _needed_capabilities(incident: object) -> set[str]:
        """Capability tags implied by the incident's accepted facts."""
        needed: set[str] = set()
        if getattr(incident, "medical_required", False):
            needed.add("advanced_life_support")
        if getattr(incident, "people_trapped", False):
            needed.add("extrication")
        category = getattr(incident, "category", None)
        if category is not None and category.value == "FLOOD":
            needed.add("water_rescue")
        return needed

    # -- internals ----------------------------------------------------------
    def _get_or_404(self, resource_id: uuid.UUID) -> Resource:
        resource = self.repo.get(resource_id)
        if resource is None:
            raise NotFoundError("Resource not found.")
        return resource

    def _validated_operator(self, operator_id: uuid.UUID | None) -> uuid.UUID | None:
        if operator_id is None:
            return None
        operator = self.users.get(operator_id)
        if operator is None or not operator.is_active:
            raise ValidationError("The selected operator cannot be assigned.")
        if operator.role not in OPERATIONAL_ROLES:
            raise ValidationError("Only operational roles can operate a resource.")
        return operator_id

    @staticmethod
    def _assert_dispatch_role(actor: User) -> None:
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators can manage resources."
            )

    @staticmethod
    def _assert_operational(actor: User) -> None:
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles can view resources.")
