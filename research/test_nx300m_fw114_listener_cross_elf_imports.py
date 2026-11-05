#!/usr/bin/env python3
"""Synthetic cross-ELF selection and symbol tests; no vendor blobs."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_listener_cross_elf_imports as scan


def fake_arm_elf() -> bytes:
    head = bytearray(52)
    head[:6] = b"\x7fELF\x01\x01"
    head[18:20] = (40).to_bytes(2, "little")
    return bytes(head)


class CrossELF(unittest.TestCase):
    def test_exact_method_name_candidates(self):
        source = (
            " 123: 00000000     0 FUNC    GLOBAL DEFAULT  UND "
            "_Z27RegisterMemoryMapListnerv\n"
            " 124: 000350d8   220 FUNC    GLOBAL DEFAULT   12 "
            "_Z27RegisterMemoryMapListnerv\n"
            " 125: 00000000     0 FUNC    GLOBAL DEFAULT  UND "
            "_Z19RegisterMemoryMapsV\n"
        )
        entries = scan.symbol_candidates(source)
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0]["undefined_import"])
        self.assertFalse(entries[1]["undefined_import"])
        self.assertTrue(scan.target_symbol_spelling(
            "_Z27RegisterMemoryMapListnerv@@CAMERA_1"))
        self.assertFalse(scan.target_symbol_spelling("OtherListener"))

    def test_select_only_root_local_valid_arm_elf(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            (root/"libmm-photo.so").write_bytes(fake_arm_elf())
            (root/"di-camera-app").write_bytes(fake_arm_elf())
            (root/"untargeted.bin").write_bytes(b"random")
            selected = scan.select_paths(root)
            self.assertEqual(set(selected), {
                "libmm-photo.so", "di-camera-app"
            })

    def test_reject_missing_bad_header_or_symlink_escape(self):
        with TemporaryDirectory() as t:
            root = Path(t)/"fw"
            root.mkdir()
            with self.assertRaisesRegex(ValueError,"photo library"):
                scan.select_paths(root)
            target = root/"libmm-photo.so"
            target.write_bytes(b"x"*52)
            with self.assertRaisesRegex(ValueError,"Expected ELF32"):
                scan.select_paths(root)
        with TemporaryDirectory() as t:
            base = Path(t)
            root = base/"fw"
            root.mkdir()
            external = base/"file.bin"
            external.write_bytes(fake_arm_elf())
            (root/"libmm-photo.so").symlink_to(external)
            with self.assertRaisesRegex(ValueError,"escapes"):
                scan.select_paths(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
