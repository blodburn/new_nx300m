#!/usr/bin/env python3
"""Synthetic, source-only checks for ARM32 listener relocation witnesses.

No Samsung firmware, physical camera or image data are required.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_listener_callback_registration as cb


class CallbackPointerRelocations(unittest.TestCase):
    def test_only_arm_relative_relocations(self):
        sample = (
            "00002030  00000017 R_ARM_RELATIVE\n"
            "00002034  00000016 R_ARM_JUMP_SLOT sysmmap_alloc\n"
            "00002038  00000002 R_ARM_ABS32 listener\n"
            "0000203c  00000017 R_ARM_RELATIVE\n"
            "bogus 00002040 R_ARM_RELATIVE\n"
        )
        self.assertEqual(cb.relative_relocations(sample), {0x2030, 0x203c})
        self.assertEqual(cb.relative_relocations(""), set())

    def test_relocated_pointer_must_equal_exact_listener_address(self):
        image = bytearray(128)
        struct.pack_into("<I", image, 0x30, 0x34d9c)
        struct.pack_into("<I", image, 0x34, 0x34fc8)
        segments = [(0x2000, 0x80, 0)]
        verified = cb.word_sites(bytes(image), segments, 0x34d9c,
                                 {0x2030, 0x2034, 0x3000})
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["relocation_address"], "0x00002030")
        self.assertTrue(verified[0]["R_ARM_RELATIVE_confirmed"])
        self.assertFalse(verified[0]["listener_registering_function_proven"])
        self.assertFalse(verified[0]["callback_invocation_on_camera_proven"])

    def test_no_unrelocated_or_truncated_pointer_guess(self):
        image = bytearray(128)
        struct.pack_into("<I", image, 0x30, 0x34d9c)
        self.assertEqual(cb.word_sites(bytes(image), [(0x2000, 0x80, 0)],
                                       0x34d9c, {0x2034}), [])
        self.assertEqual(cb.word_sites(bytes(image), [(0x2000, 0x30, 0)],
                                       0x34d9c, {0x2030}), [])

    def test_relocation_count_is_bounded(self):
        row = "00002030  00000017 R_ARM_RELATIVE"
        self.assertEqual(len(cb.relative_relocations(row)), 1)
        before = cb.MAX_RELOCS
        cb.MAX_RELOCS = 1
        try:
            with self.assertRaisesRegex(ValueError, "Too many"):
                cb.relative_relocations(
                    "00002030 00000017 R_ARM_RELATIVE\n"
                    "00002034 00000017 R_ARM_RELATIVE")
        finally:
            cb.MAX_RELOCS = before


if __name__ == "__main__":
    unittest.main(verbosity=2)
