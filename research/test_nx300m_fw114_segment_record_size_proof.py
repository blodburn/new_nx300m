#!/usr/bin/env python3
"""Synthetic ARM32 instruction mutation tests. No vendor ELF is committed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_segment_record_size_proof as proof


def synthetic_native_body()->tuple[int,...]:
    words=[0xe1a00000]*(proof.SIZE//4)
    for pc,opcode in proof.WORDS.items():
        words[(pc-proof.START)//4]=opcode
    return tuple(words)


class NativeRecordSize(unittest.TestCase):
    def test_verified_shift_is_exactly_ten_bits(self):
        self.assertEqual(proof.decode_lsl_bytes(0xe1a02503),10)
        for opcode in (0xe1a02483,0xe1a02103,0xe1a03503,0x11a02503):
            with self.subTest(opcode=hex(opcode)),self.assertRaises(ValueError):
                proof.decode_lsl_bytes(opcode)

    def test_static_formula_witness_and_fail_closed_mutation(self):
        words=synthetic_native_body()
        result=proof.proof_from_words(words)
        self.assertEqual(result["shift_left_bits"],10)
        self.assertEqual(result["length_to_osif_r1_at"],"0x0000a33c")
        self.assertTrue(result["conditional_path_may_be_skipped"])
        self.assertFalse(result["record_value_or_actual_allocated_bytes_observed"])
        self.assertFalse(result["descriptor_plus4_equals_record_plus12_times1024"])
        self.assertFalse(result["on_camera_dma_coherency_or_ownership_verified"])
        self.assertFalse(result["firmware_flash_permitted"])
        for pc in proof.WORDS:
            mutated=list(words)
            mutated[(pc-proof.START)//4]=0xe1a00000
            with self.subTest(site=hex(pc)),self.assertRaisesRegex(
                ValueError,"Changed native segment"):
                proof.proof_from_words(tuple(mutated))
        with self.assertRaises(ValueError):
            proof.proof_from_words(words[:-1])
        with self.assertRaises(ValueError):
            proof.proof_from_words(words,start=proof.START+4)

    def test_safe_host_only_size_conversion(self):
        self.assertEqual(proof.simulated_request_bytes(0),0)
        self.assertEqual(proof.simulated_request_bytes(1),1024)
        self.assertEqual(
            proof.simulated_request_bytes(40*1024),40*1024*1024)
        self.assertEqual(proof.simulated_request_bytes(4194303),4294966272)
        for bad in (True,False,-1,4194304,2**32,1.5,"40960",None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                proof.simulated_request_bytes(bad)


if __name__=="__main__":
    unittest.main(verbosity=2)
