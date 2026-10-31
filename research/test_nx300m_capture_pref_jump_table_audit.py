#!/usr/bin/env python3
"""Synthetic NX300M Capture DB table fixtures; no Samsung firmware bytes."""
from __future__ import annotations
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_capture_pref_jump_table_audit as audit

BASE=0x1000
FUNC_SIZE=0x1300
BLOB_SIZE=0x1500
PREF_SET=0x6000
PREF_GET=0x6100
DEBUG=0x6200
PLT={PREF_SET:"pref_set_long",PREF_GET:"pref_get_long",
     DEBUG:"slpcam_print_info"}
SKIP={6,19,180,*range(187,196)}

def bl(pc:int,target:int)->int:
    delta=(target-pc-8)&0xffffffff
    assert delta%4==0
    return 0xeb000000|((delta>>2)&0xffffff)

def put(data:bytearray,addr:int,word:int):
    struct.pack_into("<I",data,addr-BASE,word)

def synthetic():
    b=bytearray(BLOB_SIZE)
    header=[
        0xe92d4800,0xe28db004,0xe24dd018,0xe50b0008,0xe50b100c,
        0xe51b3008,0xe2433001,0xe35300cc,0x979ff103,0xea0004b1,
    ]
    for i,op in enumerate(header):put(b,BASE+4*i,op)
    table=BASE+0x28
    code=table+205*4
    special=code+192*20
    default=special+0x94
    simple_idx=0
    for idx in range(1,206):
        if idx in SKIP:addr=default
        elif idx==124:addr=special
        else:
            addr=code+simple_idx*20
            simple_idx+=1
            ops=(0xe3a00001,0xe3001000|idx,0xe51b200c,
                 bl(addr+12,PREF_SET),0xea000000)
            for j,v in enumerate(ops):put(b,addr+4*j,v)
        put(b,table+(idx-1)*4,addr)
    assert simple_idx==192
    for off,dest in ((0x24,PREF_SET),(0x34,PREF_GET),
                     (0x70,DEBUG),(0x78,PREF_GET),(0x88,0x6300)):
        put(b,special+off,bl(special+off,dest))
    for i,w in enumerate((0xe1a00000,0xe24bd004,0xe8bd8800)):
        put(b,default+i*4,w)
    return b,[(BASE,len(b),0)],special,default

class CapturePreferencesTableTests(unittest.TestCase):
    def test_reference_table_and_calls_proven_statistically(self):
        b,seg,_,_=synthetic()
        x=audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)
        self.assertEqual(x["jump_table_entries"],205)
        self.assertEqual(x["simple_pref_set_long_cases"],192)
        self.assertEqual(x["verified_pref_set_long_calls_in_function"],193)
        self.assertEqual(x["verified_pref_get_long_calls_in_special_case"],2)
        self.assertEqual(len(x["default_noop_case_indices"]),12)
        self.assertEqual(x["exceptional_case_index"],124)
        self.assertEqual(x["jump_table_unique_block_targets"],194)
        self.assertTrue(x["reference_pattern_fully_checked"])
        self.assertFalse(x["picture_wizard_specific_db_key_identified"])
        self.assertFalse(x["runtime_persistent_write_proven"])
        self.assertFalse(x["capture_ipc_or_isp_execution_proven"])
        self.assertFalse(x["original_firmware_114_abi_verified"])
        self.assertFalse(x["device_flash_or_memory_patch_permitted"])

    def test_jump_table_entries_must_be_mapped_to_function(self):
        b,seg,_,_=synthetic()
        put(b,BASE+0x28+4*3,0x7fffffff)
        with self.assertRaisesRegex(ValueError,"invalid or noncode"):
            audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)

    def test_prologue_or_selector_change_refused(self):
        for offset in (0x18,0x1c,0x20,0x24):
            b,seg,_,_=synthetic()
            put(b,BASE+offset,0)
            with self.assertRaisesRegex(ValueError,"prologue"):
                audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)

    def test_missing_preference_plt_symbol_fails_closed(self):
        b,seg,_,_=synthetic()
        with self.assertRaisesRegex(ValueError,"Ambiguous or missing"):
            audit.classify_table(b,seg,BASE,FUNC_SIZE,
                {PREF_SET:"pref_get_long",PREF_GET:"pref_get_long",
                 DEBUG:"slpcam_print_info"})

    def test_bl_wrong_target_fails_reference_pattern(self):
        b,seg,_,_=synthetic()
        first=BASE+0x28+205*4
        put(b,first+12,bl(first+12,PREF_GET))
        with self.assertRaisesRegex(ValueError,"classification"):
            audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)

    def test_special_pref_get_calls_must_be_verified(self):
        b,seg,special,_=synthetic()
        put(b,special+0x78,0xe1a00000)
        with self.assertRaisesRegex(ValueError,"Special-case"):
            audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)

    def test_default_block_exact_identity_matters(self):
        b,seg,_,default=synthetic()
        put(b,default,0xeb000000)
        with self.assertRaisesRegex(ValueError,"Default return block"):
            audit.classify_table(b,seg,BASE,FUNC_SIZE,PLT)

    def test_parse_jump_slot_relocations_only(self):
        row=(
          "Relocation section '.rel.dyn' at offset 0x0 contains 1 entry:\n"
          "00111111  00000015 R_ARM_GLOB_DAT        00006000 ignored\n"
          "Relocation section '.rel.plt' at offset 0x40 contains 3 entries:\n"
          "0001a100  00098616 R_ARM_JUMP_SLOT        00006000 pref_set_long\n"
          "0001a104  00159e16 R_ARM_JUMP_SLOT        00006100 pref_get_long\n"
          "0001a108  0010fd16 R_ARM_JUMP_SLOT        00006200 slpcam_print_info\n"
        )
        self.assertEqual(audit.plt_symbols(row),PLT)
        with self.assertRaisesRegex(ValueError,"Missing JUMP_SLOT"):
            audit.plt_symbols("Relocation section '.rel.plt'\n(no symbols)")

if __name__=="__main__":
    unittest.main(verbosity=2)
