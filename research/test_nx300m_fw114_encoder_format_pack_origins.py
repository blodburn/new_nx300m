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
