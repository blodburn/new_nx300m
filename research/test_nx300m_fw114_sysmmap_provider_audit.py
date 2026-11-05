#!/usr/bin/env python3
"""Synthetic export / name-selection tests; no vendor image is included."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_sysmmap_provider_audit as a


def fake_arm_eabi5() -> bytes:
    h=bytearray(52)
    h[:6]=b"\x7fELF\x01\x01"
    h[18:20]=(40).to_bytes(2,"little")
    h[36:40]=(0x05000002).to_bytes(4,"little")
    return bytes(h)


class SysmmapProvider(unittest.TestCase):
    def test_exact_symbol_matching_and_import_export(self):
        src=(
            " 1: 00001000 120 FUNC GLOBAL DEFAULT 12 sysmmap_alloc\n"
            " 2: 00002000 104 FUNC GLOBAL DEFAULT 12 sysmmap_cached_alloc\n"
            " 3: 00003000  80 FUNC GLOBAL DEFAULT 12 sysmmap_free\n"
            " 4: 00004000 100 FUNC GLOBAL DEFAULT 12 sysmmap_client_callback_register\n"
            " 5: 00000000   0 FUNC GLOBAL DEFAULT UND sysmmap_free\n"
            " 6: 00005000  16 FUNC GLOBAL DEFAULT 12 sysmmap_alloc_more\n"
            " 7: 00006000  16 FUNC GLOBAL DEFAULT 12 sysmmap_free_legacy\n"
        )
        r=a.parse_symbol_rows(src)
        self.assertEqual(len(r),5)
        self.assertEqual(len([x for x in r if x["is_defined"]]),4)
        self.assertTrue(any(x["symbol"]=="sysmmap_free" and not
                            x["is_defined"] for x in r))
        self.assertFalse(a.matching_target("sysmmap_alloc_more"))
        self.assertTrue(a.matching_target("sysmmap_free@@SAM_1"))

    def test_select_realpath_and_refuse_traversal(self):
        with TemporaryDirectory() as t:
            base=Path(t)
            root=base/"firmware"
            root.mkdir()
            path=root/a.LIBRARY
            path.write_bytes(fake_arm_eabi5())
            self.assertEqual(a.find_provider(root,a.LIBRARY),path)
            self.assertRaises(ValueError,a.find_provider,root,"libsysmmap.so")
        with TemporaryDirectory() as t:
            base=Path(t)
            root=base/"firmware"
            root.mkdir()
            outside=base/"outside"
            outside.write_bytes(fake_arm_eabi5())
            (root/a.LIBRARY).symlink_to(outside)
            with self.assertRaisesRegex(ValueError,"escapes"):
                a.find_provider(root,a.LIBRARY)

    def test_reject_invalid_elf_header(self):
        with TemporaryDirectory() as t:
            root=Path(t)
            (root/a.LIBRARY).write_bytes(b"x"*52)
            with self.assertRaises(ValueError):
                a.find_provider(root,a.LIBRARY)


if __name__=="__main__":
    unittest.main(verbosity=2)
