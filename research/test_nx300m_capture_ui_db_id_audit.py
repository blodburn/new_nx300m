#!/usr/bin/env python3
"""Synthetic fixture tests for conservative Capture UI-to-DB ID switch scan."""
from __future__ import annotations
import io
import contextlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_capture_ui_db_id_audit as audit

BASE=0x1000
SIZE=0xD00
BLOB_SIZE=0x1400
HELPERS={3,9,10,23,26,27,28,30,38,39,40,41,42,43,55,75}
COND={80,83}

def bl(site:int,target:int)->int:
    rel=(target-site-8)&0xffffffff
    assert (rel&3)==0
    return 0xeb000000|((rel>>2)&0xffffff)

def put(data,pc,word):
    struct.pack_into("<I",data,pc-BASE,word)

def synthetic():
    buffer=bytearray(BLOB_SIZE)
    for delta,value in {
        0x30:0xe51b3008,0x34:0xe2433003,
        0x38:0xe35300d0,0x3c:0x979ff103,
    }.items():
        put(buffer,BASE+delta,value)
    table_start=BASE+0x44
    code_start=table_start+209*4
    other=[i for i in range(3,212) if i not in HELPERS and i not in COND]
    defaults=set(other[:102])
    assert len(defaults)==102
    pos=code_start
    cases={}
    for idx in range(3,212):
        if idx in defaults:continue
        addr=pos;pos+=20
        if idx in HELPERS:
            words=[0xe51b300c,0xe1a00003,bl(addr+8,0x3000),
                   0xe1a03000,0xea000000]
        elif idx in COND:
            words=[0xe3a00024,bl(addr+4,0x3100),0xe1a03000,
                   0xe3530002,0x0a000000]
        else:
            words=[0xe3a03000|(idx%255),0xea000000,0,0,0]
        for i,w in enumerate(words):put(buffer,addr+4*i,w)
        cases[idx]=addr
    default=pos
    for i,w in enumerate((0xe3a03000,0xe1a00003,0xe24bd004,0xe8bd8800)):
        put(buffer,default+i*4,w)
    for idx in range(3,212):
        addr=default if idx in defaults else cases[idx]
        put(buffer,table_start+(idx-3)*4,addr)
    return buffer,[(BASE,len(buffer),0)],cases,default

class UIToDbIdentifierTests(unittest.TestCase):
    def test_all_209_entries_and_unknown_semantics(self):
        b,segs,_,_=synthetic()
        result=audit.inspect_switch(b,segs,BASE,SIZE)
        self.assertEqual(result["switch_entry_count"],209)
        self.assertEqual(result["distinct_case_targets"],108)
        self.assertEqual(result["case_kind_counts"],
            {"default_zero":102,"helper_call":16,
             "constant_return":89,"conditional_helper":2})
        self.assertEqual(result["numeric_index_39_case_kind"],"helper_call")
        self.assertFalse(result["picture_wizard_specific_ui_index_verified"])
        self.assertFalse(result["helper_to_preference_key_mapping_verified"])
        self.assertFalse(result["picture_wizard_preference_key_verified"])
        self.assertFalse(result["original_firmware_114_abi_verified"])
        self.assertFalse(result["device_flash_or_memory_patch_permitted"])

    def test_first_and_last_numeric_indices(self):
        b,segs,_,_=synthetic()
        x=audit.inspect_switch(b,segs,BASE,SIZE)
        self.assertEqual(x["selector_first_numeric_index"],3)
        self.assertEqual(x["selector_last_numeric_index"],211)

    def test_changed_table_prologue_refused(self):
        for off in (0x34,0x38,0x3c):
            b,segs,_,_=synthetic()
            put(b,BASE+off,0)
            with self.assertRaisesRegex(ValueError,"prologue"):
                audit.inspect_switch(b,segs,BASE,SIZE)

    def test_table_target_outside_function_refused(self):
        b,segs,_,_=synthetic()
        put(b,BASE+0x44+9*4,0x888888)
        with self.assertRaisesRegex(ValueError,"Invalid UI->DB jump"):
            audit.inspect_switch(b,segs,BASE,SIZE)

    def test_wrong_default_opcode_refused(self):
        b,segs,_,default=synthetic()
        put(b,default+4,0xe1a02003)
        with self.assertRaisesRegex(ValueError,"default-zero"):
            audit.inspect_switch(b,segs,BASE,SIZE)

    def test_wrong_conditional_helper_call_refused(self):
        b,segs,cases,_=synthetic()
        addr=cases[80]
        put(b,addr+4,0xe1a00000)
        with self.assertRaisesRegex(ValueError,"Unrecognized conditional helper"):
            audit.inspect_switch(b,segs,BASE,SIZE)

    def test_index_39_must_map_to_helper(self):
        b,segs,cases,_=synthetic()
        addr=cases[39]
        put(b,addr,0xe3a03001)
        with self.assertRaises(ValueError):
            audit.inspect_switch(b,segs,BASE,SIZE)

    def test_reject_nonelf_without_any_firmware_execution(self):
        with tempfile.TemporaryDirectory(prefix="nx-pw-db-id-") as folder:
            path=Path(folder)/"broken.elf"
            path.write_bytes(b"wrong executable")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--elf",str(path)]),2)
            alias=Path(folder)/"link.elf"
            alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,"bounded local ELF"):
                audit.inspect(alias)

if __name__=="__main__":
    unittest.main(verbosity=2)
