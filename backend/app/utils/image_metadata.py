"""Remove embedded metadata from uploaded images, without decoding them.

A phone photograph carries more than pixels: EXIF commonly holds the GPS position
it was taken at, the device model and serial number, and a thumbnail that can
outlive any edit. The platform stores these photographs and shows them to anyone
who may open the incident (``docs/SECURITY.md`` section 5), so a citizen who
photographs a scene from their home would otherwise publish their exact position
to every reader of the file — whatever the report form's location privacy says.

Stripping works on the container structure only (JPEG segments, PNG chunks, WebP
RIFF chunks). The image data is copied byte for byte: nothing is re-encoded, so
nothing is lost or degraded and no image library is needed. The functions are
pure: bytes in, bytes out.

The approach is an allow-list — keep what is needed to draw the picture, drop
everything else — so a metadata block this module has never heard of is dropped
rather than kept.

One piece of metadata is deliberately kept in JPEGs: the EXIF *orientation*. Phone
cameras record "rotate this 90 degrees" there rather than rotating the pixels, so
removing it would show a portrait photograph on its side. It is rewritten into a
minimal EXIF block that holds that one number and nothing else. (WebP orientation
is not preserved; see :func:`strip_webp`.)

A file whose structure cannot be walked raises :class:`ImageMetadataError`. The
caller must then refuse the upload: storing an image whose metadata could not be
removed would defeat the purpose.
"""

from __future__ import annotations

import struct

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"


class ImageMetadataError(ValueError):
    """The image's container structure could not be read, so it cannot be cleaned."""


# --- JPEG ---------------------------------------------------------------------------

_SOI = b"\xff\xd8"
_SOS = 0xDA
_EOI = 0xD9
#: Markers with no length field: TEM, SOI, EOI and the restart markers.
_STANDALONE = frozenset({0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)})
_APP0, _APP1, _APP2, _APP14 = 0xE0, 0xE1, 0xE2, 0xEE
_ICC = b"ICC_PROFILE\x00"
_EXIF = b"Exif\x00\x00"
_ORIENTATION_TAG = 0x0112


def _orientation(exif_segment: bytes) -> int | None:
    """The EXIF orientation (1-8) from an APP1 payload, or None. Never raises."""
    if not exif_segment.startswith(_EXIF):
        return None
    tiff = exif_segment[len(_EXIF) :]
    if len(tiff) < 8:
        return None
    if tiff[:2] == b"II":
        endian = "<"
    elif tiff[:2] == b"MM":
        endian = ">"
    else:
        return None
    try:
        (magic,) = struct.unpack_from(f"{endian}H", tiff, 2)
        if magic != 42:
            return None
        (ifd_offset,) = struct.unpack_from(f"{endian}I", tiff, 4)
        (count,) = struct.unpack_from(f"{endian}H", tiff, ifd_offset)
        for index in range(min(count, 512)):
            entry = ifd_offset + 2 + index * 12
            tag, kind, length = struct.unpack_from(f"{endian}HHI", tiff, entry)
            if tag != _ORIENTATION_TAG:
                continue
            if kind != 3 or length != 1:  # SHORT, one value
                return None
            (value,) = struct.unpack_from(f"{endian}H", tiff, entry + 8)
            return value if 1 <= value <= 8 else None
    except struct.error:
        return None
    return None


def _orientation_only_exif(orientation: int) -> bytes:
    """An APP1 segment holding the orientation tag and nothing else."""
    tiff = (
        b"II*\x00"  # little endian, magic 42
        + struct.pack("<I", 8)  # IFD0 immediately after the header
        + struct.pack("<H", 1)  # one entry
        + struct.pack("<HHIHH", _ORIENTATION_TAG, 3, 1, orientation, 0)
        + struct.pack("<I", 0)  # no next IFD
    )
    payload = _EXIF + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def strip_jpeg(content: bytes) -> bytes:
    """Drop EXIF/XMP/IPTC/comments and vendor segments from a JPEG.

    Kept: every segment needed to decode (quantisation and Huffman tables, frame
    header, restart interval, JFIF, the Adobe colour marker) and an ICC colour
    profile. The compressed image data after the scan header is copied untouched.
    """
    if not content.startswith(_SOI):
        raise ImageMetadataError("Not a JPEG.")

    out = bytearray(_SOI)
    orientation: int | None = None
    position = 2
    size = len(content)

    while True:
        # A marker is 0xFF, optionally repeated as fill, then a non-zero code.
        if position >= size or content[position] != 0xFF:
            raise ImageMetadataError("Expected a JPEG marker.")
        while position < size and content[position] == 0xFF:
            position += 1
        if position >= size or content[position] == 0x00:
            raise ImageMetadataError("Malformed JPEG marker.")
        marker = content[position]
        position += 1

        if marker == _EOI:
            # An image with no scan at all: nothing to draw, nothing to keep.
            raise ImageMetadataError("JPEG has no image data.")
        if marker in _STANDALONE:
            out += bytes((0xFF, marker))
            continue

        if position + 2 > size:
            raise ImageMetadataError("Truncated JPEG segment header.")
        (length,) = struct.unpack_from(">H", content, position)
        if length < 2 or position + length > size:
            raise ImageMetadataError("JPEG segment runs past the end of the file.")
        payload = content[position + 2 : position + length]
        segment = bytes((0xFF, marker)) + content[position : position + length]
        position += length

        if marker == _SOS:
            # Entropy-coded data and EOI follow; copy verbatim.
            out += segment + content[position:]
            break

        if marker == _APP1:
            if orientation is None:
                orientation = _orientation(payload)
            continue  # EXIF or XMP: dropped either way
        keep = (
            marker == _APP0
            or marker == _APP14
            or (marker == _APP2 and payload.startswith(_ICC))
            or not (0xE0 <= marker <= 0xEF or marker == 0xFE)  # not APPn / COM
        )
        if keep:
            out += segment

    if orientation is not None and orientation != 1:
        # Straight after SOI (and any JFIF header) is where EXIF conventionally sits.
        exif = _orientation_only_exif(orientation)
        insert_at = 2
        if out[2:4] == b"\xff\xe0":
            (jfif_length,) = struct.unpack_from(">H", out, 4)
            insert_at = 4 + jfif_length
        out[insert_at:insert_at] = exif
    return bytes(out)


