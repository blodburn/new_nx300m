#!/usr/bin/env python3
"""Synthetic, no-real-firmware, no-device regression for SLP/UBI/ELF diff."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib

import nx300m_fw114_native_elf_diff as native
from test_nx300m_slp_firmware_integrity import fixture, jamcrc


def fake_peb(index: int) -> bytes:
    header = bytearray(64)
    header[:4] = b"UBI#"
    header[4] = 1
    struct.pack_into(">Q", header, 8, index)
    struct.pack_into(">II", header, 16, native.VID, native.DATA)
    # Data need not be a mountable UBIFS for static UBI EC header checks;
    # non-repeating synthetic entropy avoids ZIP suspicious compression ratio.
    payload = hashlib.shake_256(b"test-ubi" + bytes([index])).digest(native.PEB-64)
    return bytes(header) + payload


def synthetic_slp(version: str) -> bytes:
    original = fixture(version=version)
    header = bytearray(original[:144])
    segments = [struct.unpack_from("<IIII", header, 64+i*16) for i in range(5)]
    last_offset = segments[4][2]
    _, _, _, magic = segments[4]
    platform = fake_peb(0) + fake_peb(1)
    struct.pack_into("<IIII", header, 64+4*16, len(platform),
                     jamcrc(platform), last_offset, magic)
    pcache = original[segments[4][2]+segments[4][0]+16:]
    struct.pack_into("<I", header, 45, last_offset + len(platform))
    pcache_h = struct.pack("<IIII", len(pcache), jamcrc(pcache),
                          last_offset+len(platform)+16, 0x32100fff)
    return bytes(header) + original[144:last_offset] + platform + pcache_h + pcache


def make_zip(root: Path, version: str) -> Path:
    path = root / ("NX300M_FW_v"+version+".zip")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("NX300M_FW_v"+version+".bin",
                         synthetic_slp(version),
                         compress_type=zipfile.ZIP_DEFLATED)
    return path


class NativeOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_split_platform_from_verified_synthetic_slp_zip(self):
        archive = make_zip(self.root, "1.14")
        out, report = native.split_platform(archive, self.root, "1.14")
        self.assertEqual(out.read_bytes(), fake_peb(0)+fake_peb(1))
        self.assertEqual(report["platform_bytes"], native.PEB*2)
        self.assertEqual(report["platform_sha256"], hashlib.sha256(
            out.read_bytes()).hexdigest())
        self.assertFalse(report["source_is_manufacturer_authenticated"])

    def test_ubi_header_sample_128k_2k_4k(self):
        path = self.root/"ubi.bin"
        path.write_bytes(fake_peb(0)+fake_peb(1))
        report = native.inspect_ubi_headers(path)
        self.assertEqual(report["peb_bytes"], 131072)
        self.assertEqual(report["peb_count"], 2)
        self.assertTrue(all(x["status"]=="ubi_ec_v1"
                            for x in report["sampled_headers"]))
        self.assertFalse(report["all_peb_crc_verified"])

    def test_invalid_ubi_magic_and_offsets_rejected(self):
        path = self.root/"ubi.bin"
        data = bytearray(fake_peb(0)+fake_peb(1))
        data[:4] = b"WRNG"
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "magic"):
            native.inspect_ubi_headers(path)
        data[:4] = b"UBI#"
        struct.pack_into(">I", data, 16, 9999)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "offset"):
            native.inspect_ubi_headers(path)

    def test_original_firmware_wrong_internal_version_refused(self):
        archive = make_zip(self.root, "1.15")
        with self.assertRaisesRegex(ValueError, "version"):
            native.split_platform(archive, self.root, "1.14")

    def test_unaligned_or_short_rejected(self):
        path = self.root/"wrong.ubi"
        path.write_bytes(fake_peb(0)+b"\x00")
        with self.assertRaisesRegex(ValueError, "aligned"):
            native.inspect_ubi_headers(path)

    def test_different_native_sha_and_symbol_addresses_detected(self):
        a={"libmm-photo.so": {
            "sha256":"a"*64,"bytes":1000,"native_symbol_samples":[
                {"symbol":"CMmDeviceDriver::EncodeYcc", "value":"0x3400", "imported":False},
                {"symbol":"CYcc::GetY0", "value":"0x0", "imported":True}
            ]}}
        b={"libmm-photo.so": {
            "sha256":"b"*64,"bytes":1001,"native_symbol_samples":[
                {"symbol":"CMmDeviceDriver::EncodeYcc", "value":"0x3480", "imported":False},
                {"symbol":"CYcc::GetY0", "value":"0x0", "imported":True}
            ]}}
        report=native.compare_inventory(a,b)
        self.assertEqual(report["changed_native_elf_count"],1)
        self.assertEqual(len(report["compared_native_elfs"][0][
            "sampled_symbol_value_changes"]),1)
        self.assertFalse(report["firmware_offsets_reusable"])
        self.assertFalse(report["model_and_native_camera_abi_verified"])
        self.assertFalse(report["physical_camera_firmware_safe"])

    def test_identical_binary_not_an_abi_license(self):
        x={"libsif.so":{"sha256":"f"*64,"bytes":100,
                         "native_symbol_samples":[]}}
        report=native.compare_inventory(x,x)
        self.assertEqual(report["identical_native_elf_count"],1)
        self.assertFalse(report["firmware_offsets_reusable"])

    def test_missing_elf_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"No camera-related"):
            native.inspected_candidates(self.root)
        with self.assertRaisesRegex(ValueError,"No matching"):
            native.compare_inventory({"libmm-photo.so":{}},{})

    def test_private_root_symlink_and_group_world_writable(self):
        symlink=self.root/"link"
        symlink.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            native.private_dir(symlink)
        path=self.root/"public"
        path.mkdir(mode=0o777)
        path.chmod(0o777)
        with self.assertRaisesRegex(ValueError,"group/world"):
            native.private_dir(path)

    def test_both_synthetic_versions_have_valid_separate_ubi(self):
        from nx300m_slp_firmware_integrity import inspect
        for v in ("1.14", "1.15"):
            archive=make_zip(self.root, v)
            info=inspect(archive,expected_version=v)
            self.assertTrue(info["all_jamcrc_ok"])
            self.assertEqual(info["segments"][4]["length"],262144)


if __name__ == "__main__":
    unittest.main(verbosity=2)
