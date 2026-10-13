"""AI analysis: request a proposal, and review it.

CLAUDE.md section 2 rule 1 is the thing under test throughout this file: an AI
proposal never changes an incident by itself. Every accepted or edited field
must arrive through the same audited path a dispatcher's manual correction
uses, and a rejected or never-reviewed proposal must leave the incident
untouched.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import UserRole
from app.models.incident import AuditLog


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def enable_ai(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_enabled", True)


# --- requesting an analysis ----------------------------------------------
def test_ai_is_disabled_by_default_and_reporting_is_unaffected(
    as_role, incident_payload
) -> None:
    """CLAUDE.md section 2 rule 7: AI is never on the critical path."""
    client, _ = as_role(UserRole.CITIZEN)
    incident = report(client, incident_payload)
    assert incident["status"] == "REPORTED"

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    response = dispatcher.post(f"/api/v1/incidents/{incident['id']}/analyses")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ANALYSIS_UNAVAILABLE"


def test_a_citizen_cannot_request_an_analysis(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    incident = report(client, incident_payload)
    assert client.post(f"/api/v1/incidents/{incident['id']}/analyses").status_code == 403


def test_a_dispatcher_can_request_an_analysis(
    as_role, incident_payload, monkeypatch
) -> None:
    enable_ai(monkeypatch)
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    response = dispatcher.post(f"/api/v1/incidents/{incident['id']}/analyses")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["model_name"]
    assert body["model_version"]
    assert body["review_decision"] is None
    # The report's own words mention trapped people and rising water.
    assert body["proposed_category"] == "FLOOD"
    assert body["people_trapped"] is True


def test_requesting_an_analysis_for_an_unknown_incident_is_404(
    as_role, monkeypatch
) -> None:
    enable_ai(monkeypatch)
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    response = dispatcher.post(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000/analyses"
    )
    assert response.status_code == 404


def test_the_analysis_is_audited(
    as_role, incident_payload, monkeypatch, db_session: Session
) -> None:
    enable_ai(monkeypatch)
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    dispatcher.post(f"/api/v1/incidents/{incident['id']}/analyses")

    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "ai.analysis_created")
    ).all()
    assert len(entries) == 1


def test_listing_analyses_for_an_unknown_incident_is_404(as_role, monkeypatch) -> None:
    enable_ai(monkeypatch)
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    response = dispatcher.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000/analyses"
    )
    assert response.status_code == 404


def test_a_citizen_cannot_list_analyses(as_role, incident_payload, monkeypatch) -> None:
    enable_ai(monkeypatch)
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    assert citizen.get(f"/api/v1/incidents/{incident['id']}/analyses").status_code == 403


# --- reviewing a proposal --------------------------------------------------
def _propose(as_role, incident_payload, monkeypatch) -> tuple[TestClient, dict, dict]:
    """Report an incident and produce one AI proposal for it."""
    enable_ai(monkeypatch)
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    analysis = dispatcher.post(f"/api/v1/incidents/{incident['id']}/analyses").json()
    return dispatcher, incident, analysis


def test_a_responder_cannot_review_a_proposal(
    as_role, incident_payload, monkeypatch
) -> None:
    _, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    responder, _ = as_role(UserRole.RESPONDER)
    response = responder.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 403


def test_accepting_a_proposal_applies_it_and_recalculates_priority(
    as_role, incident_payload, monkeypatch
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    assert analysis["proposed_category"] == "FLOOD"

    response = dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "ACCEPTED", "note": "Matches the photos too."},
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["review_decision"] == "ACCEPTED"
    assert reviewed["applied_fields"]["category"] == "FLOOD"

    updated = dispatcher.get(f"/api/v1/incidents/{incident['id']}").json()
    assert updated["category"] == "FLOOD"
    # The engine, not the AI, produced this score; it is simply recomputed
    # against the (now AI-confirmed) facts.
    assert updated["priority_score"] > 0


def test_editing_a_proposal_applies_the_dispatchers_values_not_the_models(
    as_role, incident_payload, monkeypatch
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)

    response = dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "EDITED", "category": "FIRE", "people_affected": 9},
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied_fields"] == {"category": "FIRE", "people_affected": 9}

    updated = dispatcher.get(f"/api/v1/incidents/{incident['id']}").json()
    assert updated["category"] == "FIRE"
    assert updated["people_affected"] == 9


def test_an_edit_with_no_corrected_value_is_rejected(
    as_role, incident_payload, monkeypatch
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    response = dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "EDITED"},
    )
    assert response.status_code == 400


def test_rejecting_a_proposal_leaves_the_incident_untouched(
    as_role, incident_payload, monkeypatch
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    before = dispatcher.get(f"/api/v1/incidents/{incident['id']}").json()

    response = dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "REJECTED", "note": "Description does not support this."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied_fields"] is None

    after = dispatcher.get(f"/api/v1/incidents/{incident['id']}").json()
    assert after["category"] == before["category"]
    assert after["priority_score"] == before["priority_score"]


def test_a_reviewed_analysis_cannot_be_reviewed_again(
    as_role, incident_payload, monkeypatch
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    url = f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review"
    first = dispatcher.post(url, json={"decision": "REJECTED"})
    assert first.status_code == 200

    second = dispatcher.post(url, json={"decision": "ACCEPTED"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ANALYSIS_ALREADY_REVIEWED"


def test_the_review_is_audited(
    as_role, incident_payload, monkeypatch, db_session: Session
) -> None:
    dispatcher, incident, analysis = _propose(as_role, incident_payload, monkeypatch)
    dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/analyses/{analysis['id']}/review",
        json={"decision": "ACCEPTED"},
    )
    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "ai.analysis_reviewed")
    ).all()
    assert len(entries) == 1


def test_a_proposal_can_never_carry_a_priority_or_dispatch_field(
    as_role, incident_payload, monkeypatch
) -> None:
    """CLAUDE.md section 2 rule 1: AI proposes, it never decides."""
    _, _, analysis = _propose(as_role, incident_payload, monkeypatch)
    assert not set(analysis) & {"priority_score", "priority_band", "assigned_to"}


# --- photographs (Phase 8) ---------------------------------------------------
def _recording_analyzer(seen: list):
    """Stands in for ``get_analyzer``: records the vision settings and request the
    service chose, and answers with the real text analyzer. No provider client is built.
    """
    from ai.nlp.text_analyzer import HeuristicTextAnalyzer

    def factory(enabled, vision=None):
        text = HeuristicTextAnalyzer()

        class Recorder:
            name, version = text.name, text.version

            def analyze(self, request):
                seen.append((vision, request))
                return text.analyze(request)

        return Recorder()

    return factory


def test_photos_go_to_a_provider_only_when_one_is_configured(
    as_role, incident_payload, monkeypatch, db_session: Session
) -> None:
    from pydantic import SecretStr

    from app.services import analysis_service
    from tests.integration.test_media_api import png_bytes

    seen: list = []
    monkeypatch.setattr(analysis_service, "get_analyzer", _recording_analyzer(seen))
    enable_ai(monkeypatch)

    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    uploaded = citizen.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    analyses = f"/api/v1/incidents/{incident['id']}/analyses"

    # No provider configured: text only, and the photograph is not even read.
    assert dispatcher.post(analyses).status_code == 201
    vision, request = seen[-1]
    assert vision is None
    assert request.image_bytes == []

    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "ai_api_key", SecretStr("sk-test-not-real"))
    assert dispatcher.post(analyses).status_code == 201
    vision, request = seen[-1]
    assert vision.provider == "anthropic"
    assert vision.api_key == "sk-test-not-real"
    assert len(request.image_bytes) == 1
    assert request.image_bytes[0].startswith(b"\x89PNG")

    # The transfer is on the record: how many photographs left, and to whom.
    entries = db_session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "ai.analysis_created")
        .order_by(AuditLog.created_at)
    ).all()
    assert [entry.event_metadata["photos_sent"] for entry in entries] == [0, 1]


def test_with_ai_off_no_photo_is_sent_even_if_a_provider_is_set(
    monkeypatch, db_session: Session
) -> None:
    from pydantic import SecretStr

    from app.services.analysis_service import AnalysisService

    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "ai_api_key", SecretStr("sk-test-not-real"))
    assert AnalysisService(db_session, settings)._vision_config() is None
