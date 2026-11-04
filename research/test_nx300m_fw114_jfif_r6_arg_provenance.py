#!/usr/bin/env python3
"""Synthetic AAPCS register/ARM vtable callback provenance tests."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_jfif_r6_arg_provenance as prov

START=0x28a88
PROLOGUE=[
  0xe1a00000,      # mov r0,r0
  0xe50b1030,      # str r1,[fp,#-0x30]
  0xe51b3030,      # ldr r3,[fp,#-0x30]
  0xe593600c,      # ldr r6,[r3,#0x0c]
  0xe12fff36,      # blx r6
]

class ARMJpegArgProvenanceTests(unittest.TestCase):
    def test_direct_synthetic_r1_stack_r6_callback_candidate(self):
        r=prov.select_provenance(PROLOGUE,START)
        self.assertEqual(r["base_pointer_source_register"],"fp")
        self.assertEqual(r["base_pointer_stack_offset"],-48)
        self.assertEqual(r["r6_field_load_site"],f"0x{START+12:08x}")
        self.assertEqual(r["blx_register_site"],f"0x{START+16:08x}")
        self.assertTrue(r["incoming_sJpegOp_r1_saved_to_slot_candidate"])
        self.assertFalse(r["incoming_arg_r1_is_live_sJpegOp_proven"])
        self.assertFalse(r["indirect_call_runtime_target_proven"])
        self.assertFalse(r["hal_encode_target_proven"])
        self.assertFalse(r["camera_install_or_flash_permitted"])

    def test_writing_this_r0_does_not_prove_r1(self):
        words=PROLOGUE.copy()
        words[1]=0xe50b0030
        r=prov.select_provenance(words,START)
        self.assertFalse(r["incoming_sJpegOp_r1_saved_to_slot_candidate"])
        self.assertEqual(r["stack_slot_store_candidates"][0]["source_register"],"r0")

    def test_two_aliasing_stack_writes_never_claim_incoming_r1(self):
        words=PROLOGUE.copy()
        words.insert(2,0xe50b2030)
        r=prov.select_provenance(words,START)
        self.assertEqual(len(r["stack_slot_store_candidates"]),2)
        self.assertFalse(r["incoming_sJpegOp_r1_saved_to_slot_candidate"])

    def test_missing_or_duplicate_r6_site_fails_closed(self):
        for words in (PROLOGUE[:4],PROLOGUE+[0xe12fff36],
                      PROLOGUE[:3]+[0xe5936008,0xe12fff36],
                      PROLOGUE[:3]+[0xe593600c,0xe593600c,0xe12fff36]):
            with self.subTest(words=words), self.assertRaises(ValueError):
                prov.select_provenance(words,START)

    def test_bad_stack_pointer_path_fails_closed(self):
        words=PROLOGUE.copy()
        words[2]=0xe5933030
        with self.assertRaisesRegex(ValueError,"r3"):
            prov.select_provenance(words,START)
        words=PROLOGUE.copy()
        words.insert(3,0xe51b302c)
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            prov.select_provenance(words,START)

    def test_word_decoder_rejects_byte_postindexed_and_ldr_register(self):
        d=prov.decode_mem_word(0xe51b3030)
        self.assertEqual(d["kind"],"LDR")
        self.assertEqual(d["base_register"],11)
        self.assertEqual(d["data_register"],3)
        self.assertEqual(d["offset"],-48)
        self.assertEqual(prov.decode_mem_word(0xe50b1030)["kind"],"STR")
        for op in (0xe1a03002,0xe4933004,0xe7b33002,0xe5db3030):
            self.assertIsNone(prov.decode_mem_word(op))

if __name__=="__main__":
    unittest.main(verbosity=2)
