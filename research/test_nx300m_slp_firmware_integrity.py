#!/usr/bin/env python3
"""Tests with synthetic firmware only. No proprietary firmware is distributed."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import stat
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

module = Path(__file__).with_name("nx300m_slp_firmware_integrity.py")
spec = importlib.util.spec_from_file_location("nx_slp_integrity", module)
assert spec and spec.loader
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

def jamcrc(payload: bytes) -> int:
    return zlib.crc32(payload) ^ 0xffffffff

def fixture(*, version: str = "1.14", model: str = "NX300M") -> bytes:
    content = bytearray(144)
    content[:4] = b"SLP\x00"
    content[4:12] = version.encode("ascii").ljust(8,b"\0")
    content[12:28] = model.encode("ascii").ljust(16,b"\0")
    content[28:44] = b"NX300MGLUANL1".ljust(16,b"\0")
    content[44] = 1
    offset = 144
    parts = []
    for i in range(5):
        payload = bytes((j * (i+3) + i * 17) % 256 for j in range(61 + i*23))
        struct.pack_into("<IIII",content,64+i*16,
                         len(payload),jamcrc(payload),offset,0xffffffff >> i)
        offset+=len(payload)
        parts.append(payload)
    struct.pack_into("<I",content,45,offset)
    for p in parts:content+=p
    pcache=b"NX300M TEST PCACHE ONLY NOT CAMERA REAL FILES"+bytes(range(12))
    header=struct.pack("<IIII",len(pcache),jamcrc(pcache),
                       offset+16,0x32100fff)
    return bytes(content)+header+pcache

class IntegrityTests(unittest.TestCase):
    def test_raw_model_version_and_all_six_crcs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"NX300M_FW_v1.14.bin"
            p.write_bytes(fixture())
            before=p.read_bytes()
            report=inspector.inspect(p,expected_version="1.14")
            self.assertEqual(report["version_from_binary"],"1.14")
            self.assertEqual(report["model_from_binary"],"NX300M")
            self.assertEqual(len(report["segments"]),5)
            self.assertTrue(all(x["jamcrc_ok"] for x in report["segments"]))
            self.assertTrue(report["pcache"]["jamcrc_ok"])
            self.assertFalse(report["manufacturer_authenticity_proven"])
            self.assertFalse(report["camera_flash_safe"])
            self.assertEqual(before,p.read_bytes())

    def test_zip_stored_and_deflated_both_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=fixture()
            for compression in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                p=Path(tmp)/(f"firmware_{compression}.zip")
                with zipfile.ZipFile(p,"w") as z:
                    z.writestr("NX300M_FW_v1.14.bin",data,compress_type=compression)
                report=inspector.inspect(p,expected_version="1.14")
                self.assertEqual(report["decoded_length"],len(data))
                self.assertEqual(report["source_kind"],"local_zip")
                self.assertEqual(report["zip_member"],"NX300M_FW_v1.14.bin")

    def test_wrong_declared_version_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"NX300M_FW_v1.14.bin"
            p.write_bytes(fixture(version="1.15"))
            with self.assertRaisesRegex(ValueError,"version"):
                inspector.inspect(p,expected_version="1.14")

    def test_wrong_model_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.bin"
            p.write_bytes(fixture(model="NX300"))
            with self.assertRaisesRegex(ValueError,"model"):
                inspector.inspect(p,expected_version="1.14")

    def test_payload_corruption_detected_by_jamcrc(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.bin"
            data=bytearray(fixture())
            data[165]^=0x1
            p.write_bytes(data)
            with self.assertRaisesRegex(ValueError,"JAMCRC"):
                inspector.inspect(p,expected_version="1.14")

    def test_bad_offsets_and_trailing_data_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.bin"
            data=bytearray(fixture())
            struct.pack_into("<I",data,64+8,145)
            p.write_bytes(data)
            with self.assertRaisesRegex(ValueError,"Noncontiguous"):
                inspector.inspect(p,expected_version="1.14")
            p.write_bytes(fixture()+b"extra")
            with self.assertRaisesRegex(ValueError,"span"):
                inspector.inspect(p,expected_version="1.14")

    def test_zip_traversal_and_multiple_bin_members_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bad.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("../NX300M_FW_v1.14.bin",fixture())
            with self.assertRaisesRegex(ValueError,"unsafe path"):
                inspector.inspect(p,expected_version="1.14")
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("a.bin",fixture())
                z.writestr("b.bin",fixture())
            with self.assertRaisesRegex(ValueError,"exactly one"):
                inspector.inspect(p,expected_version="1.14")

    def test_truncation_symlink_and_bad_extension_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.bin"
            p.write_bytes(fixture()[:-2])
            with self.assertRaisesRegex(ValueError,"span"):
                inspector.inspect(p,expected_version="1.14")
            symlink=Path(tmp)/"link.bin"
            symlink.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"non-symlink"):
                inspector.inspect(symlink,expected_version="1.14")
            other=Path(tmp)/"other.xyz"
            other.write_bytes(fixture())
            with self.assertRaisesRegex(ValueError,"Expected a .bin or .zip"):
                inspector.inspect(other,expected_version="1.14")

    def test_cli_errors_do_not_expose_raw_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.bin"
            p.write_bytes(fixture())
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status=inspector.main(["--input",str(p),"--expect-version","1.14"])
            self.assertEqual(status,0)
            r=json.loads(stdout.getvalue())
            self.assertIn("decoded_sha256",r)
            self.assertNotIn("firmware_raw_bytes",r)
            self.assertFalse(r["source_chain_of_custody_verified"])

    def test_external_archive_and_decoded_bin_hashes_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = fixture()
            p = Path(tmp) / "NX300M_FW_v1.14.zip"
            with zipfile.ZipFile(p, "w") as archive:
                archive.writestr("firmware/nx300m.bin", data)
            archive_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            bin_sha = hashlib.sha256(data).hexdigest()
            report = inspector.inspect(
                p, expected_version="1.14",
                expected_archive_sha256=archive_sha.upper(),
                expected_bin_sha256=bin_sha)
            self.assertEqual(report["archive_sha256"], archive_sha)
            self.assertTrue(report["archive_fingerprint_matches_expected"])
            self.assertTrue(report["bin_fingerprint_matches_expected"])
            self.assertFalse(report["manufacturer_authenticity_proven"])
            self.assertFalse(report["camera_flash_safe"])
            with self.assertRaisesRegex(ValueError, "Archive SHA-256"):
                inspector.inspect(p, expected_version="1.14",
                                  expected_archive_sha256="0" * 64)
            with self.assertRaisesRegex(ValueError, "Decoded BIN SHA-256"):
                inspector.inspect(p, expected_version="1.14",
                                  expected_bin_sha256="0" * 64)
            with self.assertRaisesRegex(ValueError, "64 hex digits"):
                inspector.inspect(p, expected_version="1.14",
                                  expected_archive_sha256="abcd")

    def test_zip_duplicate_normalized_paths_and_other_symlinks_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("NX300M.BIN", fixture())
                z.writestr("nx300m.bin", fixture())
            with self.assertRaisesRegex(ValueError, "duplicate normalized"):
                inspector.inspect(p, expected_version="1.14")
            link = zipfile.ZipInfo("link.txt")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("NX300M.bin", fixture())
                z.writestr(link, b"NX300M.bin")
            with self.assertRaisesRegex(ValueError, "symlink"):
                inspector.inspect(p, expected_version="1.14")

    def test_zip_unsafe_windows_path_and_other_member_bomb_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("NX300M.bin", fixture())
                z.writestr("C:/evil.txt", b"bad")
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                inspector.inspect(p, expected_version="1.14")
            with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("NX300M.bin", fixture())
                z.writestr("other.dat", b"0" * (1 << 20))
            with self.assertRaisesRegex(ValueError, "compression ratio"):
                inspector.inspect(p, expected_version="1.14")

    def test_file_change_during_scan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "image.bin"
            p.write_bytes(fixture())
            old_hash = inspector.sha256_reader
            def change_mtime_after_hash(reader):
                digest = old_hash(reader)
                st = p.stat()
                os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
                return digest
            with mock.patch.object(inspector, "sha256_reader",
                                   side_effect=change_mtime_after_hash):
                with self.assertRaisesRegex(ValueError, "changed during validation"):
                    inspector.inspect(p, expected_version="1.14")

if __name__=="__main__":
    unittest.main(verbosity=2)
