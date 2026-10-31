#!/usr/bin/env python3
"""Synthetic offline UI39 helper-to-preference chain tests; no firmware bytes."""
from __future__ import annotations
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_ui39_pref_key_chain_audit as chain

BASE=0x1000
GET_VALUE=0x1800
END=0x2000
SYNTHETIC_KEYS=[868]+list(range(236,281,4))

def put(binary:bytearray,pc:int,opcode:int):
    struct.pack_into("<I",binary,pc-BASE,opcode)

def branch(pc:int,target:int,link:bool=False)->int:
    rel=(target-pc-8)&0xffffffff
    if rel&3:raise ValueError("Unaligned ARM synthetic branch")
    return 0xea000000 | ((1<<24) if link else 0) | ((rel>>2)&0xffffff)

def fixture():
    blob=bytearray(END-BASE)
    entry=0x1100
    fixed={
      0x00:0xe92d4800,0x04:0xe28db004,0x08:0xe24dd008,
      0x0c:0xe50b0008,0x10:0xe3a00025,
      0x18:0xe1a03000,0x1c:0xe2433001,
      0x20:0xe353000b,0x24:0x979ff103,
      0x28:0xea000023,0xc0:0xe1a00003,
      0xc4:0xe24bd004,0xc8:0xe8bd8800,
      0xbc:0xe3a03034,
    }
    for d,word in fixed.items():put(blob,entry+d,word)
    put(blob,entry+0x14,branch(entry+0x14,GET_VALUE,True))
    for i in range(12):
        at=entry+0x5c+i*8
        put(blob,entry+0x2c+i*4,at)
        put(blob,at,0xe3a03000|(53+i))
        put(blob,at+4,branch(at+4,entry+0xc0))
    return blob,[(BASE,len(blob),0)],entry

def preference():
    return {"simple_case_key_values":[
        {"case_index":index,"local_pref_key_immediate":value}
        for index,value in zip(range(52,65),SYNTHETIC_KEYS)
    ]}

class StaticUI39ChainTests(unittest.TestCase):
    def test_twelve_checked_values_and_default_52(self):
        blob,segs,entry=fixture()
        r=chain.parse_helper(blob,segs,entry,GET_VALUE)
        self.assertEqual(r["helper_reads_ui_item_numeric"],37)
        self.assertEqual(r["helper_branch_count"],12)
        self.assertEqual(r["conditional_return_mapping"],[
            {"ui_get_value_37_result":i,"db_selector":52+i}
            for i in range(1,13)])
        self.assertEqual(r["other_value_default_db_selector"],52)
        self.assertTrue(r["does_not_prove_picture_wizard_item"])

    def test_thirteen_db_selectors_join_to_reference_keys(self):
        blob,segs,entry=fixture()
        r=chain.join_preference_keys(
            chain.parse_helper(blob,segs,entry,GET_VALUE),preference())
        mapping=r["db_selector_to_syntactic_pref_set_long_key"]
        self.assertEqual([x["db_selector"] for x in mapping],list(range(52,65)))
        self.assertEqual([x["syntactic_pref_set_long_key"] for x in mapping],
                         SYNTHETIC_KEYS)
        self.assertFalse(r["picture_wizard_specific_preference_key_verified"])
        self.assertFalse(r["hardware_isp_effect_verified"])

    def test_missing_preference_case_refused(self):
        blob,segs,entry=fixture()
        report=preference()
        report["simple_case_key_values"].pop()
        with self.assertRaisesRegex(ValueError,"no checked"):
            chain.join_preference_keys(chain.parse_helper(
                blob,segs,entry,GET_VALUE),report)

    def test_conflicting_key_and_duplicate_case_refused(self):
        blob,segs,entry=fixture()
        h=chain.parse_helper(blob,segs,entry,GET_VALUE)
        report=preference()
        report["simple_case_key_values"][1]["local_pref_key_immediate"]=555
        with self.assertRaisesRegex(ValueError,"do not match"):
            chain.join_preference_keys(h,report)
        report=preference()
        report["simple_case_key_values"].append(report["simple_case_key_values"][2])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            chain.join_preference_keys(h,report)

    def test_corrupt_helper_ui_selector_refused(self):
        blob,segs,entry=fixture()
        put(blob,entry+0x10,0xe3a00024)
        with self.assertRaisesRegex(ValueError,"Unexpected UI39 helper"):
            chain.parse_helper(blob,segs,entry,GET_VALUE)

    def test_changed_helper_call_target_refused(self):
        blob,segs,entry=fixture()
        put(blob,entry+0x14,branch(entry+0x14,GET_VALUE+4,True))
        with self.assertRaisesRegex(ValueError,"does not call"):
            chain.parse_helper(blob,segs,entry,GET_VALUE)

    def test_invalid_jump_table_pointer_and_return_refused(self):
        blob,segs,entry=fixture()
        put(blob,entry+0x2c+4,0x1af0)
        with self.assertRaisesRegex(ValueError,"12-entry"):
            chain.parse_helper(blob,segs,entry,GET_VALUE)
        blob,segs,entry=fixture()
        put(blob,entry+0x5c,0xe3a030ff)
        with self.assertRaisesRegex(ValueError,"selector constant"):
            chain.parse_helper(blob,segs,entry,GET_VALUE)
        blob,segs,entry=fixture()
        put(blob,entry+0x60,branch(entry+0x60,entry+0xb8))
        with self.assertRaisesRegex(ValueError,"common epilogue"):
            chain.parse_helper(blob,segs,entry,GET_VALUE)

    def test_bad_input_refused_and_no_camera_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"missing.elf"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(chain.main(["--elf",str(path)]),2)
            path.write_bytes(b"not an ARM ELF")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(chain.main(["--elf",str(path)]),2)
            alias=Path(folder)/"symlink.elf"
            alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,"local ARM32"):
                chain.inspect(alias)

if __name__=="__main__":
    unittest.main(verbosity=2)
