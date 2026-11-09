#!/usr/bin/env python3
"""Offline gate for an owner-operated, read-only NX300M installed-ELF report.

Compare SHA256 hashes of four fixed installed camera libraries against an
explicitly selected, local, independently owned ELF reference directory.
No camera access, device code, native library execution, firmware mutation,
runtime memory reading, or manufacturer authenticity assertion occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

HEADER = "NX300M_INSTALLED_CAMERA_ELF_SHA_V1"
LIBRARIES = {
    "photo": "libmm-photo.so",
    "sif": "libsif.so",
    "capture": "libcapture-fw-slpcam-nx300.so",
    "sysmmap": "libsys-mmap-manager.so",
}
REPORT_MAX_BYTES = 4096
ELF_MAX_BYTES = 64 * 1024 * 1024
KNOWN_UNOFFICIAL_SYSMAP_SHA = (
    "118a0d77927bfca7576458d86284889143ece1c13578edc96a480911faa5bea9"
)
SAFE_LINE = re.compile(r"([a-z0-9_]+)=([a-z0-9_]+)\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,8})\Z")
NEGATIVE = (
    "manufacturer_firmware_authenticated",
    "camera_binary_runtime_binding_verified",
    "live_ycc420_layout_verified",
    "dma_buffer_ownership_verified",
    "firmware_flash_permitted",
    "firmware_write_performed",
)


def parse_report(report: str) -> dict:
    if len(report.encode("utf-8")) > REPORT_MAX_BYTES or (
        "\r" in report or "\0" in report
    ):
        raise ValueError("Unbounded or invalid installed-ELF report")
    lines = report.splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError("Wrong read-only installed-ELF report header")
    expected = {"probe_scope", "all_four_files_read", *NEGATIVE}
    for role in LIBRARIES:
        expected.update((f"{role}_sha256", f"{role}_bytes"))
    result: dict[str, str] = {}
    for line in lines[1:]:
        pair = SAFE_LINE.fullmatch(line)
        if not pair:
            raise ValueError("Invalid camera report field syntax")
        key, value = pair.groups()
        if key not in expected or key in result:
            raise ValueError("Unexpected or duplicate camera report field")
        result[key] = value
    if set(result) != expected:
        raise ValueError("Missing installed-ELF report field")
    if result["probe_scope"] != "read_only_installed_elf_files":
        raise ValueError("Not the read-only file-hash probe")
    if any(result[key] != "no" for key in NEGATIVE):
        raise ValueError("Unverified native camera or installation claim")
    all_present = True
    for role in LIBRARIES:
        digest = result[f"{role}_sha256"]
        bytes_text = result[f"{role}_bytes"]
        if digest == "unknown":
            if bytes_text != "unknown":
                raise ValueError("Unknown hash has a numeric file length")
            all_present = False
            continue
        if not DIGEST.fullmatch(digest) or not INTEGER.fullmatch(bytes_text):
            raise ValueError("Invalid installed-ELF digest/size")
        if not 52 <= int(bytes_text) <= ELF_MAX_BYTES:
            raise ValueError("Unexpected installed ELF byte count")
    status = "yes" if all_present else "no"
    if result["all_four_files_read"] != status:
        raise ValueError("Observed file-count flag is inconsistent")
    return result


def hash_reference_elf(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("Reference ELF symlinks are not permitted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not (
            52 <= before.st_size <= ELF_MAX_BYTES
        ):
            raise ValueError("Reference camera ELF must be a bounded regular file")
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb", closefd=True) as stream:
            header = stream.read(52)
            # ELF32, little endian, ARM e_machine=40, ET_DYN=3.
            if (header[:6] != b"\x7fELF\x01\x01" or
                struct.unpack_from("<H", header, 16)[0] != 3 or
                struct.unpack_from("<H", header, 18)[0] != 40):
                raise ValueError("Reference is not a 32-bit ARM shared ELF")
            digest.update(header)
            for piece in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(piece)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field)
               for field in fields):
            raise ValueError("Reference library changed during reading")
        return {"sha256": digest.hexdigest(), "bytes": before.st_size}
    finally:
        os.close(fd)


def inspect(report: str, reference_directory: Path) -> dict:
    source = parse_report(report)
    if reference_directory.is_symlink() or not reference_directory.is_dir():
        raise ValueError("Reference directory missing or symlinked")
    offline = {
        role: hash_reference_elf(reference_directory / filename)
        for role, filename in LIBRARIES.items()
    }
    matched = {}
    for role in LIBRARIES:
        matched[role] = (
            source[f"{role}_sha256"] == offline[role]["sha256"] and
            source[f"{role}_bytes"] == str(offline[role]["bytes"])
        )
    complete = source["all_four_files_read"] == "yes"
    verdict = (
        "INCOMPLETE" if not complete else
        "MATCHED_REFERENCE_BYTES" if all(matched.values()) else
        "DIFFERENT_BYTES"
    )
    return {
        "scope": "OFFLINE_READ_ONLY_INSTALLED_ELF_COMPARISON",
        "comparison": verdict,
        "files_matching_reference": matched,
        "all_four_installed_files_observed": complete,
        "unofficial_sysmmap_reference_matches_prior_study_sha": (
            offline["sysmmap"]["sha256"] == KNOWN_UNOFFICIAL_SYSMAP_SHA
        ),
        "actual_camera_device_identity_authenticated": False,
        "manufacturer_firmware_authenticated": False,
        "live_capture_buffers_verified": False,
        "native_ycc420_layout_verified": False,
        "dma_ownership_and_cache_coherency_verified": False,
        "camera_firmware_flash_permitted": False,
        "note": (
            "Matching SHA256 proves only bytes equal to the operator-selected "
            "offline reference, not that the report came from an NX300M or "
            "that real DMA or camera firmware installation is safe."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reference-libdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.report.is_symlink() or not args.report.is_file() or (
            args.report.stat().st_size > REPORT_MAX_BYTES
        ):
            raise ValueError("Missing, symlinked or oversized device report")
        report = args.report.read_text(encoding="utf-8")
        result = inspect(report, args.reference_libdir)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["comparison"] == "MATCHED_REFERENCE_BYTES" else 3
    except (ValueError, OSError, UnicodeError) as exc:
        print("NX300M_ELF_IDENTITY_REJECTED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
