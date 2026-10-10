"""Metadata stripping: what is removed, what must survive, and what is refused.

The images are built byte by byte, so every segment and chunk under test is one
the test put there. They are structurally valid (the stripper never decodes pixels)
but not renderable; ``scripts/e2e`` and the integration tests cover real uploads.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from app.utils.image_metadata import (
    ImageMetadataError,
    _orientation,
    strip_jpeg,
    strip_metadata,
    strip_png,
    strip_webp,
)

GPS_TEXT = b"13.082700N 80.270700E"
SERIAL = b"SERIAL-123456789"


# --- builders -----------------------------------------------------------------------
def tiff(orientation: int | None, *, big: bool = False) -> bytes:
    """A TIFF block with Make (carrying a serial), optional Orientation and a GPS IFD."""
    e = ">" if big else "<"
    make = SERIAL + b"\x00"
    entries = 2 + (1 if orientation is not None else 0)
    ifd0_size = 2 + entries * 12 + 4
    make_offset = 8 + ifd0_size
    gps_offset = make_offset + len(make)
    out = bytearray(b"MM\x00*" if big else b"II*\x00")
    out += struct.pack(f"{e}I", 8)
    out += struct.pack(f"{e}H", entries)
    out += struct.pack(f"{e}HHII", 0x010F, 2, len(make), make_offset)  # Make
    if orientation is not None:
        value = struct.pack(f"{e}H", orientation) + b"\x00\x00"
        out += struct.pack(f"{e}HHI", 0x0112, 3, 1) + value
    out += struct.pack(f"{e}HHII", 0x8825, 4, 1, gps_offset)  # GPSInfo pointer
    out += struct.pack(f"{e}I", 0)
    out += make
    out += (
        struct.pack(f"{e}H", 1)
        + struct.pack(f"{e}HHI", 0x0002, 2, len(GPS_TEXT))
        + b"\x00\x00\x00\x00"
    )
    out += GPS_TEXT
    return bytes(out)


def segment(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def exif_segment(orientation: int | None, *, big: bool = False) -> bytes:
    return segment(0xE1, b"Exif\x00\x00" + tiff(orientation, big=big))


JFIF = segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
ICC = segment(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"PROFILE-BYTES")
MPF = segment(0xE2, b"MPF\x00" + b"multi-picture")
XMP = segment(
    0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>" + GPS_TEXT + b"</x:xmpmeta>"
)
IPTC = segment(0xED, b"Photoshop 3.0\x00" + GPS_TEXT)
COMMENT = segment(0xFE, b"taken at " + GPS_TEXT)
ADOBE = segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01")
DQT = segment(0xDB, b"\x00" + bytes(range(64)))
SOF = segment(0xC0, b"\x08\x00\x10\x00\x10\x01\x01\x11\x00")
DHT = segment(0xC4, b"\x00" + bytes(16) + b"\x00")
SOS = segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
SCAN = b"\x12\x34\xff\x00\x56\xff\xd0\x78\xff\x00\x9a"  # stuffing and a restart marker
EOI = b"\xff\xd9"


def jpeg(*segments: bytes) -> bytes:
    return b"\xff\xd8" + b"".join(segments) + DQT + SOF + DHT + SOS + SCAN + EOI


def png_chunk(kind: bytes, data: bytes = b"") -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


PNG_SIG = b"\x89PNG\r\n\x1a\n"
IHDR = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
IDAT = png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
IEND = png_chunk(b"IEND")


def webp_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    )


def webp(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --- JPEG ------------------------------------------------------------------------------------
def test_jpeg_loses_exif_xmp_iptc_and_comments() -> None:
    original = jpeg(JFIF, exif_segment(None), XMP, IPTC, COMMENT, MPF)
    assert GPS_TEXT in original and SERIAL in original

    cleaned = strip_jpeg(original)
    for secret in (GPS_TEXT, SERIAL, b"Exif", b"xmpmeta", b"Photoshop", b"multi-picture"):
        assert secret not in cleaned, secret


def test_jpeg_keeps_everything_needed_to_draw_it() -> None:
    cleaned = strip_jpeg(jpeg(JFIF, exif_segment(None), ICC, ADOBE))
    for needed in (JFIF, ICC, ADOBE, DQT, SOF, DHT, SOS):
        assert needed in cleaned
    # The compressed data after the scan header is byte for byte what was uploaded.
    assert cleaned.endswith(SOS + SCAN + EOI)
    assert cleaned.startswith(b"\xff\xd8")


@pytest.mark.parametrize("big", [False, True])
@pytest.mark.parametrize("orientation", [3, 6, 8])
def test_jpeg_keeps_only_the_orientation_so_portrait_photos_stay_upright(
    orientation: int, big: bool
) -> None:
    cleaned = strip_jpeg(jpeg(JFIF, exif_segment(orientation, big=big)))

    start = cleaned.index(b"\xff\xe1")
    (length,) = struct.unpack_from(">H", cleaned, start + 2)
    block = cleaned[start + 4 : start + 2 + length]
    assert _orientation(block) == orientation
    assert length < 40  # the number and nothing else
    assert GPS_TEXT not in cleaned and SERIAL not in cleaned
    # Placed straight after the JFIF header, where readers expect it.
    assert cleaned.index(JFIF) + len(JFIF) == start


def test_jpeg_with_default_orientation_keeps_no_exif_at_all() -> None:
    assert b"Exif" not in strip_jpeg(jpeg(JFIF, exif_segment(1)))
    assert b"Exif" not in strip_jpeg(jpeg(JFIF, exif_segment(None)))


def test_jpeg_with_a_nonsense_orientation_is_not_trusted() -> None:
    assert b"Exif" not in strip_jpeg(jpeg(JFIF, exif_segment(99)))


def test_jpeg_cleaning_is_idempotent() -> None:
    once = strip_jpeg(jpeg(JFIF, exif_segment(6), XMP, COMMENT))
    assert strip_jpeg(once) == once


def test_jpeg_tolerates_fill_bytes_between_markers() -> None:
    original = (
        b"\xff\xd8"
        + JFIF
        + b"\xff\xff\xff"
        + exif_segment(None)[0:0]
        + XMP
        + DQT
        + SOF
        + DHT
        + SOS
        + SCAN
        + EOI
    )
    assert GPS_TEXT not in strip_jpeg(original)


@pytest.mark.parametrize(
    "damaged",
    [
        b"\xff\xd8",  # nothing after the start
        b"\xff\xd8" + JFIF,  # ends before any image data
        b"\xff\xd8" + JFIF + b"\xff\xd9",  # a scan-less image
        b"\xff\xd8" + b"\xff\xe1\x00\x40" + b"short",  # segment longer than the file
        b"\xff\xd8" + b"\xff\xe1\x00\x01" + b"xx",  # impossible length
        b"\xff\xd8" + b"garbage" * 8,  # not a marker
        b"\xff\xd8" + b"\xff\x00" + b"x" * 8,  # stuffed zero where a marker should be
    ],
)
def test_jpeg_with_a_broken_structure_is_refused(damaged: bytes) -> None:
    with pytest.raises(ImageMetadataError):
        strip_jpeg(damaged)


def test_a_truncated_scan_is_fine_because_the_headers_are_intact() -> None:
    truncated = b"\xff\xd8" + JFIF + XMP + DQT + SOF + DHT + SOS + SCAN[:3]
    cleaned = strip_jpeg(truncated)
    assert GPS_TEXT not in cleaned and cleaned.endswith(SOS + SCAN[:3])


def test_exif_parsing_never_raises_on_hostile_input() -> None:
    for blob in (
        b"",
        b"Exif\x00\x00",
        b"Exif\x00\x00II*\x00\xff\xff\xff\xff",
        b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\xff\xff",
    ):
        assert _orientation(blob) is None


# --- PNG ----------------------------------------------------------------------------------------
def test_png_loses_text_exif_time_and_unknown_chunks() -> None:
    original = (
        PNG_SIG
        + IHDR
        + png_chunk(b"tEXt", b"Comment\x00" + GPS_TEXT)
        + png_chunk(b"eXIf", tiff(None))
        + png_chunk(b"tIME", bytes(7))
        + png_chunk(b"zTXt", b"k\x00\x00" + GPS_TEXT)
        + png_chunk(b"prVt", SERIAL)
        + IDAT
        + IEND
    )
    cleaned = strip_png(original)
    assert cleaned == PNG_SIG + IHDR + IDAT + IEND
    for secret in (GPS_TEXT, SERIAL):
        assert secret not in cleaned


def test_png_keeps_colour_and_animation_chunks() -> None:
    kept = [
        png_chunk(b"PLTE", bytes(6)),
        png_chunk(b"tRNS", b"\x00"),
        png_chunk(b"gAMA", bytes(4)),
        png_chunk(b"sRGB", b"\x00"),
        png_chunk(b"iCCP", b"p\x00\x00data"),
        png_chunk(b"pHYs", bytes(9)),
        png_chunk(b"acTL", bytes(8)),
        png_chunk(b"fcTL", bytes(26)),
        png_chunk(b"fdAT", bytes(8)),
    ]
    original = PNG_SIG + IHDR + b"".join(kept) + IDAT + IEND
    assert strip_png(original) == original


def test_a_png_with_no_metadata_is_unchanged_and_trailing_bytes_are_dropped() -> None:
    plain = PNG_SIG + IHDR + IDAT + IEND
    assert strip_png(plain) == plain
    assert strip_png(plain + b"appended " + GPS_TEXT) == plain


@pytest.mark.parametrize(
    "damaged",
    [
        PNG_SIG,  # no chunks
        PNG_SIG + IHDR + IDAT,  # no IEND
        PNG_SIG + IHDR + b"\x00\x00\xff\xffIDAT",  # chunk longer than the file
        PNG_SIG + IHDR + b"\x00\x00",  # truncated header
        b"not a png at all",
    ],
)
def test_png_with_a_broken_structure_is_refused(damaged: bytes) -> None:
    with pytest.raises(ImageMetadataError):
        strip_png(damaged)


# --- WebP ------------------------------------------------------------------------------------------
def test_webp_loses_exif_and_xmp_and_stays_well_formed() -> None:
    vp8x = webp_chunk(b"VP8X", bytes([0x08 | 0x04 | 0x20]) + bytes(9))
    original = webp(
        vp8x,
        webp_chunk(b"ICCP", b"profile"),
        webp_chunk(b"VP8 ", b"\x01" * 7),
        webp_chunk(b"EXIF", tiff(None)),
        webp_chunk(b"XMP ", GPS_TEXT),
    )
    cleaned = strip_webp(original)

    for secret in (GPS_TEXT, SERIAL, b"EXIF", b"XMP "):
        assert secret not in cleaned
    assert b"ICCP" in cleaned and b"VP8 " in cleaned
    assert cleaned[:4] == b"RIFF" and cleaned[8:12] == b"WEBP"
    assert struct.unpack_from("<I", cleaned, 4)[0] == len(cleaned) - 8
    # The feature flags no longer promise metadata that is not there (0x20 = ICC stays).
    flags = cleaned[cleaned.index(b"VP8X") + 8]
    assert flags & 0x08 == 0 and flags & 0x04 == 0 and flags & 0x20 == 0x20


def test_a_webp_with_no_metadata_is_unchanged() -> None:
    plain = webp(webp_chunk(b"VP8 ", b"\x02" * 8))
    assert strip_webp(plain) == plain


def test_webp_cleaning_is_idempotent() -> None:
    once = strip_webp(
        webp(
            webp_chunk(b"VP8X", bytes(10)),
            webp_chunk(b"EXIF", tiff(None)),
            webp_chunk(b"VP8 ", b"\x01" * 6),
        )
    )
    assert strip_webp(once) == once


@pytest.mark.parametrize(
    "damaged",
    [
        b"RIFF\x04\x00\x00\x00WEBP"
        + b"VP8 \xff\xff\x00\x00"
        + b"x",  # chunk past the end
        b"RIFF\x04\x00\x00\x00WEBP" + b"VP8",  # truncated chunk header
        b"RIFF\x04\x00\x00\x00WAVE",  # not WebP
        b"short",
    ],
)
def test_webp_with_a_broken_structure_is_refused(damaged: bytes) -> None:
    with pytest.raises(ImageMetadataError):
        strip_webp(damaged)


# --- dispatch -------------------------------------------------------------------------------------------
def test_dispatch_by_content_type() -> None:
    assert strip_metadata(jpeg(JFIF, XMP), "image/jpeg") == strip_jpeg(jpeg(JFIF, XMP))
    assert strip_metadata(PNG_SIG + IHDR + IDAT + IEND, "image/png").startswith(PNG_SIG)
    assert strip_metadata(
        webp(webp_chunk(b"VP8 ", b"\x01" * 4)), "image/webp"
    ).startswith(b"RIFF")


def test_an_unsupported_type_is_an_error_not_a_pass_through() -> None:
    """A privacy control that silently returns its input would hide a gap."""
    with pytest.raises(ImageMetadataError):
        strip_metadata(b"GIF89a....", "image/gif")
