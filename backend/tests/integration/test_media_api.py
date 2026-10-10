"""Media upload validation — the highest-risk input path in the platform."""

from __future__ import annotations

import random
import struct
import zlib

from fastapi.testclient import TestClient

from app.models.enums import UserRole


def png_bytes(width: int = 1, height: int = 1, *, noisy: bool = False) -> bytes:
    """A real, minimal PNG, so magic-byte validation sees genuine content.

    ``noisy`` fills the image with random pixels so it does not compress away —
    useful when a test needs the encoded file to actually be large.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    if noisy:
        raw = b"".join(b"\x00" + random.randbytes(3 * width) for _ in range(height))
    else:
        raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_incident(authed_client, make_user, incident_payload) -> tuple[TestClient, dict]:
    reporter = make_user(UserRole.CITIZEN)
    client = authed_client(reporter)
    created = client.post("/api/v1/incidents", json=incident_payload).json()
    return client, created


def test_a_reporter_can_attach_a_photograph(
    authed_client, make_user, incident_payload
) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] > 0
    assert "storage_key" not in body, "the storage layout is not client business"


def test_uploaded_media_appears_on_the_incident(
    authed_client, make_user, incident_payload
) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    )
    listing = client.get(f"/api/v1/incidents/{incident['id']}/media").json()
    assert len(listing) == 1


def test_media_content_is_served_back_as_an_attachment(
    authed_client, make_user, incident_payload
) -> None:
    """Never inline: an upload must not become stored XSS in an operator's browser."""
    client, incident = make_incident(authed_client, make_user, incident_payload)
    media = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    ).json()

    response = client.get(f"/api/v1/media/{media['id']}/content")
    assert response.status_code == 200
    assert response.content == png_bytes()
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_an_oversized_upload_is_refused(
    authed_client, make_user, incident_payload, monkeypatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "media_max_bytes", 512)
    client, incident = make_incident(authed_client, make_user, incident_payload)

    oversized = png_bytes(64, 64, noisy=True)
    assert len(oversized) > 512
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "MEDIA_TOO_LARGE"


def test_a_disallowed_mime_type_is_refused(
    authed_client, make_user, incident_payload
) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 415


def test_a_payload_disguised_as_an_image_is_refused(
    authed_client, make_user, incident_payload
) -> None:
    """The declared type must agree with the actual bytes."""
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("shell.png", b"<?php system($_GET['c']); ?>", "image/png")},
    )
    assert response.status_code == 415
    assert "do not match" in response.json()["error"]["message"]


def test_an_empty_file_is_refused(authed_client, make_user, incident_payload) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code in (400, 415)


def test_a_traversal_filename_is_stripped_to_its_basename(
    authed_client, make_user, incident_payload
) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("../../../../etc/passwd.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 201
    assert "/" not in (response.json()["original_filename"] or "")


def test_a_stranger_cannot_attach_media_to_someone_elses_incident(
    client: TestClient, authed_client, make_user, incident_payload
) -> None:
    _, incident = make_incident(authed_client, make_user, incident_payload)
    stranger = authed_client(make_user(UserRole.CITIZEN))
    response = stranger.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 404


def test_a_stranger_cannot_read_someone_elses_media(
    client: TestClient, authed_client, make_user, incident_payload
) -> None:
    owner_client, incident = make_incident(authed_client, make_user, incident_payload)
    media = owner_client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    ).json()

    stranger = authed_client(make_user(UserRole.CITIZEN))
    assert stranger.get(f"/api/v1/media/{media['id']}/content").status_code == 404


def test_a_dispatcher_can_read_incident_media(
    client: TestClient, authed_client, make_user, incident_payload
) -> None:
    owner_client, incident = make_incident(authed_client, make_user, incident_payload)
    media = owner_client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    ).json()

    dispatcher = authed_client(make_user(UserRole.DISPATCHER))
    assert dispatcher.get(f"/api/v1/media/{media['id']}/content").status_code == 200


def test_uploading_requires_authentication(
    client: TestClient, authed_client, make_user, incident_payload
) -> None:
    _, incident = make_incident(authed_client, make_user, incident_payload)
    client.headers.pop("Authorization", None)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/media",
        files={"file": ("scene.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 401


# --- malware scanning (Phase 16) ---------------------------------------------
import pytest  # noqa: E402

from app.models.enums import ScanStatus  # noqa: E402
from app.services import media_service  # noqa: E402
from app.services.scanners import ScannerUnavailableError, ScanOutcome  # noqa: E402


class _StubScanner:
    def __init__(self, result: ScanOutcome | Exception) -> None:
        self.result = result

    def scan(self, content: bytes) -> ScanOutcome:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def use_scanner(monkeypatch):
    def _use(result: ScanOutcome | Exception) -> None:
        monkeypatch.setattr(
            media_service, "get_scanner", lambda settings: _StubScanner(result)
        )

    return _use


def _upload(client: TestClient, incident_id: str):
    return client.post(
        f"/api/v1/incidents/{incident_id}/media",
        files={"file": ("photo.png", png_bytes(), "image/png")},
    )


def test_an_upload_with_no_scanner_is_recorded_as_unscanned(
    authed_client, make_user, incident_payload
) -> None:
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = _upload(client, incident["id"])
    assert response.status_code == 201
    assert response.json()["scan_status"] == "UNSCANNED"


def test_a_clean_scan_is_recorded(
    authed_client, make_user, incident_payload, use_scanner
) -> None:
    use_scanner(ScanOutcome(ScanStatus.CLEAN))
    client, incident = make_incident(authed_client, make_user, incident_payload)
    assert _upload(client, incident["id"]).json()["scan_status"] == "CLEAN"


def test_an_infected_upload_is_refused_and_never_stored(
    authed_client, make_user, incident_payload, use_scanner, tmp_path, db_session
) -> None:
    use_scanner(ScanOutcome(ScanStatus.INFECTED, "Eicar-Test-Signature"))
    client, incident = make_incident(authed_client, make_user, incident_payload)

    response = _upload(client, incident["id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MEDIA_INFECTED"
    assert "Eicar" not in response.text  # the signature stays in the audit log

    assert not list((tmp_path / "media").rglob("*.png"))
    listed = client.get(f"/api/v1/incidents/{incident['id']}/media").json()
    assert listed == []

    from sqlalchemy import select

    from app.models.incident import AuditLog

    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "media.rejected_malware")
    ).all()
    assert len(audited) == 1
    assert audited[0].event_metadata == {"signature": "Eicar-Test-Signature"}


def test_an_unreachable_scanner_does_not_block_the_upload_by_default(
    authed_client, make_user, incident_payload, use_scanner
) -> None:
    use_scanner(ScannerUnavailableError("down"))
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = _upload(client, incident["id"])
    assert response.status_code == 201
    assert response.json()["scan_status"] == "UNSCANNED"


def test_an_unreachable_scanner_blocks_the_upload_when_scanning_is_required(
    authed_client, make_user, incident_payload, use_scanner, monkeypatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "clamav_required", True)
    use_scanner(ScannerUnavailableError("down"))
    client, incident = make_incident(authed_client, make_user, incident_payload)
    response = _upload(client, incident["id"])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MEDIA_SCAN_UNAVAILABLE"
