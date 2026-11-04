#!/usr/bin/env python3
"""Synthetic ARM words and ELF metadata only; real firmware in ephemeral CI."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_sif_virtual_dispatch as audit

BASE=0x1000
def code(words):
    buf=bytearray(b"\x00"*512)
    for i,word in enumerate(words):
        struct.pack_into("<I",buf,i*4,word)
    return bytes(buf)


class FirmwareVirtualDispatchTests(unittest.TestCase):
    def test_arm_blx_register_and_near_vtable_load_syntax(self):
        # LDR r3,[r0]; LDR r3,[r3,#16]; BLX r3.
        words=[0xe5903000,0xe5933010,0xe12fff33,0xe12fff1e]
        result=audit.scan_indirect(code(words),[(BASE,512,0)],BASE,len(words)*4)
        self.assertEqual(result["BLX_register"],1)
        self.assertEqual(result["BX_register_tail_candidate"],0)
        self.assertEqual(result["observed_indirect_branch_candidates"],1)
        call=result["sites"][0]
        self.assertEqual(call["site_address"],"0x00001008")
        self.assertEqual(call["register"],"r3")
        self.assertTrue(call["two_load_chain_candidate"])
        self.assertEqual([d["byte_offset"] for d in call["nearby_register_loads"]],
                         [16,0])
        self.assertFalse(call["vtable_target_identity_proven"])
        self.assertFalse(result["runtime_vtable_target_proven"])

    def test_indirect_tail_and_indirect_pc_are_not_function_call_proofs(self):
        words=[0xe590f014,0xe12fff11,0xe12fff1e,0xe1a0f00e]
        result=audit.scan_indirect(code(words),[(BASE,512,0)],BASE,len(words)*4)
        self.assertEqual(result["BLX_register"],0)
        self.assertEqual(result["BX_register_tail_candidate"],1)
        self.assertEqual(result["LDR_PC_indirect_tail_candidate"],1)
        self.assertEqual(result["observed_indirect_branch_candidates"],2)

    def test_invalid_forged_arm_blx_immediate_not_register(self):
        # BLX immediate has condition=1111, do not treat as BLX register.
        for word in (0xfa000000,0xe1a0f00e,0xe12fff1e):
            self.assertIsNone(audit.decode_indirect(word))

    def test_ldr_decode_immediate_load_not_store_or_literal(self):
        self.assertEqual(audit.decode_ldr_immediate(0xe5933010),
                         {"dst":3,"base":3,"offset":16})
        self.assertEqual(audit.decode_ldr_immediate(0xe5133010),
                         {"dst":3,"base":3,"offset":-16})
        for x in (0xe5833010,0xe1a03001,0xe5933010&~(1<<20)):
            self.assertIsNone(audit.decode_ldr_immediate(x))

    def test_missing_register_provenance_stays_unproven(self):
        words=[0xe1a00000,0xe1a00000,0xe12fff33]
        result=audit.scan_indirect(code(words),[(BASE,512,0)],BASE,len(words)*4)
        self.assertEqual(result["BLX_register"],1)
        self.assertFalse(result["sites"][0]["two_load_chain_candidate"])
        self.assertEqual(result["sites"][0]["nearby_register_loads"],[])

    def test_symbol_metadata_and_bounded_relocations(self):
        objects=(
            "     5: 0006c1b8    16 OBJECT  GLOBAL DEFAULT   12 _ZTV7DscJfif\n"
            "     6: 00028a88   456 FUNC    GLOBAL DEFAULT   12 _ZN7DscJfif10JpegEncodeER7sJpegOpb\n"
        )
        index=audit.symbol_index(objects)
        item=audit.select(index,"vtable for DscJfif","OBJECT")
        self.assertEqual(item["address"],0x6c1b8)
        self.assertEqual(item["size"],16)
        reloc=audit.relocations(
            "Relocation section '.rel.dyn' ...\n"
            "0006c1c0  00000017 R_ARM_RELATIVE\n"
            "0006c1c4  00000017 R_ARM_RELATIVE\n"
        )
        self.assertEqual(reloc[0x6c1c0],"R_ARM_RELATIVE")
        self.assertEqual(reloc[0x6c1c4],"R_ARM_RELATIVE")
        with self.assertRaises(ValueError):
            audit.relocations("No relocations")

    def test_arm_abs32_zero_addend_resolved_by_relocation_symbol(self):
        # Shared object vtable slots can contain zero before the dynamic
        # loader resolves their R_ARM_ABS32 target symbol. This is not NULL.
        text=(
            "Relocation section '.rel.dyn' at offset 0x0 contains 2 entries:\n"
            "0006c1bc  00010002 R_ARM_ABS32 0006c1c8 _ZTI7DscJfif\n"
            "0006c1c4  00020002 R_ARM_ABS32 00028a88 "
            "_ZN7DscJfif10JpegEncodeER7sJpegOpb\n"
        )
        d=audit.relocation_symbol_targets(text)
        self.assertEqual(d[0x6c1c4]["mangled_symbol"],
                         "_ZN7DscJfif10JpegEncodeER7sJpegOpb")
        self.assertEqual(d[0x6c1c4]["symbol_value"],"0x00028a88")
        self.assertEqual(d[0x6c1bc]["relocation_type"],"R_ARM_ABS32")
        self.assertEqual(d[0x6c1bc]["mangled_symbol"],"_ZTI7DscJfif")

    def test_relocation_target_conflict_is_rejected(self):
        text=(
            "0006c1c4  00020002 R_ARM_ABS32 00028a88 A\n"
            "0006c1c4  00030002 R_ARM_ABS32 00028a88 B\n"
        )
        with self.assertRaisesRegex(ValueError,"Conflicting relocations"):
            audit.relocation_symbol_targets(text)

    def test_function_or_vtable_rejected_if_missing_or_ambiguous(self):
        index={
            "vtable for DscJfif":{"address":0x6c1b8,"size":16,"kind":"OBJECT"},
            "vtable for DscJfif extra":{"address":0x6c200,"size":16,"kind":"OBJECT"},
        }
        with self.assertRaisesRegex(ValueError,"Missing or overloaded"):
            audit.select(index,"vtable for DscJfif","OBJECT")
        with self.assertRaisesRegex(ValueError,"Missing or overloaded"):
            audit.select({},"DscJfif::JpegEncode(","FUNC")

    def test_unaligned_or_unbounded_functions_reject(self):
        for address,size in ((BASE+2,16),(BASE,0),(BASE,65540),(BASE,17)):
            with self.subTest(address=address,size=size),self.assertRaises(ValueError):
                audit.scan_indirect(bytes(128),[(BASE,128,0)],address,size)


if __name__=="__main__":
    unittest.main(verbosity=2)
