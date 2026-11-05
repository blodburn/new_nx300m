#!/usr/bin/env python3
"""Static only: reject incorrect ARM branch/lifetime claims."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_photo_buffer_lifetime as life


class NativeARMPhotoLifetimeTests(unittest.TestCase):
    def test_conditional_and_unconditional_arm_B(self):
        # BNE +12, B -8
        self.assertEqual(life.arm_direct_b(0x1a000001,0x1000)["target"],
                         "0x0000100c")
        self.assertEqual(life.arm_direct_b(0xeafffffc,0x1010)["target"],
                         "0x00001008")
        self.assertFalse(life.arm_direct_b(0x1a000001,0x1000)["unconditional"])
        self.assertTrue(life.arm_direct_b(0xeafffffc,0x1010)["unconditional"])
        for op in (0xeb000001,0xfa000001,0xe12fff1e,0xe1a00000):
            self.assertIsNone(life.arm_direct_b(op,0x1000))

    def test_native_function_branch_bounds(self):
        words=(0x1a000000,0xeafffffc,0xeb000003,0xe1a00000)
        b=life.branch_boundaries(words,0x1000)
        self.assertEqual(len(b),2)
        self.assertEqual(b[0]["target"],"0x00001008")
        self.assertTrue(b[0]["target_inside_function"])
        self.assertEqual(b[1]["target"],"0x00001000")
        with self.assertRaises(ValueError):
            life.branch_boundaries(words,0x1001)
        with self.assertRaises(ValueError):
            life.branch_boundaries((),0x1000)

    def test_unbounded_excerpts_reject(self):
        words=(0xe1a00000,0xe5903004,0xe58b3008,0xe12fff1e)
        result=life.excerpt(words,0x1000,0x1000,0x1010)
        self.assertEqual(len(result),4)
        self.assertEqual(result[1]["LDR_STR_immediate"]["kind"],"LDR")
        self.assertEqual(result[2]["LDR_STR_immediate"]["kind"],"STR")
        for args in ((0x1000,0x1014),(0x0ffc,0x1004),(0x1001,0x1008)):
            with self.subTest(args=args),self.assertRaises(ValueError):
                life.excerpt(words,0x1000,*args)

    def test_no_false_live_buffer_claims_from_static_file(self):
        self.assertEqual(life.FUNC,"CMmDeviceDriver::EncodeYcc(")
        self.assertIn((0x34b18,0x34c14),life.WINDOWS)
        self.assertEqual(life.WINDOWS[1][1],0x34d9c)


if __name__=="__main__":
    unittest.main(verbosity=2)
