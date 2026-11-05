#!/usr/bin/env python3
"""Synthetic ARM instructions only; no private FW or camera data."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_pool_slot8_writer_audit as pool

class NativePoolWrites(unittest.TestCase):
    def test_arm_store_8_candidate_not_runtime_proof(self):
        words=(0xe58b1008,0xe5832008,0xe5932008,0xe5832004,0xe1a00000)
        r=pool.offset8_stores(words,0x1000)
        self.assertEqual(len(r),2)
        self.assertEqual(r[0]["base_register"],"r11")
        self.assertEqual(r[1]["base_register"],"r3")
        self.assertEqual(r[1]["value_register"],"r2")
        self.assertFalse(r[1]["is_confirmed_pool_this_plus8_write"])
        self.assertFalse(r[1]["is_confirmed_live_pool_reuse"])

    def test_fail_closed_on_invalid_or_unbounded_arm(self):
        with self.assertRaises(ValueError):
            pool.offset8_stores((),0x1000)
        with self.assertRaises(ValueError):
            pool.offset8_stores((0xe5832008,),0x1001)
        with self.assertRaises(ValueError):
            pool.offset8_stores((0xe5832008,)*4097,0x1000)

    def test_reject_unrelated_loads_offsets(self):
        self.assertEqual(
            pool.offset8_stores((0xe5932008,0xe583200c,0xe1a00000),0x1000),
            [])

if __name__=="__main__":
    unittest.main(verbosity=2)
