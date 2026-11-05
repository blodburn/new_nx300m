#!/usr/bin/env python3
"""Only synthetic ARM words/size guard tests; no firmware pixels or blobs."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_pool_mmap_size_contract as x


class MemoryMapSizeContract(unittest.TestCase):
    def test_pointer_arithmetic_requires_40mib(self):
        self.assertEqual(x.MIN_ARENA_BYTES, 41943040)
        self.assertEqual(x.CONTRACT["pool_slot4_offset_bytes"], 31457280)
        self.assertEqual(x.CONTRACT["pool_slot8_offset_bytes"], 41943040)
        self.assertEqual(x.CONTRACT["alloc_size_descriptor_offset_bytes"], 4)
        self.assertEqual(x.CONTRACT["free_size_descriptor_offset_bytes"], 4)

    def test_real_sample_gate_is_fail_closed(self):
        for length in (0, 1, 1048576, 40*1024*1024-1, -1):
            with self.subTest(length=length), self.assertRaises(ValueError):
                x.assert_contract(length, length)
        for value in (None, 0.0, 40.0, True, str(40*1024*1024)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                x.assert_contract(value, value)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            x.assert_contract(40*1024*1024, 40*1024*1024+1)
        ok = x.assert_contract(40*1024*1024, 40*1024*1024)
        self.assertTrue(ok["size_lower_bound_satisfied"])
        self.assertFalse(ok["actual_runtime_dma_coherency_established"])
        self.assertFalse(ok["firmware_flash_permitted"])

    def test_decode_real_site_shaped_arm_synthetic_words(self):
        begin=0x00034e54
        code=(
            0xe51b301c,
            0xe5932004,
            0xe51b301c,
            0xe593300c,
            0xe1a00002,
            0xe1a01003,
        )
        proof=x.exact_listener_words(code,begin,"AllocListener")
        self.assertEqual(proof["descriptor_size_offset"],4)
        self.assertFalse(proof["actual_descriptor_size_bytes_observed"])
        mutated=list(code)
        mutated[1]=0xe5932008
        with self.assertRaisesRegex(ValueError,"descriptor size path"):
            x.exact_listener_words(tuple(mutated),begin,"AllocListener")
        with self.assertRaises(ValueError):
            x.exact_listener_words(code,begin,"UnexpectedListener")

    def test_bounded_arm_window(self):
        words=tuple(range(32))
        window=x.bounded_window(words,0x1000,0x1010,0x1020)
        self.assertEqual([item["word"] for item in window],
                         ["0x00000004","0x00000005",
                          "0x00000006","0x00000007"])
        for begin,end in ((0xffc,0x1010),(0x1010,0x1090),
                          (0x1020,0x1010),(0x1001,0x1010)):
            with self.subTest(begin=begin,end=end),self.assertRaises(ValueError):
                x.bounded_window(words,0x1000,begin,end)


if __name__=="__main__":
    unittest.main(verbosity=2)
