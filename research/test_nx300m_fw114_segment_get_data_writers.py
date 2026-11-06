#!/usr/bin/env python3
"""Synthetic native ARM record-offset discovery checks (no vendor binary)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_segment_get_data_writers as module


class SegmentGetDataWriters(unittest.TestCase):
    def test_arm_ldr_str_of_exact_field12(self):
        read=module.arm_word_offset12(0xe593300c)
        self.assertEqual(read["operation"],"LDR")
        self.assertEqual(read["base_register"],"r3")
        self.assertEqual(read["value_register"],"r3")
        self.assertEqual(read["offset_bytes"],12)
        self.assertFalse(read["record_identity_confirmed"])
        write=module.arm_word_offset12(0xe583200c)
        self.assertEqual(write["operation"],"STR")
        self.assertEqual(write["value_register"],"r2")
        self.assertFalse(write["conditional"])
        cond=module.arm_word_offset12(0x1583200c)
        self.assertTrue(cond["conditional"])
        for word in (0xe5933008,0xe5934004,0xe5832008,
                     0xe783200c,0xe5c3200c,0xe5a3200c,
                     0xe513300c,0xf583200c):
            with self.subTest(word=hex(word)):
                self.assertIsNone(module.arm_word_offset12(word))
        for invalid in (-1,0x100000000,None):
            with self.assertRaises((TypeError,ValueError)):
                module.arm_word_offset12(invalid)

    def test_symbol_rows_deduplicated(self):
        text="""Symbol table '.dynsym' contains 2 entries:
   4: 0000a114   796 FUNC GLOBAL DEFAULT   11 sysmmap_segment_alloc
   5: 00009420    28 FUNC GLOBAL DEFAULT   11 sysmmap_segment_get_data
Symbol table '.symtab' contains 3 entries:
  25: 0000a114   796 FUNC GLOBAL DEFAULT   11 sysmmap_segment_alloc
  26: 00009420    28 FUNC GLOBAL DEFAULT   11 sysmmap_segment_get_data
  27: 00001120    16 FUNC GLOBAL DEFAULT  UND sysmmap_segment_nope
"""
        funcs=module.segment_functions(text)
        self.assertEqual(len(funcs),2)
        self.assertEqual(
            next(f for f in funcs
                 if f["symbol"]==module.GET_DATA)["address"],0x9420)
        self.assertEqual(funcs[0]["symbol"],module.GET_DATA)

    def test_bounded_symbol_inventory(self):
        huge="\n".join("nonsense" for _ in range(module.MAX_SYM_LINES+2))
        with self.assertRaisesRegex(ValueError,"Unbounded"):
            module.segment_functions(huge)


if __name__=="__main__":
    unittest.main(verbosity=2)
