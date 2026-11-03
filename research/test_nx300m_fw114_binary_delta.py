#!/usr/bin/env python3
"""Synthetic-only SLP114/115 differential inspection regression suite."""
from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import nx300m_fw114_binary_delta as delta
import nx300m_slp_firmware_integrity as integrity
from test_nx300m_slp_firmware_integrity import fixture, jamcrc


def change_first_segment(data: bytes) -> bytes:
    out = bytearray(data)
    length, _, offset, _ = struct.unpack_from("<IIII", out, 64)
    assert offset == 144 and length > 0
    out[offset] ^= 0x40
    struct.pack_into("<I", out, 68, jamcrc(out[offset:offset+length]))
    return bytes(out)


class DifferentialTests(unittest.TestCase):

    def test_region_sha_matches_independent_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "original_114.bin"
            data = fixture(version="1.14")
            path.write_bytes(data)
            result = integrity.inspect(path, expected_version="1.14")
            self.assertEqual(len(result["segments"]), 5)
            for item in result["segments"]:
                piece = data[item["offset"]:item["offset"]+item["length"]]
                self.assertEqual(item["sha256"], hashlib.sha256(piece).hexdigest())
            p = result["pcache"]
            piece = data[p["offset"]:p["offset"]+p["length"]]
            self.assertEqual(p["sha256"], hashlib.sha256(piece).hexdigest())
            self.assertFalse(result["camera_flash_safe"])

    def test_versions_and_one_changed_image(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "fw114.bin", Path(folder) / "modified115.bin"
            original = fixture(version="1.14")
            modified = change_first_segment(fixture(version="1.15"))
            a.write_bytes(original)
            b.write_bytes(modified)
            result = delta.compare(
                a, b,
                expected_fw114_sha256=hashlib.sha256(original).hexdigest(),
                expected_fw114_bin_sha256=hashlib.sha256(original).hexdigest(),
                expected_fw115_sha256=hashlib.sha256(modified).hexdigest(),
            )
            self.assertTrue(result["firmware_114_internal_header_and_jamcrc_verified"])
            self.assertTrue(result["target"]["external_archive_hash_matched"])
            self.assertTrue(result["target"]["external_bin_hash_matched"])
            self.assertEqual(result["changed_image_count"], 1)
            self.assertFalse(result["images"][0]["sha256_equal"])
            self.assertTrue(all(x["sha256_equal"] for x in result["images"][1:]))
            self.assertTrue(result["pcache"]["sha256_equal"])
            for key in ("firmware_114_vendored_provenance_verified",
                        "binary_abi_equivalence_verified",
                        "safe_original_restore_or_full_brick_recovery_verified",
                        "camera_firmware_modification_permitted"):
                self.assertFalse(result[key])
            self.assertEqual(a.read_bytes(), original)
            self.assertEqual(b.read_bytes(), modified)

    def test_same_payload_not_falsely_approved_for_abi(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.bin", Path(folder) / "b.bin"
            a.write_bytes(fixture(version="1.14"))
            b.write_bytes(fixture(version="1.15"))
            report = delta.compare(a, b)
            self.assertEqual(report["changed_image_count"], 0)
            self.assertFalse(report["binary_abi_equivalence_verified"])
            self.assertFalse(report["camera_firmware_modification_permitted"])

    def test_internal_version_115_cannot_pass_as_fw114(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "NX300M_FW_v1.14.bin", Path(folder) / "fw115.bin"
            a.write_bytes(fixture(version="1.15"))
            b.write_bytes(fixture(version="1.15"))
            with self.assertRaisesRegex(ValueError, "version"):
                delta.compare(a, b)

    def test_reference_114_cannot_pass_as_fw115(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.bin", Path(folder) / "b.bin"
            a.write_bytes(fixture(version="1.14"))
            b.write_bytes(fixture(version="1.14"))
            with self.assertRaisesRegex(ValueError, "version"):
                delta.compare(a, b)

    def test_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "missing114.bin", Path(folder) / "reference115.bin"
            b.write_bytes(fixture(version="1.15"))
            with self.assertRaisesRegex(ValueError, "Input must"):
                delta.compare(a, b)

    def test_identical_paths_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / "fw114.bin"
            a.write_bytes(fixture(version="1.14"))
            with self.assertRaisesRegex(ValueError, "separate"):
                delta.compare(a, a)

    def test_corrupt_crc_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "fw114.bin", Path(folder) / "fw115.bin"
            raw = bytearray(fixture(version="1.14"))
            raw[145] ^= 0xff
            a.write_bytes(raw)
            b.write_bytes(fixture(version="1.15"))
            with self.assertRaisesRegex(ValueError, "JAMCRC"):
                delta.compare(a, b)

    def test_mismatched_independent_target_sha_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "fw114.bin", Path(folder) / "fw115.bin"
            a.write_bytes(fixture(version="1.14"))
            b.write_bytes(fixture(version="1.15"))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                delta.compare(a, b, expected_fw114_sha256="0"*64)

    def test_zip_to_bin_comparison_without_extracting(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "stock114.zip", Path(folder) / "old_reference115.bin"
            original = fixture(version="1.14")
            with zipfile.ZipFile(a, "w") as z:
                z.writestr("NX300M_FW_v1.14.bin", original,
                           compress_type=zipfile.ZIP_DEFLATED)
            b.write_bytes(fixture(version="1.15"))
            result = delta.compare(a, b)
            self.assertEqual(result["target"]["source_kind"], "local_zip")
            self.assertEqual(result["target"]["decoded_bin_sha256"],
                             hashlib.sha256(original).hexdigest())
            self.assertFalse(result["camera_firmware_modification_permitted"])

    def test_cli_no_binary_dump_on_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = delta.main(["--fw114", str(Path(folder)/"missing.bin"),
                                 "--reference115", str(Path(folder)/"absent.bin")])
            self.assertEqual(rc, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("FIRMWARE_DELTA_REJECTED", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
