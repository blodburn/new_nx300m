#!/usr/bin/env python3
"""Safe native-provider path selection tests; no vendor firmware included."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import struct

import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_cycc_provider_probe as probe


class CyccProviderPathTests(unittest.TestCase):
    def test_missing_optional_provider_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(probe.safe_sources(Path(t)),{})

    def test_symlink_stays_within_private_root(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            target=root/"libmm-type.so.0.0.0"
            target.write_bytes(b"x"*128)
            (root/"libmm-type.so").symlink_to(target.name)
            indexed=probe.safe_sources(root)
            self.assertEqual(indexed["libmm-type.so"],target.resolve())

    def test_escape_symlink_rejects(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/"private";root.mkdir()
            out=Path(t)/"outside.so";out.write_bytes(b"x"*128)
            (root/"libmm-type.so").symlink_to(out)
            with self.assertRaisesRegex(ValueError,"escapes"):
                probe.safe_sources(root)

    def test_realistic_cycc_destructor_arm_lifecycle_is_only_static(self):
        # BL to same-ELF local method, register BLX, then return.
        words=(0xe92d4008,0xeb000002,0xe12fff33,0xe8bd8008)
        data=struct.pack("<IIII",*words)
        result=probe.critical_arm_body(
            data,[(0x1000,16,0)],0x1000,16,
            {0x1010:"CYcc::Cleanup()"},{}
        )
        self.assertEqual(result["arm_word_count"],4)
        self.assertEqual(
            result["direct_ARM_BL_edges"][0]["local_native_function"],
            "CYcc::Cleanup()"
        )
        self.assertEqual(
            result["register_indirect_branches"][0]["register"],3
        )
        self.assertFalse(result["native_actual_pixel_release_verified"])
        self.assertFalse(result["no_hidden_or_indirect_release_proven"])

    def test_alias_conflict_is_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            one=root/"a";two=root/"b";one.mkdir();two.mkdir()
            for location in (one,two):
                (location/"libmm-type.so").write_bytes(b"x"*128)
            with self.assertRaisesRegex(ValueError,"Ambiguous"):
                probe.safe_sources(root)


if __name__=="__main__":
    unittest.main(verbosity=2)