# --- PNG ------------------------------------------------------------------------------

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Chunks needed to draw the image (including animated PNG). Everything else —
#: eXIf, tEXt, zTXt, iTXt, tIME and anything unknown — is dropped.
_PNG_KEEP = frozenset(
    {
        b"IHDR",
        b"PLTE",
        b"IDAT",
        b"IEND",
        b"tRNS",
        b"gAMA",
        b"cHRM",
        b"sRGB",
        b"iCCP",
        b"sBIT",
        b"cICP",
        b"bKGD",
        b"hIST",
        b"pHYs",
        b"sPLT",
        b"acTL",
        b"fcTL",
        b"fdAT",
    }
)


def strip_png(content: bytes) -> bytes:
    """Drop text, EXIF and timestamp chunks from a PNG; keep everything that draws it."""
    if not content.startswith(_PNG_SIGNATURE):
        raise ImageMetadataError("Not a PNG.")
    out = bytearray(_PNG_SIGNATURE)
    position = len(_PNG_SIGNATURE)
    size = len(content)
    seen_end = False

    while position < size:
        if position + 8 > size:
            raise ImageMetadataError("Truncated PNG chunk header.")
        (length,) = struct.unpack_from(">I", content, position)
        kind = content[position + 4 : position + 8]
        end = position + 8 + length + 4  # data, then the CRC
        if length > 0x7FFFFFFF or end > size:
            raise ImageMetadataError("PNG chunk runs past the end of the file.")
        if kind in _PNG_KEEP:
            out += content[position:end]
        position = end
        if kind == b"IEND":
            seen_end = True
            break  # bytes after IEND are not part of the image

    if not seen_end:
        raise ImageMetadataError("PNG has no IEND chunk.")
    return bytes(out)


# --- WebP -------------------------------------------------------------------------------

_WEBP_DROP = frozenset({b"EXIF", b"XMP "})
_VP8X_EXIF_FLAG = 0x08
_VP8X_XMP_FLAG = 0x04


def strip_webp(content: bytes) -> bytes:
    """Drop the EXIF and XMP chunks of a WebP and fix the size and feature flags.

    Unlike JPEG, WebP orientation is not preserved: a WebP photograph that relied on
    an EXIF rotation will display unrotated. WebP is rare for camera photographs
    (phones write JPEG), and carrying orientation would need the same rewrite again
    inside a VP8X-flagged container; it is noted here rather than half-built.
    """
    if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ImageMetadataError("Not a WebP.")
    body = bytearray()
    position = 12
    size = len(content)

    while position < size:
        if position + 8 > size:
            raise ImageMetadataError("Truncated WebP chunk header.")
        kind = content[position : position + 4]
        (length,) = struct.unpack_from("<I", content, position + 4)
        padded = length + (length & 1)
        end = position + 8 + padded
        if end > size:
            # Tolerate a missing final pad byte, which some encoders omit.
            if position + 8 + length == size:
                end = size
            else:
                raise ImageMetadataError("WebP chunk runs past the end of the file.")
        if kind not in _WEBP_DROP:
            chunk = bytearray(content[position:end])
            if kind == b"VP8X" and length >= 1:
                chunk[8] &= ~(_VP8X_EXIF_FLAG | _VP8X_XMP_FLAG) & 0xFF
            body += chunk
        position = end

    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + bytes(body)


# --- dispatch --------------------------------------------------------------------------------


def strip_metadata(content: bytes, content_type: str) -> bytes:
    """Return ``content`` with embedded metadata removed.

    ``content_type`` must already have been validated against the file's magic
    bytes. An unsupported type is an error, not a pass-through: this function is a
    privacy control, and returning the input unchanged would hide a gap.
    """
    if content_type == JPEG:
        return strip_jpeg(content)
    if content_type == PNG:
        return strip_png(content)
    if content_type == WEBP:
        return strip_webp(content)
    raise ImageMetadataError(f"No metadata stripper for {content_type!r}.")
