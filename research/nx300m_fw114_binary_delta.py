#!/usr/bin/env python3
"""Offline compare NX300M *actual provided* SLP1.14 vs SLP1.15 BIN/ZIP images.

All checks are read-only, rely on nx300m_slp_firmware_integrity for streamed
SLP/JAMCRC, ZIP integrity, decoded SHA-256 and optional trusted fingerprints.
A region-level match/difference is NOT ABI equivalence, vendor authenticity,
recovery capability or permission to flash. No extraction or patching.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile
import zlib

import nx300m_slp_firmware_integrity as slp


def compare(
    fw114: Path,
    reference115: Path,
    *,
    expected_fw114_sha256: str | None = None,
    expected_fw115_sha256: str | None = None,
    expected_fw114_bin_sha256: str | None = None,
) -> dict:
    """Report per-region SHA256 equality; never certify live camera compatibility."""
    if fw114.resolve() == reference115.resolve():
        raise ValueError("1.14 and 1.15 must be separate files")
    target = slp.inspect(
        fw114,
        expected_version="1.14",
        expected_archive_sha256=expected_fw114_sha256,
        expected_bin_sha256=expected_fw114_bin_sha256,
    )
    reference = slp.inspect(
        reference115,
        expected_version="1.15",
        expected_archive_sha256=expected_fw115_sha256,
    )
    if len(target["segments"]) != 5 or len(reference["segments"]) != 5:
        raise ValueError("Unexpected SLP region count")
    regions = []
    for a, b in zip(target["segments"], reference["segments"]):
        if a["index"] != b["index"]:
            raise ValueError("SLP region order changed")
        regions.append({
            "index": a["index"],
            "fw114_bytes": a["length"],
            "fw115_bytes": b["length"],
            "fw114_segment_sha256": a["sha256"],
            "fw115_segment_sha256": b["sha256"],
            "sha256_equal": a["sha256"] == b["sha256"],
            "size_equal": a["length"] == b["length"],
        })
    pcache_a, pcache_b = target["pcache"], reference["pcache"]
    return {
        "mode": "OFFLINE_BOUNDED_READ_ONLY_COMPARISON",
        "target": {
            "model": target["model_from_binary"],
            "internal_version": target["version_from_binary"],
            "filename": target["archive_basename"],
            "source_kind": target["source_kind"],
            "source_sha256": target["archive_sha256"],
            "decoded_bin_sha256": target["decoded_sha256"],
            "declared_bytes": target["decoded_length"],
            "external_archive_hash_matched":
                target["archive_fingerprint_matches_expected"],
            "external_bin_hash_matched": target["bin_fingerprint_matches_expected"],
        },
        "reference": {
            "model": reference["model_from_binary"],
            "internal_version": reference["version_from_binary"],
            "filename": reference["archive_basename"],
            "source_kind": reference["source_kind"],
            "source_sha256": reference["archive_sha256"],
            "decoded_bin_sha256": reference["decoded_sha256"],
            "declared_bytes": reference["decoded_length"],
            "external_archive_hash_matched":
                reference["archive_fingerprint_matches_expected"],
        },
        "images": regions,
        "pcache": {
            "fw114_bytes": pcache_a["length"],
            "fw115_bytes": pcache_b["length"],
            "fw114_sha256": pcache_a["sha256"],
            "fw115_sha256": pcache_b["sha256"],
            "sha256_equal": pcache_a["sha256"] == pcache_b["sha256"],
        },
        "changed_image_count": sum(not x["sha256_equal"] for x in regions),
        "firmware_114_internal_header_and_jamcrc_verified": True,
        "firmware_114_vendored_provenance_verified": False,
        "binary_abi_equivalence_verified": False,
        "safe_original_restore_or_full_brick_recovery_verified": False,
        "native_isp_ycc420_pixel_layout_verified": False,
        "camera_firmware_modification_permitted": False,
        "warning": (
            "CRC and SHA verify only the supplied files. A third-party or modified "
            "binary may retain correct internal checksums. Segment differences "
            "do not reveal actual native function addresses or memory ownership. "
            "Never use old FW1.15 offsets on stock FW1.14 without version-specific "
            "binary disassembly, independent authenticity and physical recovery."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fw114", required=True, type=Path,
                   help="existing local original-candidate FW1.14 BIN/ZIP")
    p.add_argument("--reference115", required=True, type=Path,
                   help="existing local FW1.15 BIN/ZIP, may be modified; not proof")
    p.add_argument("--expect-fw114-archive-sha256",
                   help="independently supplied archive SHA-256, never guessed")
    p.add_argument("--expect-fw114-bin-sha256",
                   help="independently supplied decompressed BIN SHA-256")
    p.add_argument("--expect-fw115-archive-sha256",
                   help="independently supplied SHA-256 for reference")
    a = p.parse_args(argv)
    try:
        print(json.dumps(compare(
            a.fw114, a.reference115,
            expected_fw114_sha256=a.expect_fw114_archive_sha256,
            expected_fw114_bin_sha256=a.expect_fw114_bin_sha256,
            expected_fw115_sha256=a.expect_fw115_archive_sha256,
        ), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, EOFError,
            RuntimeError, zlib.error) as exc:
        print("FIRMWARE_DELTA_REJECTED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
