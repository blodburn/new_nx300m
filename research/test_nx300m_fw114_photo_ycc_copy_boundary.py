#!/usr/bin/env python3
"""No proprietary firmware: strictly synthetic ARM code evidence tests."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_photo_ycc_copy_boundary as audit

class NativeYccBufferBoundaryTests(unittest.TestCase):
    def test_actual_shape_of_getter_call_window_without_claiming_ownership(self):
        words=(0xe5913000,0xe50b300c,0xe1a00001,0xeb000012,0xe1a00000)
        x=audit.site_window(words,0x34cb0,0x34cbc)
        self.assertEqual(x["callsite"],"0x00034cbc")
        self.assertFalse(x["DMA_or_owned_lifetime_proven"])
        self.assertFalse(x["register_arg_values_runtime_proven"])
        self.assertEqual(
            x["bounded_arm_instruction_window"][1]["memory_op"],
            {"kind":"STR","base":"r11","register":"r3","offset":-12}
        )
        self.assertTrue(x["bounded_arm_instruction_window"][3]["is_this_call"])

    def test_unaligned_or_outside_callsite_rejects(self):
        words=(0xe1a00000,)*5
        for site in (0x4001,0x3ffc,0x4014):
            with self.subTest(site=site),self.assertRaises(ValueError):
                audit.site_window(words,0x4000,site)

    def test_unbounded_method_or_non_arm_function_rejects(self):
        import struct
        words=struct.pack("<II",0xe1a00000,0xe12fff1e)
        for start,size in ((0x1001,12),(0x1000,8),(0x1000,8196)):
            with self.subTest(start=start,size=size),self.assertRaises(ValueError):
                audit.native_words(words,[(0x1000,8,0)],start,size)

    def test_getter_order_expected_in_real_native_abi_gate(self):
        self.assertEqual(
            [s for s,_ in audit.jpeg.EDGES],list(audit.CALL_SITES))
        self.assertEqual(audit.GETTERS[-1],"DscImage::EncodeYCC(")
        self.assertEqual(len(audit.CALL_SITES),8)
        self.assertIn("CMmDeviceDriver::BlockCopy(CYcc&, CYcc&)",
                      audit.METHODS)
        self.assertIn("CMmDeviceDriver::BlockCopy(CYcc&, sYccAddr)",
                      audit.METHODS)

if __name__=="__main__":
    unittest.main(verbosity=2)
