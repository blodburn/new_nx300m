#!/usr/bin/env python3
"""Synthetic-only probe/report/reference tests. No physical NX300M is touched."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

import nx300m_fw114_installed_elf_identity_gate as gate

SCRIPT = Path(__file__).resolve().parents[1] / (
    "scripts/nx300m_fw114_installed_elf_fingerprint.sh"
)


def fake_arm_shared_elf(role: str) -> bytes:
    elf = bytearray(256)
    elf[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<H", elf, 16, 3)  # ET_DYN
    struct.pack_into("<H", elf, 18, 40) # ARM
    role_data = role.encode("ascii")
    elf[64:64 + len(role_data)] = role_data
    return bytes(elf)


class InstalledLibraryIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.camera = self.root / "camera"
        self.reference = self.root / "reference"
        self.camera.mkdir()
        self.reference.mkdir()
        for role, filename in gate.LIBRARIES.items():
            payload = fake_arm_shared_elf(role)
            (self.camera / filename).write_bytes(payload)
            (self.reference / filename).write_bytes(payload)

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, location=None):
        result = subprocess.run(
            ["sh", str(SCRIPT), str(location or self.camera)],
            capture_output=True, text=True, check=False, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertLess(len(result.stdout), gate.REPORT_MAX_BYTES)
        return result.stdout

    def test_four_exact_reference_bytes_without_device_claim(self):
        old = {
            (d.name, p.name): p.read_bytes()
            for d in (self.camera, self.reference)
            for p in d.iterdir()
        }
        report = self.capture()
        out = gate.inspect(report, self.reference)
        self.assertEqual(out["comparison"], "MATCHED_REFERENCE_BYTES")
        self.assertTrue(all(out["files_matching_reference"].values()))
        self.assertTrue(out["all_four_installed_files_observed"])
        self.assertFalse(out["manufacturer_firmware_authenticated"])
        self.assertFalse(out["actual_camera_device_identity_authenticated"])
        self.assertFalse(out["native_ycc420_layout_verified"])
        self.assertFalse(out["dma_ownership_and_cache_coherency_verified"])
        self.assertFalse(out["camera_firmware_flash_permitted"])
        self.assertFalse(out["unofficial_sysmmap_reference_matches_prior_study_sha"])
        self.assertNotIn(str(self.camera), report)
        self.assertNotIn("pid=", report)
        self.assertNotIn("serial", report)
        after = {
            (d.name, p.name): p.read_bytes()
            for d in (self.camera, self.reference)
            for p in d.iterdir()
        }
        self.assertEqual(old, after)

    def test_changed_installed_elf_fails_comparison(self):
        report = self.capture()
        name = gate.LIBRARIES["capture"]
        (self.camera / name).write_bytes(fake_arm_shared_elf("other"))
        unchanged = gate.inspect(report, self.reference)
        self.assertEqual(unchanged["comparison"], "MATCHED_REFERENCE_BYTES")
        new_report = self.capture()
        result = gate.inspect(new_report, self.reference)
        self.assertEqual(result["comparison"], "DIFFERENT_BYTES")
        self.assertFalse(result["files_matching_reference"]["capture"])

    def test_missing_installed_elf_never_promotes_to_complete(self):
        (self.camera / gate.LIBRARIES["sif"]).unlink()
        report = self.capture()
        parsed = gate.parse_report(report)
        self.assertEqual(parsed["sif_sha256"], "unknown")
        self.assertEqual(parsed["sif_bytes"], "unknown")
        self.assertEqual(parsed["all_four_files_read"], "no")
        self.assertEqual(gate.inspect(report, self.reference)["comparison"],
                         "INCOMPLETE")

    def test_installed_symlink_is_not_hashed(self):
        target = self.camera / gate.LIBRARIES["sif"]
        target.unlink()
        target.symlink_to(self.camera / gate.LIBRARIES["photo"])
        parsed = gate.parse_report(self.capture())
        self.assertEqual(parsed["sif_sha256"], "unknown")

    def test_reference_symlink_rejected(self):
        target = self.reference / gate.LIBRARIES["photo"]
        target.unlink()
        target.symlink_to(self.reference / gate.LIBRARIES["sif"])
        with self.assertRaisesRegex(ValueError, "symlinks"):
            gate.inspect(self.capture(), self.reference)

    def test_reference_non_arm32_rejected(self):
        (self.reference / gate.LIBRARIES["photo"]).write_bytes(b"x" * 256)
        with self.assertRaisesRegex(ValueError, "ARM"):
            gate.inspect(self.capture(), self.reference)

    def test_exact_report_syntax_rejects_false_go_and_injection(self):
        report = self.capture()
        for modified in (
            report.replace("firmware_flash_permitted=no",
                           "firmware_flash_permitted=yes"),
            report.replace("probe_scope=read_only_installed_elf_files",
                           "probe_scope=firmware_writable"),
            report + "device_serial=secret\n",
            report + "photo_bytes=256\n",
            report.replace("all_four_files_read=yes",
                           "all_four_files_read=no"),
            report.replace("photo_bytes=256",
                           "photo_bytes=257"),
            report.replace("photo_sha256=",
                           "photo_sha256=z"),
        ):
            with self.subTest(start=modified[:50]):
                with self.assertRaises(ValueError):
                    # One size mutation is still syntactically valid but
                    # must not match the independently hashed reference.
                    if "photo_bytes=257" in modified:
                        v = gate.inspect(modified, self.reference)
                        self.assertEqual(v["comparison"], "DIFFERENT_BYTES")
                    else:
                        gate.parse_report(modified)

    def test_cli_0_match_3_mismatch_2_invalid(self):
        report = self.root / "report.txt"
        report.write_text(self.capture())
        command = [
            "--report", str(report),
            "--reference-libdir", str(self.reference),
        ]
        self.assertEqual(gate.main(command), 0)
        (self.reference / gate.LIBRARIES["sif"]).write_bytes(
            fake_arm_shared_elf("different")
        )
        self.assertEqual(gate.main(command), 3)
        report.write_text("malformed")
        self.assertEqual(gate.main(command), 2)

    def test_unprivileged_shell_help_and_invalid_directory(self):
        result = subprocess.run(
            ["sh", str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(result.returncode, 0)
        result = subprocess.run(
            ["sh", str(SCRIPT), "relative"],
            capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(result.returncode, 2)

    def test_report_path_symlink_rejected(self):
        original = self.root / "report.txt"
        original.write_text(self.capture())
        link = self.root / "report-link"
        link.symlink_to(original)
        self.assertEqual(gate.main([
            "--report", str(link),
            "--reference-libdir", str(self.reference)]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
