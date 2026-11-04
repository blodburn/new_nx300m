#!/usr/bin/env python3
"""Synthetic AAPCS register/ARM vtable callback provenance tests."""
from __future__ import annotations

import sys
import struct
import tempfile
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
        self.assertFalse(r["incoming_object_this_r0_saved_to_slot_candidate"])
        self.assertFalse(r["incoming_arg_r1_is_live_sJpegOp_proven"])
        self.assertFalse(r["indirect_call_runtime_target_proven"])
        self.assertFalse(r["hal_encode_target_proven"])
        self.assertFalse(r["camera_install_or_flash_permitted"])

    def test_writing_this_r0_does_not_prove_r1(self):
        words=PROLOGUE.copy()
        words[1]=0xe50b0030
        r=prov.select_provenance(words,START)
        self.assertFalse(r["incoming_sJpegOp_r1_saved_to_slot_candidate"])
        self.assertTrue(r["incoming_object_this_r0_saved_to_slot_candidate"])
        self.assertFalse(r["cpp_aapcs_this_pointer_runtime_identity_proven"])
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

    def test_three_tDscHal_slots_to_instance_exact_arm_copies(self):
        words=[
            0xe50b0008, # str r0,[fp,#-8] this
            0xe50b100c, # str r1,[fp,#-12] tDscHal*
            0xe51b300c,0xe5932000,0xe51b3008,0xe5832004,
            0xe51b300c,0xe5932004,0xe51b3008,0xe5832008,
            0xe51b300c,0xe5932008,0xe51b3008,0xe583200c,
        ]
        result=prov.decode_hal_registration_words(words,0x28828)
        pairs=result["static_arm_exact_field_copies"]
        self.assertEqual(
            [(x["tDscHal_input_field_offset"],x["dscjfif_object_field_offset"])
             for x in pairs],[(0,4),(4,8),(8,12)]
        )
        self.assertTrue(result["jfif_encode_callback_object_plus12_from_hal_plus8"])
        self.assertFalse(result["runtime_hal_callback_address_proven"])
        self.assertFalse(result["hardware_encode_is_third_callback_slot_proven"])
        self.assertFalse(result["camera_firmware_flash_permitted"])

    def test_hal_register_swapped_slots_or_missing_arg_reject(self):
        words=[
            0xe50b0008,0xe50b100c,
            0xe51b300c,0xe5932000,0xe51b3008,0xe5832004,
            0xe51b300c,0xe5932004,0xe51b3008,0xe5832008,
            0xe51b300c,0xe5932008,0xe51b3008,0xe583200c,
        ]
        wrong=words.copy()
        wrong[11]=0xe5932004
        with self.assertRaisesRegex(ValueError,"field copy"):
            prov.decode_hal_registration_words(wrong,0x28828)
        wrong=words.copy()
        wrong[1]=0xe50b200c
        with self.assertRaisesRegex(ValueError,"stack arguments"):
            prov.decode_hal_registration_words(wrong,0x28828)

    def test_offline_constructor_member_store_is_only_syntax(self):
        # An isolated synthetic function is not a firmware loader or camera.
        with tempfile.TemporaryDirectory() as directory:
            fn=Path(directory)/"synthetic_code.bin"
            fn.write_bytes(struct.pack(
                "<III",0xe580100c,0xe583200c,0xe12fff1e
            ))
            info={
                "DscJPEG::DscJPEG()":{
                    "address":0x1000,"size":12,"kind":"FUNC",
                },
            }
            values=prov.constructor_field_store_candidates(
                fn,[(0x1000,12,0)],info
            )
            self.assertEqual(len(values),1)
            stores=values[0]["stores_into_any_base_plus12"]
            self.assertEqual(len(stores),2)
            self.assertEqual(
                [s["value_register"] for s in stores],["r1","r2"]
            )
            self.assertEqual(
                [s["base_register"] for s in stores],["r0","r3"]
            )
            self.assertFalse(values[0]["callback_assignment_proven"])
            self.assertFalse(values[0]["actual_dscjfif_this_object_proven"])

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
