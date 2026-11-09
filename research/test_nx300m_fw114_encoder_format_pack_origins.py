#!/usr/bin/env python3
"""Synthetic ARM32 Y/C type/pack frame-slot provenance tests; no camera I/O."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_encoder_format_pack_origins as source

NOP = 0xe1a00000

MARSHAL = {
    0x34d20: 0xe58d9000,
    0x34d24: 0xe3a02000,
    0x34d28: 0xe58d2004,
    0x34d2c: 0xe3a02000,
    0x34d30: 0xe58d2008,
    0x34d34: 0xe51b2068,
    0x34d38: 0xe58d200c,
    0x34d3c: 0xe58da010,
    0x34d40: 0xe58d8014,
    0x34d44: 0xe58d3018,
    0x34d48: 0xe51b3028,
    0x34d4c: 0xe58d301c,
    0x34d50: 0xe51b302c,
    0x34d54: 0xe58d3020,
    0x34d58: 0xe3a03002,
    0x34d5c: 0xe58d3024,
    0x34d60: 0xe3a03e7d,
    0x34d64: 0xe58d3028,
}


def fixture():
    result = [NOP] * (source.BODY_BYTES // 4)
    for pc, op in MARSHAL.items():
        result[(pc-source.START)//4] = op
    for pc, op in {
        0x34b70: 0xe3a01001,  # MOV r1,#1
        0x34b74: 0xe50b1028,  # STR r1,[fp,-40]
        0x34b78: 0xe3a03002,  # MOV r3,#2
        0x34b7c: 0xe50b302c,  # STR r3,[fp,-44]
    }.items():
        result[(pc-source.START)//4] = op
    return result


def fixture_actual_guard_pairs():
    """Synthetic instructions pinned to six source-backed writer PCs."""
    words = fixture()
    for pc in (0x34b70, 0x34b74, 0x34b78, 0x34b7c):
        words[(pc-source.START)//4] = NOP
    for field, sites in source.PINNED_DIRECT_WRITERS.items():
        store_op = (
            0xe50b3028 if field == "eImgYCCType" else 0xe50b302c
        )
        for store_pc, value in sites:
            words[(store_pc-4-source.START)//4] = 0xe3a03000 | value
            words[(store_pc-source.START)//4] = store_op
    for guards in source.PINNED_LOCAL_BRANCH_GUARDS.values():
        for _, uxtb_pc, cmp_pc, branch_pc, branch_op, _ in guards:
            words[(uxtb_pc-source.START)//4] = source.EXPECTED_UXTB_R3_R3
            words[(cmp_pc-source.START)//4] = source.EXPECTED_CMP_R3_ZERO
            words[(branch_pc-source.START)//4] = branch_op
    return words


class EncoderYccFieldOriginTests(unittest.TestCase):
    def test_two_separate_native_stack_slot_writer_candidates(self):
        proof = source.trace_field_origins(tuple(fixture()))
        ycc = proof["fields"]["eImgYCCType"]
        pack = proof["fields"]["eImgYCCPackType"]
        self.assertEqual(ycc["stack_offset_from_fp"], -40)
        self.assertEqual(pack["stack_offset_from_fp"], -44)
        self.assertEqual(ycc["native_jpeg_argument_stack_offset"], 28)
        self.assertEqual(pack["native_jpeg_argument_stack_offset"], 32)
        self.assertEqual(ycc["direct_writer_count"], 1)
        self.assertEqual(pack["direct_writer_count"], 1)
        self.assertEqual(
            ycc["direct_frame_pointer_store_candidates"][0][
                "immediate_preceding_mov_candidate"],
            {"kind": "MOV_IMM", "immediate": 1}
        )
        self.assertEqual(
            pack["direct_frame_pointer_store_candidates"][0][
                "immediate_preceding_mov_candidate"],
            {"kind": "MOV_IMM", "immediate": 2}
        )
        for label in ("eImgYCCType", "eImgYCCPackType"):
            self.assertFalse(
                proof["fields"][label]["actual_native_enum_value_proven"]
            )
            self.assertFalse(
                proof["fields"][label]["indirect_alias_writers_excluded"]
            )
        self.assertFalse(proof["live_camera_capture_layout_proven"])
        self.assertFalse(proof["firmware_flash_permitted"])

    def test_multiple_writers_are_not_reduced_to_one_constant(self):
        words = fixture()
        words[(0x34b88-source.START)//4] = 0x150b0028  # STRNE r0,[fp,-40]
        result = source.trace_field_origins(tuple(words))
        ycc = result["fields"]["eImgYCCType"]
        self.assertEqual(ycc["direct_writer_count"], 2)
        self.assertFalse(ycc["single_direct_writer_candidate"])
        self.assertEqual(
            ycc["direct_frame_pointer_store_candidates"][1]["condition"],
            "ARM_COND_1"
        )
        self.assertFalse(ycc["actual_native_enum_value_proven"])

    def test_missing_direct_writer_remains_unresolved(self):
        words = fixture()
        words[(0x34b74-source.START)//4] = NOP
        result = source.trace_field_origins(tuple(words))
        ycc = result["fields"]["eImgYCCType"]
        self.assertEqual(ycc["direct_writer_count"], 0)
        self.assertFalse(ycc["single_direct_writer_candidate"])
        self.assertFalse(ycc["actual_native_enum_value_proven"])

    def test_six_pinned_real_native_mov_and_str_pairs(self):
        words = fixture()
        for site in (0x34b70, 0x34b74, 0x34b78, 0x34b7c):
            words[(site-source.START)//4] = NOP
        for name, entries in source.PINNED_DIRECT_WRITERS.items():
            offset = 0xe50b3028 if name == "eImgYCCType" else 0xe50b302c
            for site, value in entries:
                words[(site-4-source.START)//4] = 0xe3a03000 | value
                words[(site-source.START)//4] = offset
        proof = source.trace_field_origins(tuple(words))
        pins = source.pin_known_arm_direct_writer_values(proof)
        self.assertTrue(pins["six_native_opcodes_and_preceding_immediates_pinned"])
        for name, data in pins["pinned_fw114_115_known_direct_stores"].items():
            self.assertEqual(data["direct_store_count"], 3)
            self.assertTrue(data["direct_store_values_within_zero_or_one"])
            self.assertFalse(data["runtime_path_values_or_precedence_proven"])
        # One changed literal must fail the strict real-ELF pin.
        pc = 0x34c3c
        words[(pc-source.START)//4] = 0xe3a03002
        with self.assertRaisesRegex(ValueError, "Changed actual"):
            source.pin_known_arm_direct_writer_values(
                source.trace_field_origins(tuple(words))
            )

    def test_four_real_arm_zero_guard_edges(self):
        words = tuple(fixture_actual_guard_pairs())
        pins = source.pin_known_arm_direct_writer_values(
            source.trace_field_origins(words)
        )
        proof = source.pin_local_ycc_branch_guards(words, pins)
        self.assertEqual(proof["direct_zero_test_guard_count"], 4)
        self.assertTrue(proof["direct_beq_skip_targets_source_backed"])
        expected = {
            "eImgYCCType": ("0x00034c18", "0x00034c44"),
            "eImgYCCPackType": ("0x00034c7c", "0x00034ca8"),
        }
        for field, targets in expected.items():
            trace = proof["fields"][field]
            self.assertEqual(
                tuple(x["branch_target"]
                      for x in trace["pinned_local_beq_skip_edges"]),
                targets
            )
            self.assertEqual(
                len(trace["direct_stores_without_nearby_pinned_beq"]), 1
            )
            for edge in trace["pinned_local_beq_skip_edges"]:
                self.assertTrue(edge["branch_takes_skip_of_this_direct_store"])
                self.assertFalse(edge["runtime_r3_input_origin_proven"])
                self.assertFalse(edge["fallthrough_store_guaranteed"])
            self.assertFalse(
                trace["actual_camera_runtime_branch_outcome_proven"]
            )
        self.assertFalse(proof["live_ycc_format_or_chroma_pack_verified"])
        self.assertFalse(proof["firmware_flash_permitted"])

    def test_any_mutated_guard_instruction_fails_closed(self):
        baseline = fixture_actual_guard_pairs()
        pins = source.pin_known_arm_direct_writer_values(
            source.trace_field_origins(tuple(baseline))
        )
        for guards in source.PINNED_LOCAL_BRANCH_GUARDS.values():
            for _, uxtb_pc, cmp_pc, branch_pc, branch_op, _ in guards:
                for pc, bad in (
                    (uxtb_pc, NOP),
                    (cmp_pc, 0xe3530001),  # CMP r3,#1, not #0
                    (branch_pc, branch_op ^ 1),  # changed branch target
                ):
                    with self.subTest(pc=hex(pc), bad=hex(bad)):
                        wrong = baseline.copy()
                        wrong[(pc-source.START)//4] = bad
                        with self.assertRaisesRegex(ValueError, "Changed native"):
                            source.pin_local_ycc_branch_guards(
                                tuple(wrong), pins
                            )

    def test_beq_target_decoder_rejects_bl_ne_and_unaligned_sites(self):
        self.assertEqual(
            source.a32_beq_direct_target(0x0a000002, 0x34c08),
            0x34c18
        )
        self.assertEqual(
            source.a32_beq_direct_target(0x0afffffe, 0x1000),
            0x1000
        )
        for value, pc in (
            (0x1a000002, 0x34c08), # BNE
            (0xeb000002, 0x34c08), # BL
            (0x0a000002, 0x34c09), # unaligned
            (-1, 0x34c08),
            (True, 0x34c08),
        ):
            with self.subTest(word=value,site=pc):
                with self.assertRaises(ValueError):
                    source.a32_beq_direct_target(value, pc)

    def test_changed_native_jpeg_argument_load_rejected(self):
        words = fixture()
        words[(0x34d50-source.START)//4] = 0xe51b3028
        with self.assertRaisesRegex(ValueError, "stack source"):
            source.trace_field_origins(tuple(words))

    def test_wrong_shape_and_opcode_type_rejected(self):
        words = fixture()
        with self.assertRaisesRegex(ValueError, "code body"):
            source.trace_field_origins(tuple(words[:-1]))
        with self.assertRaisesRegex(ValueError, "code body"):
            source.trace_field_origins(tuple(words), start=source.START+4)
        words[0] = True
        with self.assertRaisesRegex(ValueError, "code body"):
            source.trace_field_origins(tuple(words))

    def test_simple_mov_only_no_shifted_or_conditional_register_claim(self):
        self.assertEqual(source.decode_arm_simple_mov(0xe3a03007,3),
                         {"kind":"MOV_IMM","immediate":7})
        self.assertEqual(source.decode_arm_simple_mov(0xe1a03004,3),
                         {"kind":"MOV_REG","source_register":"r4"})
        self.assertIsNone(source.decode_arm_simple_mov(0xe1a03184,3))
        self.assertIsNone(source.decode_arm_simple_mov(0x13a03001,3))
        self.assertIsNone(source.decode_arm_simple_mov(0xe3a02001,3))
        with self.assertRaises(ValueError):
            source.decode_arm_simple_mov(-1,3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
