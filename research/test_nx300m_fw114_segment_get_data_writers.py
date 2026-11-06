#!/usr/bin/env python3
"""Synthetic native ARM record-offset discovery checks (no vendor binary)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_segment_get_data_writers as module


class SegmentGetDataWriters(unittest.TestCase):
    def test_arm_ldr_str_of_exact_field12(self):
        read=module.arm_word_offset12(0xe593300c)
        self.assertEqual(read["operation"],"LDR")
        self.assertEqual(read["base_register"],"r3")
        self.assertEqual(read["value_register"],"r3")
        self.assertEqual(read["offset_bytes"],12)
        self.assertFalse(read["record_identity_confirmed"])
        write=module.arm_word_offset12(0xe583200c)
        self.assertEqual(write["operation"],"STR")
        self.assertEqual(write["value_register"],"r2")
        self.assertFalse(write["conditional"])
        cond=module.arm_word_offset12(0x1583200c)
        self.assertTrue(cond["conditional"])
        for word in (0xe5933008,0xe5934004,0xe5832008,
                     0xe783200c,0xe5c3200c,0xe5a3200c,
                     0xe513300c,0xf583200c):
            with self.subTest(word=hex(word)):
                self.assertIsNone(module.arm_word_offset12(word))
        for invalid in (-1,0x100000000,None):
            with self.assertRaises((TypeError,ValueError)):
                module.arm_word_offset12(invalid)

    def test_exact_accessor_pointer_and_writer_witnesses(self):
        words=[0xe1a00000]*(module.ACCESSOR_SIZE//4)
        for site,opcode in module.ACCESSOR_EXACT_WORDS.items():
            words[(site-module.ACCESSOR_ADDRESS)//4]=opcode
        p=module.accessor_static_pointer_witness(
            tuple(words),module.ACCESSOR_ADDRESS)
        self.assertEqual(
            p["non_null_arm_pointer_dereference"],
            "r0_return = *( *(input_r0 + 0) + 4 )")
        self.assertFalse(p["record_plus12_writer_alias_proven"])
        self.assertFalse(p["actual_camera_mapped_bytes_proven"])
        for site in module.ACCESSOR_EXACT_WORDS:
            changed=list(words)
            changed[(site-module.ACCESSOR_ADDRESS)//4]=0xe1a00000
            with self.subTest(site=site),self.assertRaises(ValueError):
                module.accessor_static_pointer_witness(
                    tuple(changed),module.ACCESSOR_ADDRESS)
        start=0xb124
        writer=[0xe1a00000]*((0xb1a8-start)//4+1)
        for site,opcode in module.EMPTY_RESET_OPCODES.items():
            writer[(site-start)//4]=opcode
        ctx=module.target_writer_context(tuple(writer),start)
        self.assertEqual(ctx["site"],"0x0000b19c")
        self.assertFalse(ctx["record_return_alias_to_writer_r3_proven"])
        self.assertFalse(ctx["stored_r2_runtime_value_observed"])
        reset=ctx["exact_empty_record_zero_reset"]
        self.assertTrue(reset["writes_zero_to_indicated_pointer_plus12"])
        self.assertEqual(reset["status_marker_byte"],0x65)
        self.assertFalse(reset["real_positive_allocation_size_initializer_found"])
        for pc in module.EMPTY_RESET_OPCODES:
            changed=list(writer)
            changed[(pc-start)//4]=0xe1a00000
            with self.subTest(pc=pc),self.assertRaises(ValueError):
                module.target_writer_context(tuple(changed),start)
        with self.assertRaises(ValueError):
            module.target_writer_context((0,0,0),0xb198)
        with self.assertRaises(ValueError):
            module.target_writer_context(tuple(writer),start+1)

    def test_mempool_plus4_changes_effective_reset_field_offset(self):
        start=module.MEMPOOL_ADDRESS
        words=[0xe1a00000]*(module.MEMPOOL_SIZE//4)
        for pc,word in module.MEMPOOL_EXACT_WORDS.items():
            words[(pc-start)//4]=word
        words[(module.MEMPOOL_GET_DATA_CALL-start)//4]=0xeb000001
        result=module.mempool_data_pointer_witness(tuple(words),start)
        self.assertEqual(result["get_data_return_plus_bytes"],4)
        self.assertEqual(result["get_data_return_plus_site"],"0x00009adc")
        self.assertEqual(
            result["non_null_return_formula"],
            "get_mempool_data(x) = get_data(x) + 4")
        self.assertEqual(result["empty_reset_effective_offset_from_get_data_return"],16)
        self.assertEqual(result["alloc_size_load_offset_from_get_data_return"],12)
        self.assertFalse(result["same_input_effective_offsets_equal"])
        self.assertFalse(
            result["get_data_input_identity_proven_across_allocator_and_reset"])
        self.assertFalse(result["runtime_pointer_alias_or_memory_overlap_excluded"])
        self.assertFalse(result["positive_size_initializer_identified"])
        for pc in module.MEMPOOL_EXACT_WORDS:
            corrupted=list(words)
            corrupted[(pc-start)//4]=0xe1a00000
            with self.subTest(pc=pc),self.assertRaises(ValueError):
                module.mempool_data_pointer_witness(tuple(corrupted),start)
        corrupted=list(words)
        corrupted[(module.MEMPOOL_GET_DATA_CALL-start)//4]=0xe1a00000
        with self.assertRaises(ValueError):
            module.mempool_data_pointer_witness(tuple(corrupted),start)
        with self.assertRaises(ValueError):
            module.mempool_data_pointer_witness(tuple(words),start+4)

    def test_symbol_rows_deduplicated(self):
        text="""Symbol table '.dynsym' contains 2 entries:
   4: 0000a114   796 FUNC GLOBAL DEFAULT   11 sysmmap_segment_alloc
   5: 00009420    28 FUNC GLOBAL DEFAULT   11 sysmmap_segment_get_data
Symbol table '.symtab' contains 3 entries:
  25: 0000a114   796 FUNC GLOBAL DEFAULT   11 sysmmap_segment_alloc
  26: 00009420    28 FUNC GLOBAL DEFAULT   11 sysmmap_segment_get_data
  27: 00001120    16 FUNC GLOBAL DEFAULT  UND sysmmap_segment_nope
"""
        funcs=module.segment_functions(text)
        self.assertEqual(len(funcs),2)
        self.assertEqual(
            next(f for f in funcs
                 if f["symbol"]==module.GET_DATA)["address"],0x9420)
        self.assertEqual(funcs[0]["symbol"],module.GET_DATA)

    def test_bounded_symbol_inventory(self):
        huge="\n".join("nonsense" for _ in range(module.MAX_SYM_LINES+2))
        with self.assertRaisesRegex(ValueError,"Unbounded"):
            module.segment_functions(huge)


if __name__=="__main__":
    unittest.main(verbosity=2)
