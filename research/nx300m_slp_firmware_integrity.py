#!/usr/bin/env python3
"""Read-only NX300M SLP firmware BIN/ZIP integrity check (NO FLASH).

Examines a supplied local BIN or a single firmware member of a ZIP without
extracting to disk. Verifies SLP\0 metadata, model/version, contiguous image
headers, all five image JAMCRC values, pcache JAMCRC, member ZIP CRC,
stream length, and SHA-256. NEVER executes vendor code, requests camera
access, updates firmware, or certifies a mirror's chain of custody.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
import zipfile
import zlib

MAX_IMAGE_BYTES = 512 * 1024 * 1024
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 64
HEADER_BYTES = 144
CHUNK = 1024 * 1024

def filename_is_safe(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        return False
    path = PurePosixPath(name)
    return not any(part in (".", "..") for part in name.split("/")) and path.name != ""

def fields(data: bytes) -> dict:
    if len(data) != HEADER_BYTES or data[:4] != b"SLP\x00":
        raise ValueError("Not an NX300M SLP v1 firmware header")
    def ascii_field(part: bytes) -> str:
        result = part.partition(b"\0")[0]
        if not result or any(c < 32 or c > 126 for c in result):
            raise ValueError("Invalid SLP ASCII metadata")
        return result.decode("ascii")
    version = ascii_field(data[4:12])
    model = ascii_field(data[12:28])
    release = ascii_field(data[28:44])
    if model != "NX300M" or not data[44] == 1:
        raise ValueError("Wrong camera model or unsupported SLP pcache format")
    pcache_header_offset = struct.unpack_from("<I", data, 45)[0]
    segments = []
    expected_offset = HEADER_BYTES
    for i in range(5):
        length, claimed_crc, offset, magic = struct.unpack_from(
            "<IIII", data, 64 + i * 16)
        if not length or offset != expected_offset:
            raise ValueError("Noncontiguous or empty SLP image segment")
        expected_offset += length
        if expected_offset > MAX_IMAGE_BYTES:
            raise ValueError("Declared SLP image too large")
        segments.append({
            "index": i, "length": length, "offset": offset,
            "claimed_jamcrc": f"{claimed_crc:08x}",
            "magic": f"{magic:08x}"
        })
    if pcache_header_offset != expected_offset:
        raise ValueError("SLP pcache offset mismatches five image segments")
    return {
        "version_from_binary": version,
        "model_from_binary": model,
        "release_from_binary": release,
        "pcache_header_offset": pcache_header_offset,
        "segments": segments,
    }

def validate_stream(reader, declared_length: int, *, expected_version: str) -> dict:
    if declared_length < HEADER_BYTES + 16 or declared_length > MAX_IMAGE_BYTES:
        raise ValueError("BIN length outside allowed range")
    digest = hashlib.sha256()
    def read_exact(n: int) -> bytes:
        content = reader.read(n)
        if len(content) != n:
            raise ValueError("Truncated SLP payload")
        digest.update(content)
        return content
    header = read_exact(HEADER_BYTES)
    evidence = fields(header)
    evidence["expected_version"] = expected_version
    evidence["version_matches_expected"] = (
        evidence["version_from_binary"] == expected_version)
    if not evidence["version_matches_expected"]:
        raise ValueError("Internal SLP version does not match required version")
    def segment_hash(length: int, claim_hex: str) -> tuple[str, bool]:
        remaining = length
        accumulator = 0
        while remaining:
            piece = read_exact(min(remaining, CHUNK))
            accumulator = zlib.crc32(piece, accumulator)
            remaining -= len(piece)
        value = (accumulator ^ 0xffffffff) & 0xffffffff
        actual = f"{value:08x}"
        return actual, actual == claim_hex
    for segment in evidence["segments"]:
        value, ok = segment_hash(segment["length"], segment["claimed_jamcrc"])
        segment["computed_jamcrc"] = value
        segment["jamcrc_ok"] = ok
        if not ok:
            raise ValueError(f"SLP image {segment['index']} JAMCRC mismatch")
    pcache_header = read_exact(16)
    size, crc, start, magic = struct.unpack("<IIII", pcache_header)
    if (start != evidence["pcache_header_offset"] + 16 or
        start + size != declared_length or not size or size > MAX_IMAGE_BYTES):
        raise ValueError("pcache declared span does not match firmware")
    pcache = {
        "offset": start,
        "length": size,
        "claimed_jamcrc": f"{crc:08x}",
        "magic": f"{magic:08x}",
    }
    actual, ok = segment_hash(size, pcache["claimed_jamcrc"])
    pcache["computed_jamcrc"] = actual
    pcache["jamcrc_ok"] = ok
    if not ok:
        raise ValueError("pcache JAMCRC mismatch")
    if reader.read(1) != b"":
        raise ValueError("Unexpected trailing data after pcache")
    evidence["pcache"] = pcache
    evidence["decoded_length"] = declared_length
    evidence["decoded_sha256"] = digest.hexdigest()
    evidence["all_jamcrc_ok"] = True
    evidence["camera_flash_safe"] = False
    evidence["manufacturer_authenticity_proven"] = False
    evidence["picture_wizard_abi_114_verified"] = False
    return evidence

def inspect(path: Path, *, expected_version: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Input must be a real, non-symlink local file")
    if path.stat().st_size > MAX_ZIP_BYTES or path.stat().st_size == 0:
        raise ValueError("File outside allowed archive size")
    extension = path.suffix.lower()
    if extension == ".bin":
        with path.open("rb") as f:
            evidence = validate_stream(f, path.stat().st_size,
                                       expected_version=expected_version)
        evidence["source_kind"] = "local_bin"
    elif extension == ".zip":
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Too many ZIP entries")
            if any(not filename_is_safe(x.filename) for x in entries):
                raise ValueError("ZIP contains unsafe path")
            members = [x for x in entries
                       if not x.is_dir() and x.filename.lower().endswith(".bin")]
            if len(members) != 1:
                raise ValueError("ZIP must contain exactly one .bin firmware member")
            member = members[0]
            if ((member.flag_bits & 1) or member.file_size > MAX_IMAGE_BYTES or
                member.file_size <= HEADER_BYTES + 16 or
                member.compress_size == 0 or
                member.file_size > member.compress_size * 200):
                raise ValueError("Encrypted, oversized or suspicious ZIP firmware member")
            mode = (member.external_attr >> 16) & 0xffff
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("ZIP firmware member must be a regular file")
            with archive.open(member, "r") as reader:
                evidence = validate_stream(reader, member.file_size,
                                           expected_version=expected_version)
            evidence["source_kind"] = "local_zip"
            evidence["zip_member"] = member.filename
    else:
        raise ValueError("Expected a .bin or .zip input")
    evidence["archive_basename"] = path.name
    evidence["source_chain_of_custody_verified"] = False
    return evidence

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="existing local BIN or ZIP; never flashes or extracts files")
    parser.add_argument("--expect-version", required=True,
                        help="exact internal header version, e.g. 1.14")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.input, expected_version=args.expect_version)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, EOFError,
            RuntimeError, zlib.error) as exc:
        print(f"FIRMWARE_REJECTED: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
