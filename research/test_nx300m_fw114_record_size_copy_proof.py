#!/usr/bin/env python3
"""Synthetic tests for the strictly static SYSMMAP P+12 copy witness."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_record_size_copy_proof as p


def words_fixture()->tuple[int,...]:
    words=[0xe1a00000]*(p.SIZE//4)
    for site,word in p.COPIED_WORDS.items():
        words[(site-p.START)//4]=word
    words[(p.CALL_GET_MEMPOOL-p.START)//4]=0xeb000000
    return tuple(words)


class RecordSizeCopyProof(unittest.TestCase):
    def test_field_plus8_copy_maps_to_get_data_plus12(self):
        result=p.proof_from_words(words_fixture())
        self.assertEqual(result["source_field_offset_bytes"],8)
        self.assertEqual(
            result["destination_helper_returns_get_data_plus_bytes"],4)
        self.assertEqual(result["destination_field_offset_from_helper"],8)
        self.assertEqual(result["effective_destination_field_from_get_data_return"],12)
        self.assertEqual(result["static_copy_formula"],
                         "*(get_data(r0)+12) = *(source_ptr+8)")
        self.assertEqual(result["adjacent_zero_reset_effective_offset"],16)
        self.assertTrue(result["read_value_may_be_zero"])
        for flag in ("nonzero_value_or_real_allocation_size_proven",
                     "source_pointer_is_user_listener_descriptor_proven",
                     "record_pointer_identity_in_other_calls_proven",
                     "all_control_flow_paths_reach_copy_proven",
                     "camera_runtime_mapping_or_dma_safety_proven",
                     "camera_flash_permitted"):
            self.assertFalse(result[flag],flag)

    def test_each_real_machine_word_is_a_required_witness(self):
        source=words_fixture()
        for site in p.COPIED_WORDS:
            changed=list(source)
            changed[(site-p.START)//4]=0xe1a00000
            with self.subTest(site=hex(site)),self.assertRaises(ValueError):
                p.proof_from_words(tuple(changed))
        changed=list(source)
        changed[(p.CALL_GET_MEMPOOL-p.START)//4]=0xe1a00000
        with self.assertRaises(ValueError):
            p.proof_from_words(tuple(changed))
        with self.assertRaises(ValueError):
            p.proof_from_words(source[:-1])
        with self.assertRaises(ValueError):
            p.proof_from_words(source,start=p.START+4)
        invalid=list(source)
        invalid[0]=True
        with self.assertRaises(ValueError):
            p.proof_from_words(tuple(invalid))


if __name__=="__main__":
    unittest.main(verbosity=2)
