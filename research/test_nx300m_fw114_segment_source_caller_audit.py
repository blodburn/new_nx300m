#!/usr/bin/env python3
"""Host-only synthetic checks: bounded static ARM direct-call discovery."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_segment_source_caller_audit as audit


class QSourceCallers(unittest.TestCase):
    def test_arm_word_stores_to_nonstack_plus8(self):
        v=audit.decode_record_word_store_plus8(0xe5832008)
        self.assertEqual(v["base"],"r3")
        self.assertEqual(v["source"],"r2")
        self.assertEqual(v["offset"],8)
        self.assertFalse(v["conditional"])
        self.assertFalse(v["base_is_get_data_record_proven"])
        conditional=audit.decode_record_word_store_plus8(0x15832008)
        self.assertTrue(conditional["conditional"])
        for opcode in (0xe583200c,0xe5932008,0xe5c32008,
                       0xe58d2008,0xe58b2008,0xe5a32008,
                       0xe5832004,0xe5032008,0xe7832008,
                       0xf5832008):
            with self.subTest(opcode=hex(opcode)):
                self.assertIsNone(audit.decode_record_word_store_plus8(opcode))
        for word in (None,True,-1,0x100000000,"0xe5832008"):
            with self.assertRaises(ValueError):
                audit.decode_record_word_store_plus8(word)

    def test_exact_r1_to_Q_prologue_and_fail_closed(self):
        words=[0xe1a00000]*(audit.TARGET_SIZE//4)
        for pc,opcode in audit.Q_ENTRY_OPCODES.items():
            words[(pc-audit.TARGET_START)//4]=opcode
        proof=audit.verify_source_q_incoming(tuple(words))
        self.assertEqual(proof["source_q_is_input_register"],"r1")
        self.assertEqual(proof["q_field_plus8_load_pc"],"0x0000b188")
        self.assertFalse(proof["q_source_value_positive_proven"])
        self.assertFalse(proof["incoming_r1_callers_or_execution_proven"])
        for pc in audit.Q_ENTRY_OPCODES:
            altered=list(words)
            altered[(pc-audit.TARGET_START)//4]=0xe1a00000
            with self.subTest(pc=pc),self.assertRaises(ValueError):
                audit.verify_source_q_incoming(tuple(altered))

    def test_indirect_blx_and_pointer_literal_guards(self):
        self.assertEqual(audit.arm_blx_register(0xe12fff33)["via_register"],"r3")
        self.assertIsNone(audit.arm_blx_register(0xe12fff13))
        self.assertIsNone(audit.arm_blx_register(0xeb000001))
        self.assertIsNone(audit.arm_blx_register(0xf12fff33))
        with self.assertRaises(ValueError):
            audit.arm_blx_register(True)
        import struct
        mem=struct.pack("<IIIII",0x1234,audit.TARGET_START,
                        audit.TARGET_START+1,0,0x200)
        literals=audit.aligned_literal_refs(
            mem,[(0x3000,len(mem),0)],audit.TARGET_START)
        self.assertEqual([x["elf_vaddr"] for x in literals],
                         ["0x00003004","0x00003008"])
        self.assertFalse(literals[0]["literal_referenced_by_code_proven"])
        lines="0010 R_ARM_ABS32 0000b0e0 sysmmap_segment_update_empty_seg\\n"
        self.assertEqual(len(audit.named_native_relocations(lines)),1)

    def test_all_defined_native_functions_are_deduplicated(self):
        sample="""Symbol table '.symtab':
   1: 0000b0e0   244 FUNC GLOBAL DEFAULT   12 sysmmap_segment_update_empty_seg
   2: 00004000   100 FUNC LOCAL DEFAULT   12 hidden_native_caller
   3: 00005000    50 FUNC GLOBAL DEFAULT  UND imported_caller
Symbol table '.dynsym':
   4: 0000b0e0   244 FUNC GLOBAL DEFAULT   12 sysmmap_segment_update_empty_seg
"""
        funcs=audit.defined_functions(sample)
        self.assertEqual(len(funcs),2)
        self.assertEqual(funcs[0]["symbol"],"hidden_native_caller")
        self.assertEqual(funcs[1]["symbol"],audit.TARGET)
        self.assertEqual(funcs[1]["size"],244)

    def test_symbol_input_has_bounds(self):
        s="\n".join("not symbol" for i in range(75002))
        with self.assertRaisesRegex(ValueError,"unbounded"):
            audit.defined_functions(s)


if __name__=="__main__":
    unittest.main(verbosity=2)
