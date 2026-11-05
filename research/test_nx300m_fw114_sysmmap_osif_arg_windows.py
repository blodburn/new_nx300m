#!/usr/bin/env python3
"""Synthetic ARM state tests, no actual camera firmware binaries included."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_sysmmap_osif_arg_windows as a


class OSIFArgumentWindows(unittest.TestCase):
    def test_writer_candidates_and_unknown_argument_policy(self):
        mov=a.classify_arm_argument_writer(0xe1a01002,0x1000,1)
        self.assertEqual(mov["kind"],"MOV_REGISTER")
        self.assertEqual(mov["value"],"r2")
        self.assertFalse(mov["proves_arg_value"])
        imm=a.classify_arm_argument_writer(0xe3a01020,0x1004,1)
        self.assertEqual(imm["kind"],"MOV_IMMEDIATE")
        self.assertEqual(imm["value"],32)
        ldr=a.classify_arm_argument_writer(0xe59b1004,0x1008,1)
        self.assertEqual(ldr["kind"],"LDR_IMMEDIATE")
        self.assertEqual(ldr["source_register"],"r11")
        self.assertEqual(ldr["byte_offset"],4)
        self.assertIsNone(a.classify_arm_argument_writer(0x11a01002,0x100c,1))
        self.assertIsNone(a.classify_arm_argument_writer(0xe1a02003,0x1010,1))

    def test_bounded_aapcs_window(self):
        words=(0xe1a01002,0xe3a02001,0xe59b3008,0xeb000001)
        r=a.argument_context(words,0x1000,0x100c,lookback=3)
        self.assertEqual(r["callsite"],"0x0000100c")
        self.assertEqual(r["arm_aapcs_6_arg_mmap_length_register"],"r1")
        self.assertEqual(r["candidate_argument_writers"]["r1"][0]["value"],"r2")
        self.assertIsNone(r.get("actual_requested_mmap_bytes_observed") or None)
        self.assertFalse(r["native_mmap_argument_provenance_complete"])
        with self.assertRaisesRegex(ValueError,"callsite"):
            a.argument_context(words,0x1000,0x1010)
        with self.assertRaisesRegex(ValueError,"branch-with-link"):
            a.argument_context(words,0x1000,0x1008)
        with self.assertRaises(ValueError):
            a.argument_context(words,0x1000,0x100c,lookback=50)

    def test_static_os_symbol_expectations(self):
        self.assertEqual(a.EXPECTED["sysmmap_osif_alloc"]["calls"],
                         {"ioctl":0xc7f0,"mmap":0xc81c})
        self.assertEqual(a.EXPECTED["sysmmap_osif_free"]["calls"],
                         {"munmap":0xc8d8})
        self.assertFalse(a.compare_versions.__doc__ == "Device-ready")


if __name__=="__main__":
    unittest.main(verbosity=2)
