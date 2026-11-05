#!/usr/bin/env python3
"""Synthetic FW ARM symbol/BL tests, no third-party firmware data."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_mm_photo_init_cross_elf as x


class NativePhotoInitCallerTests(unittest.TestCase):
    def test_exact_native_symbol_and_version_suffix(self):
        self.assertTrue(x.exact_symbol("_Z13mm_photo_initv"))
        self.assertTrue(x.exact_symbol("_Z13mm_photo_initv@@CAMERA_1"))
        for raw in ("mm_photo_init", "_Z13mm_photo_initv_foo",
                    "_Z12mm_photo_initv", "_Z13mm_photo_exitv",
                    "mm_photo_init_extra"):
            with self.subTest(raw=raw):
                self.assertFalse(x.exact_symbol(raw))

    def test_readelf_import_and_export_and_similar_spelling(self):
        rows = (
            "  8: 00000000 0 FUNC GLOBAL DEFAULT UND _Z13mm_photo_initv\n"
            "  9: 00055114 32 FUNC GLOBAL DEFAULT 12 _Z13mm_photo_initv\n"
            " 10: 00000000 0 FUNC GLOBAL DEFAULT UND _Z14mm_photo_initsv\n"
        )
        found = x.symbol_rows(rows)
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0]["undefined"])
        self.assertFalse(found[1]["undefined"])

    def test_direct_edges_require_exact_kind_and_name(self):
        items = {
            "identified_calls_truncated": False,
            "identified_callsite_evidence": [
                {"callsite": "0x00005500", "target_kind": "local",
                 "target_symbol": "mm_photo_init()"},
                {"callsite": "0x00005504", "target_kind": "import",
                 "target_symbol": "_Z13mm_photo_initv"},
                {"callsite": "0x00005508", "target_kind": "import",
                 "target_symbol": "_Z13mm_photo_initv_extra"},
                {"callsite": "0x0000550c", "target_kind": "local",
                 "target_symbol": "_Z13mm_photo_initv"},
            ],
        }
        actual = x.direct_edges(items)
        self.assertEqual([q["edge_class"] for q in actual],
                         ["ARM_BL_LOCAL", "ARM_BL_PLT_IMPORT"])
        self.assertTrue(all(not q["runtime_binding_verified"]
                            for q in actual))
        with self.assertRaisesRegex(ValueError, "Truncated"):
            x.direct_edges({"identified_calls_truncated": True,
                            "identified_callsite_evidence": []})
        with self.assertRaisesRegex(ValueError, "Invalid"):
            x.direct_edges({})

    def test_bounded_function_inventory_and_aliases(self):
        rows = (
            "  8: 00001000 16 FUNC GLOBAL DEFAULT 12 _Z13mm_photo_initv\n"
            "  9: 00001000 16 FUNC WEAK DEFAULT 12 _Z13mm_photo_initv\n"
            " 10: 00001021 40 FUNC GLOBAL DEFAULT 12 thumb_fn\n"
            " 11: 00001100 12 FUNC GLOBAL DEFAULT 12 other_fn\n"
            " 12: 00000000 0 FUNC GLOBAL DEFAULT UND external_fn\n"
        )
        self.assertEqual(x.method_inventory(rows),[(0x1000,16),(0x1100,12)])
        self.assertEqual(x.method_inventory(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
