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

    def test_real_jpeg_abi_r0_r3_register_marshal(self):
        start=0x34b18
        words=[0xe1a00000]*((0x34d78-start)//4+1)
        for address,op in (
            (0x34cc0,0xe1a06003),
            (0x34cd0,0xe1a05003),
            (0x34ce0,0xe1a04003),
            (0x34cf0,0xe1a09003),
            (0x34d00,0xe1a0a003),
            (0x34d10,0xe1a08003),
            (0x34d68,0xe1a00007),
            (0x34d6c,0xe1a01006),
            (0x34d70,0xe1a02005),
            (0x34d74,0xe1a03004),
        ):
            words[(address-start)//4]=op
        got=audit.validate_jpeg_abi_marshal(tuple(words),start)
        self.assertEqual(
            [x["argument"] for x in got[
                "DscImage_EncodeYCC_first_four_arm_args"]],
            ["DscImage instance","Y0","Y1","C0"])
        self.assertEqual(got["JPEG_callsite"],"0x00034d78")
        self.assertFalse(got["safe_copy_insertion_proven"])
        self.assertFalse(got["photography_live_pixel_input_dma_owned"])
        words[(0x34d74-start)//4]=0xe1a03005 # accidentally passes Y1 as C0
        with self.assertRaisesRegex(ValueError,"register ABI"):
            audit.validate_jpeg_abi_marshal(tuple(words),start)
        words[(0x34d74-start)//4]=0xe1a03004
        words[(0x34ce0-start)//4]=0xe1a04005 # wrong C0 getter copy
        with self.assertRaisesRegex(ValueError,"getter return"):
            audit.validate_jpeg_abi_marshal(tuple(words),start)

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
