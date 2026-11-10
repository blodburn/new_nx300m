#!/usr/bin/env python3
"""Synthetic ARM32 stack receiver tests. NEVER accesses camera buffers."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_encoder_format_pack_origins as fmt
import nx300m_fw114_ycc_getter_receiver_sources as source
import test_nx300m_fw114_encoder_format_pack_origins as fixtures

def base():
    words,named,guard=fixtures.fixture_getter_return_chain()
    words[(source.SAVE_SITE-source.START)//4]=source.SAVE_OPCODE
    for sites in fmt.GETTER_CALLS.values():
        for pc,_,_,_ in sites:
            words[(pc-4-source.START)//4]=0xe51b0064
    proof=fmt.pin_getter_result_boolean_paths(tuple(words),named,guard)
    return words,proof

class NativeYccReceiverSourceTests(unittest.TestCase):
    def test_four_getters_read_prologue_r1_saved_slot(self):
        words,proof=base()
        report=source.trace_receiver_inputs(tuple(words),proof)
        self.assertEqual(report["recognized_getter_calls"],4)
        self.assertEqual(report["incoming_r1_saved_to_fp_offset"],-100)
        self.assertTrue(report["four_getter_r0_setup_uses_incoming_r1_frame_slot"])
        self.assertTrue(report["only_one_direct_fp_slot_store_before_getters"])
        self.assertEqual(len(report["direct_frame_slot_store_witnesses"]),1)
        for item in report["getter_receiver_evidence"]:
            self.assertEqual(item["r0_frame_slot_offset"],-100)
            self.assertTrue(item["same_slot_as_saved_incoming_r1"])
            self.assertEqual(item["r0_final_writer_kind"],"LDR_r0_from_fp_immediate")
            self.assertFalse(item["runtime_receiver_pointer_identity_verified"])
            self.assertFalse(item["native_getter_receiver_lifetime_verified"])
        self.assertFalse(report["incoming_r1_runtime_object_same_across_all_calls_proven"])
        self.assertFalse(report["native_camera_dma_cache_coherency_verified"])
        self.assertFalse(report["firmware_flash_permitted"])

    def test_different_receiver_r0_frame_slot_must_be_reported(self):
        words,proof=base()
        words[(0x34c18-source.START)//4]=0xe51b0060 # LDR r0,[fp,-96]
        got=source.trace_receiver_inputs(tuple(words),proof)
        self.assertFalse(got["four_getter_r0_setup_uses_incoming_r1_frame_slot"])
        self.assertEqual(got["getter_receiver_evidence"][1]["r0_frame_slot_offset"],-96)
        self.assertFalse(got["incoming_r1_runtime_object_same_across_all_calls_proven"])

    def test_unmodeled_final_r0_writer_not_guessed(self):
        words,proof=base()
        words[(0x34c4c-source.START)//4]=0xe1a00004 # MOV r0,r4
        got=source.trace_receiver_inputs(tuple(words),proof)
        self.assertFalse(got["four_getter_r0_setup_uses_incoming_r1_frame_slot"])
        self.assertIsNone(got["getter_receiver_evidence"][2]["r0_frame_slot_offset"])
        self.assertEqual(got["getter_receiver_evidence"][2]["r0_final_writer_kind"],
                         "UNRESOLVED_OTHER_ARM_INSTRUCTION")

    def test_prologue_parameter_save_change_is_rejected(self):
        words,proof=base()
        words[(source.SAVE_SITE-source.START)//4]=0xe50b0064 # STR r0,[fp,-100]
        with self.assertRaisesRegex(ValueError,"prologue"):
            source.trace_receiver_inputs(tuple(words),proof)

    def test_extra_direct_slot_writer_prevents_unique_source_claim(self):
        words,proof=base()
        words[(0x34b64-source.START)//4]=0xe50b2064 # STR r2,[fp,-100]
        got=source.trace_receiver_inputs(tuple(words),proof)
        self.assertFalse(got["only_one_direct_fp_slot_store_before_getters"])
        self.assertEqual(len(got["direct_frame_slot_store_witnesses"]),2)
        self.assertFalse(got["indirect_stack_alias_writes_excluded"])

    def test_invalid_or_forged_getter_proof_rejected(self):
        words,proof=base()
        for changed in (dict(proof,four_local_getter_equality_tests=3),
                        dict(proof,four_native_imported_getter_calls_and_r0_r3_paths_verified=False)):
            with self.assertRaises(ValueError):
                source.trace_receiver_inputs(tuple(words),changed)
        forged=dict(proof)
        forged["getters"]={k:[dict(x) for x in val] for k,val in proof["getters"].items()}
        forged["getters"]["eImgYCCType"][0]["imported_callsite"]="0x00034c50"
        with self.assertRaisesRegex(ValueError,"mapping"):
            source.trace_receiver_inputs(tuple(words),forged)
        with self.assertRaisesRegex(ValueError,"bounded ARM"):
            source.trace_receiver_inputs(tuple(words[:-1]),proof)

if __name__=="__main__":
    unittest.main(verbosity=2)
