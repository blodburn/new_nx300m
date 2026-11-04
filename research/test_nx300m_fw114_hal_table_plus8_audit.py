#!/usr/bin/env python3
"""Synthetic ARM32 store-site tests; real FW evidence only in private CI."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from nx300m_fw114_hal_table_plus8_audit import candidate_mem_store_sites

class HalTableField8Tests(unittest.TestCase):
    def test_immediate_arm_str_offset8(self):
        # STR r2, [r3, #8]; STR r4,[r0,#8]; other offset is excluded
        code=(0xe5832008,0xe5804008,0xe583200c,0xe5932008)
        report=candidate_mem_store_sites(code,0x1000)
        self.assertEqual(len(report),2)
        self.assertEqual(report[0]["site"],"0x00001000")
        self.assertEqual(report[0]["base_register"],"r3")
        self.assertEqual(report[0]["value_register"],"r2")
        self.assertFalse(report[0]["proven_tDscHal_plus8_write"])
        self.assertFalse(report[0]["proven_hal_encoder_callback_value"])

    def test_stack_argument_store_does_not_prove_tDscHal(self):
        report=candidate_mem_store_sites((0xe58d0008,),0x1000)
        self.assertEqual(report[0]["base_register"],"r13")
        self.assertFalse(report[0]["proven_tDscHal_plus8_write"])

    def test_non_store_or_different_offset_excluded(self):
        report=candidate_mem_store_sites(
            (0xe5932008,0xe5832004,0xe5832000,0xe1a00000),0x1000
        )
        self.assertEqual(report,[])

    def test_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"Unbounded"):
            candidate_mem_store_sites((0xe5832008,)*41,0x1000)

if __name__=="__main__":
    unittest.main(verbosity=2)
