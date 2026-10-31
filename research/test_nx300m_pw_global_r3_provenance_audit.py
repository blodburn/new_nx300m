#!/usr/bin/env python3
"""Synthetic ARM BSS provenance tests; zero vendor code or camera writes."""
from __future__ import annotations
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_pw_global_r3_provenance_audit as proof

BASE=0x1000
HANDLER=0x1100
SETTER=0x2000
BSS=0x4da0b4

def instruction_branch(site:int,target:int)->int:
    offset=(target-site-8)&0xffffffff
    assert offset&3==0
    return 0xeb000000|((offset>>2)&0xffffff)

def synthetic():
    blob=bytearray(0x2000)
    def put(pc:int,instruction:int)->None:
        struct.pack_into("<I",blob,pc-BASE,instruction)
    d=HANDLER+0x5d0
    c=HANDLER+0x604
    words={
        d-24:0xe30a30b4,d-20:0xe340304d,d-16:0xe5933000,
        d-12:0xe3a00005,d-8:0xe3a01004,d-4:0xe3a02027,
        c-16:0xe3a00002,c-12:0xe3a01004,
        c-8:0xe3a02027,c-4:0xe3a03000,
    }
    for pc,value in words.items():put(pc,value)
    put(d,instruction_branch(d,SETTER))
    put(c,instruction_branch(c,SETTER))
    return blob,[(BASE,len(blob),0)],put

class GlobalR3SourceTests(unittest.TestCase):
    def test_movw_movt_address_reconstruction(self):
        self.assertEqual(proof.imm16(0xe30a30b4),0xa0b4)
        self.assertEqual(proof.imm16(0xe340304d),0x4d)
        self.assertEqual(proof.movw_movt_address(0xe30a30b4,0xe340304d),
                         (3,BSS))

    def test_reject_different_register_and_opcode(self):
        self.assertIsNone(proof.movw_movt_address(0xe30a30b4,0xe340204d))
        self.assertIsNone(proof.movw_movt_address(0xe1a03002,0xe340304d))
        self.assertIsNone(proof.movw_movt_address(0xe30a30b4,0xe1a03002))

    def test_direct_access_discrimination(self):
        self.assertEqual(proof.access_kind(0xe5933000,3),"direct_read")
        self.assertEqual(proof.access_kind(0xe5832000,3),"direct_write")
        self.assertEqual(proof.access_kind(0xe3a02000,3),"unresolved")
        self.assertEqual(proof.access_kind(0xe5933004,3),"unresolved")
        self.assertEqual(proof.access_kind(0x05933000,3),"unresolved")

    def test_global_scan_counts_read_write_deferred(self):
        blob,segs,put=synthetic()
        addresses=[0x1010,0x1028,0x1040]
        for pc,last in zip(addresses,(0xe5933000,0xe5832000,0xe3a02000)):
            put(pc,0xe30a30b4)
            put(pc+4,0xe340304d)
            put(pc+8,last)
        funcs=[(0x1000,0x100,"TestPWState::handle()"),
               (HANDLER,0x900,"TestPWState::slider()")]
        r=proof.scan_global(blob,segs,funcs,BSS)
        self.assertEqual(r["total_movw_movt_global_references"],4)
        self.assertEqual(r["access_kind_counts"],
            {"direct_read":2,"direct_write":1,"unresolved":1})
        self.assertFalse(r["reference_static_access_pattern_verified"])

    def test_both_pw_event_calls_and_dynamic_register(self):
        blob,segs,_=synthetic()
        r=proof.verify_calls(blob,segs,HANDLER,SETTER,BSS)
        self.assertEqual(r["dynamic_event_r0_r1_r2"],[5,4,39])
        self.assertEqual(r["clear_event_r0_r1_r2_r3"],[2,4,39,0])
        self.assertFalse(r["dynamic_event_r3_runtime_value_known"])
        self.assertTrue(r["both_events_call_gui_set_system_value"])

    def test_reject_broken_event_immediate_or_callee(self):
        for pc,val in ((HANDLER+0x5d0-4,0xe3a02026),
                       (HANDLER+0x604-4,0xe3a03001),
                       (HANDLER+0x5d0,instruction_branch(HANDLER+0x5d0,SETTER+4))):
            blob,segs,put=synthetic()
            put(pc,val)
            with self.assertRaises(ValueError):
                proof.verify_calls(blob,segs,HANDLER,SETTER,BSS)

    def test_bss_section_size_not_file_offset(self):
        blob=bytearray(128)
        blob[:6]=b"\x7fELF\x01\x01"
        struct.pack_into("<I",blob,32,64) # section-header table offset
        struct.pack_into("<HH",blob,46,40,1) # stride, count
        struct.pack_into("<IIIIII",blob,64,0,8,3,BSS-8,0xabcdef,16)
        self.assertEqual(proof.bss_ranges(blob),[(BSS-8,BSS+8)])
        struct.pack_into("<I",blob,64+20,4)
        self.assertEqual(proof.bss_ranges(blob),[(BSS-8,BSS-4)])
        struct.pack_into("<I",blob,64+8,1) # section is not NOBITS
        self.assertEqual(proof.bss_ranges(blob),[])

    def test_missing_or_symlink_elf_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"invalid.elf"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(proof.main(["--elf",str(file)]),2)
            file.write_bytes(b"not an ARM ELF")
            alias=Path(d)/"link.elf"
            alias.symlink_to(file)
            with self.assertRaisesRegex(ValueError,"bounded local"):
                proof.inspect(alias)

if __name__=="__main__":
    unittest.main(verbosity=2)
