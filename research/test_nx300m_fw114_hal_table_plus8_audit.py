#!/usr/bin/env python3
"""Synthetic ARM32 store-site tests; real FW evidence only in private CI."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest
import struct

sys.path.insert(0,str(Path(__file__).resolve().parent))
from nx300m_fw114_hal_table_plus8_audit import candidate_mem_store_sites, resolve_initializer_four_fields

class HalTableField8Tests(unittest.TestCase):
    def test_immediate_arm_str_offset8(self):
        # STR r2, [r3, #8]; STR r4,[r0,#8]; other offset is excluded
        code=(0xe5832008,0xe5804008,0xe583200c,0xe5932008)
        report=candidate_mem_store_sites(code,0x1000)
        self.assertEqual(len(report),2)
        self.assertEqual(report[0]["site"],"0x00001000")
        self.assertEqual(report[0]["base_register"],"r3")
        self.assertEqual(report[0]["value_register"],"r2")
        self.assertFalse(report[0]["proven_tDscHal_plus8_write"])
        self.assertFalse(report[0]["proven_hal_encoder_callback_value"])

    def test_stack_argument_store_does_not_prove_tDscHal(self):
        report=candidate_mem_store_sites((0xe58d0008,),0x1000)
        self.assertEqual(report[0]["base_register"],"r13")
        self.assertFalse(report[0]["proven_tDscHal_plus8_write"])

    def test_non_store_or_different_offset_excluded(self):
        report=candidate_mem_store_sites(
            (0xe5932008,0xe5832004,0xe5832000,0xe1a00000),0x1000
        )
        self.assertEqual(report,[])

    def test_realistic_arm_pic_got_to_jpeg_hal_stacked_structure(self):
        start=0x00053f80
        base=0x0006ce00
        raw=bytearray(0x300)
        words=[0xe1a00000]*55
        words[(0x53f88-start)//4]=0xe59f40d0
        words[(0x53f8c-start)//4]=0xe08f4004
        for i,site in enumerate((0x53fc8,0x53fd4,0x53fe0,0x53fec)):
            j=(site-start)//4
            lit=(0x5404c+4*i)-(site+8)
            words[j]=0xe59f3000|lit
            words[j+1]=0xe7943003
            words[j+2]=0xe50b3000|(28-4*i)
        words[(0x54004-start)//4]=0xe24b301c
        for i,w in enumerate(words):
            struct.pack_into("<I",raw,4*i,w)
        struct.pack_into("<I",raw,0x54060-start,(base-(0x53f8c+8))&0xffffffff)
        offsets=(0x10,0x40,0x98,0xc0)
        reloc={}
        for i,index in enumerate(offsets):
            struct.pack_into("<I",raw,0x5404c-start+4*i,index)
            reloc[base+index]={
                "relocation_type":"R_ARM_GLOB_DAT",
                "mangled_symbol": (
                    "_ZN10DscJfifHal6EncodeEfoo"
                    if i==2 else f"_Z3fn{i}v"),
                "symbol_value":"0x00029830" if i==2 else "0x00021111",
            }
        segments=[(start,len(raw),0)]
        result=resolve_initializer_four_fields(
            bytes(raw),segments,tuple(words),start,reloc
        )
        self.assertTrue(result[
            "tDscHal_plus8_static_reloc_symbol_is_DscJfifHal_Encode"])
        self.assertEqual(
            [x["tDscHal_field_offset"] for x in result["fields"]],
            [0,4,8,12]
        )
        self.assertEqual(result["fields"][2]["got_slot"],"0x0006ce98")
        self.assertFalse(result["hardware_callback_invocation_observed"])
        self.assertFalse(result["flash_allowed"])
        damaged=reloc.copy()
        del damaged[0x6ce98]
        with self.assertRaisesRegex(ValueError,"Unresolved"):
            resolve_initializer_four_fields(
                bytes(raw),segments,tuple(words),start,damaged
            )
        damaged=reloc.copy()
        damaged[0x6ce98]=dict(reloc[0x6ce98],
                               mangled_symbol="_ZN7DscJfif10JpegDecodeEv")
        with self.assertRaisesRegex(ValueError,"HAL Encode"):
            resolve_initializer_four_fields(
                bytes(raw),segments,tuple(words),start,damaged
            )
        wrong=words.copy()
        wrong[(0x54004-start)//4]=0xe24b3018
        with self.assertRaisesRegex(ValueError,"fourth ARM argument"):
            resolve_initializer_four_fields(
                bytes(raw),segments,tuple(wrong),start,reloc
            )

    def test_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"Unbounded"):
            candidate_mem_store_sites((0xe5832008,)*41,0x1000)

if __name__=="__main__":
    unittest.main(verbosity=2)
