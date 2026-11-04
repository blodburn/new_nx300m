#!/usr/bin/env python3
"""Read-only, HOST-only JPEG structure + Exif APP1/MakerNote preservation audit.

This verifies byte equality of caller-provided EXIF from two JPEG files.
It NEVER authenticates source-camera provenance, proprietary MakerNote meaning,
Samsung FW1.14 native encoder ABI or actual on-device JPEG capture.
No JPEG entropy decoding is performed. No camera or firmware I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nx300m_jpeg_sof_probe import JPEGHeaderError, probe_bytes

MAX_JPEG = 128 * 1024 * 1024
MAX_IFD_ENTRIES = 256
TYPE_BYTES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def refuse(message: str):
    raise ValueError(message)


def read_private_jpeg(path: Path) -> tuple[bytes, str]:
    if path.is_symlink():
        refuse("JPEG symlink is not allowed")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 16 <= before.st_size <= MAX_JPEG:
            refuse("JPEG must be a bounded regular file")
        data = stream.read(MAX_JPEG + 1)
        after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in fields):
            refuse("JPEG changed during inspection")
        if len(data) != before.st_size:
            refuse("Truncated JPEG read")
    return data, hashlib.sha256(data).hexdigest()


def scan_jpeg(data: bytes) -> dict:
    if not data.startswith(b"\xff\xd8"):
        refuse("Missing JPEG SOI")
    cursor = 2
    exif = []
    app_segments = []
    found_sof = 0
    found_sos = 0
    entropy_bytes = 0
    while cursor < len(data):
        if data[cursor] != 0xFF:
            refuse("Invalid JPEG marker boundary")
        while cursor < len(data) and data[cursor] == 0xFF:
            cursor += 1
        if cursor == len(data):
            refuse("Truncated JPEG marker")
        marker = data[cursor]
        cursor += 1
        if marker in (0xD8, 0xD9, 0x00, 0x01) or 0xD0 <= marker <= 0xD7:
            refuse("Unexpected marker outside image entropy")
        if cursor + 2 > len(data):
            refuse("Truncated JPEG marker length")
        segment_length = int.from_bytes(data[cursor:cursor + 2], "big")
        if segment_length < 2 or cursor + segment_length > len(data):
            refuse("Malformed JPEG segment length")
        payload = data[cursor + 2:cursor + segment_length]
        cursor += segment_length
        if marker == 0xC0:
            found_sof += 1
        elif marker in (0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            refuse("Only host baseline JPEG SOF0 is supported")
        if marker in range(0xE0, 0xF0):
            app_segments.append(f"APP{marker - 0xE0}")
        if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
            exif.append(payload)
        if marker != 0xDA:
            continue
        found_sos += 1
        if found_sof != 1 or found_sos != 1:
            refuse("Missing or repeated baseline JPEG frame/scan")
        # Only a single baseline entropy scan is permitted. Bytes FF00 are
        # stuffed; D0..D7 restart markers are allowed. SOI/APP/SOS in the
        # entropy stream, premature EOF or trailing data all fail closed.
        while cursor < len(data):
            byte = data[cursor]
            cursor += 1
            if byte != 0xFF:
                entropy_bytes += 1
                continue
            while cursor < len(data) and data[cursor] == 0xFF:
                cursor += 1
            if cursor >= len(data):
                refuse("Truncated JPEG entropy marker")
            follow = data[cursor]
            cursor += 1
            if follow == 0x00:
                entropy_bytes += 1
            elif 0xD0 <= follow <= 0xD7:
                continue
            elif follow == 0xD9:
                if cursor != len(data) or entropy_bytes == 0:
                    refuse("JPEG EOI missing, entropy empty or trailing bytes")
                if len(exif) != 1:
                    refuse("Require exactly one Exif APP1 segment")
                try:
                    sof = probe_bytes(data)
                except JPEGHeaderError as exc:
                    raise ValueError("Invalid JPEG SOF") from exc
                if sof["sof_marker"] != "FFC0" or sof["bit_depth"] != 8:
                    refuse("Unexpected JPEG SOF profile")
                return {
                    "sof": sof,
                    "exif_app1": exif[0],
                    "app_segments": app_segments,
                    "entropy_bytes": entropy_bytes,
                }
            else:
                refuse("Unsupported marker inside JPEG entropy")
        refuse("Missing JPEG EOI")
    refuse("No JPEG SOS found")


def extract_makernote(exif_app1: bytes) -> bytes | None:
    if not exif_app1.startswith(b"Exif\x00\x00"):
        refuse("Invalid Exif APP1 prefix")
    tiff = exif_app1[6:]
    if len(tiff) < 14 or tiff[:2] not in (b"II", b"MM"):
        refuse("Invalid TIFF EXIF header")
    byteorder = "little" if tiff[:2] == b"II" else "big"

    def number(offset: int, size: int) -> int:
        if offset < 0 or offset + size > len(tiff):
            refuse("Exif TIFF pointer beyond APP1 data")
        return int.from_bytes(tiff[offset:offset + size], byteorder)

    if number(2, 2) != 42:
        refuse("Invalid TIFF signature")

    visited = set()
    pending = [number(4, 4)]
    notes = []
    while pending:
        base = pending.pop()
        if base in visited:
            refuse("TIFF IFD cycle or duplicate reference")
        visited.add(base)
        if len(visited) > 8 or base < 8:
            refuse("Exceeded IFD traversal bound")
        count = number(base, 2)
        if count > MAX_IFD_ENTRIES:
            refuse("Too many TIFF directory entries")
        end = base + 2 + count * 12
        number(end, 4)  # Require a valid next-IFD pointer field.
        for idx in range(count):
            entry = base + 2 + 12 * idx
            tag = number(entry, 2)
            value_type = number(entry + 2, 2)
            elements = number(entry + 4, 4)
            if tag not in (0x8769, 0x927C):
                continue
            item_size = TYPE_BYTES.get(value_type)
            if not item_size or elements == 0 or elements > MAX_JPEG // item_size:
                refuse("Invalid Exif tag type or size")
            nbytes = elements * item_size
            if nbytes <= 4:
                value = tiff[entry + 8:entry + 8 + nbytes]
            else:
                ptr = number(entry + 8, 4)
                number(ptr, nbytes)
                value = tiff[ptr:ptr + nbytes]
            if tag == 0x8769:
                if value_type != 4 or elements != 1:
                    refuse("Invalid Exif subIFD pointer type")
                pending.append(int.from_bytes(value, byteorder))
            if tag == 0x927C:
                if value_type != 7:
                    refuse("MakerNote must use UNDEFINED Exif type")
                notes.append(value)
        # Do not chase thumbnail IFD1. MakerNote is defined in ExifIFD.
    if len(notes) > 1:
        refuse("Duplicate Exif MakerNote fields")
    return notes[0] if notes else None


def inspect_pair(original_path: Path, film_path: Path,
                 require_makernote: bool = False,
                 expected_width: int | None = None,
                 expected_height: int | None = None) -> dict:
    orig, ohash = read_private_jpeg(original_path)
    film, fhash = read_private_jpeg(film_path)
    a = scan_jpeg(orig)
    b = scan_jpeg(film)
    source = a["sof"]
    output = b["sof"]
    for s in (source, output):
        if s["chroma_subsampling"] != "4:2:0":
            refuse("JPEG output is not host 4:2:0")
        if (expected_width is not None and s["width"] != expected_width) or (
            expected_height is not None and s["height"] != expected_height
        ):
            refuse("Unexpected JPEG dimensions")
    if (source["width"], source["height"]) != (output["width"], output["height"]):
        refuse("JPEG dimensions changed")
    if a["exif_app1"] != b["exif_app1"]:
        refuse("Original Exif APP1 is not byte-identical")
    note = extract_makernote(a["exif_app1"])
    if require_makernote and note is None:
        refuse("Required MakerNote field is missing")
    return {
        "result": "HOST_JPEG_STRUCTURE_AND_APP1_EQUAL",
        "width": source["width"],
        "height": source["height"],
        "sampling": source["chroma_subsampling"],
        "original_sha256": ohash,
        "processed_sha256": fhash,
        "exif_app1_sha256": hashlib.sha256(a["exif_app1"]).hexdigest(),
        "exif_app1_size": len(a["exif_app1"]),
        "makernote_found": note is not None,
        "makernote_sha256": hashlib.sha256(note).hexdigest() if note is not None else None,
        "makernote_size": len(note) if note is not None else 0,
        "app_markers_preserved": a["app_segments"] == b["app_segments"],
        "native_samsung_exif_abi_verified": False,
        "maker_note_semantics_verified": False,
        "real_camera_capture_verified": False,
        "firmware_flash_permitted": False,
        "warning": "Byte-identical APP1 cannot authenticate proprietary MakerNote semantics or camera provenance.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-jpeg", required=True, type=Path)
    p.add_argument("--film-jpeg", required=True, type=Path)
    p.add_argument("--require-makernote", action="store_true")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    args = p.parse_args(argv)
    try:
        r = inspect_pair(args.original_jpeg, args.film_jpeg,
                         args.require_makernote, args.width, args.height)
        print(json.dumps(r, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print("NX300M_JPEG_EXIF_REJECTED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
