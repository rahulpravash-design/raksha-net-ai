"""Recognising a voice recording from its own bytes.

Only the containers browsers record into with ``MediaRecorder`` are accepted: WebM
(Chrome, Edge, Firefox), Ogg (Firefox) and MP4 (Safari). Each is told apart by its
opening bytes, so a declared type that disagrees with the file is caught.
"""

from __future__ import annotations

#: The declared types a voice recording may arrive as (parameters such as
#: ``;codecs=opus`` are stripped before comparison).
ACCEPTED_AUDIO_TYPES: tuple[str, ...] = ("audio/webm", "audio/ogg", "audio/mp4")

_EBML = b"\x1a\x45\xdf\xa3"  # WebM is a Matroska (EBML) document
_OGG = b"OggS"


def sniff_audio_type(content: bytes) -> str | None:
    """The container type the bytes actually are, or None if not one we accept."""
    if content.startswith(_EBML):
        return "audio/webm"
    if content.startswith(_OGG):
        return "audio/ogg"
    # ISO base media: a box size, then the "ftyp" box naming the brand.
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "audio/mp4"
    return None
