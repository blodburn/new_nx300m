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

    def test_exact_30_10_mib_ctor_offsets_and_corruption(self):
        start=0x351b4
        words=[0xe1a00000]*23
        proof_words={
            0x351c8:0xe51b3008,0x351cc:0xe51b200c,
            0x351d0:0xe5832000,0x351d4:0xe51b3008,
            0x351d8:0xe5933000,0x351dc:0xe283261e,
            0x351e0:0xe51b3008,0x351e4:0xe5832004,
            0x351e8:0xe51b3008,0x351ec:0xe5933004,
            0x351f0:0xe283260a,0x351f4:0xe51b3008,
            0x351f8:0xe5832008,
        }
        for pc,op in proof_words.items():
            words[(pc-start)//4]=op
        p=pool.prove_ctor_immutable_slot_base(tuple(words),start)
        self.assertEqual(p["field_offset_to_base"],
                         {"0":0,"4":30*1024*1024,"8":40*1024*1024})
        self.assertFalse(p["physical_pool_size_or_allocation_bounds_proven"])
        self.assertFalse(p["concurrent_or_later_writers_excluded"])
        self.assertIsNone(pool.decode_arm_add_immediate(0xe1a00000))
        changed=words.copy()
        changed[(0x351f0-start)//4]=0xe283260b
        with self.assertRaisesRegex(ValueError,"30MiB"):
            pool.prove_ctor_immutable_slot_base(tuple(changed),start)
        changed=words.copy()
        changed[(0x351f8-start)//4]=0xe5832004
        with self.assertRaisesRegex(ValueError,"constructor ARM changed"):
            pool.prove_ctor_immutable_slot_base(tuple(changed),start)

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
