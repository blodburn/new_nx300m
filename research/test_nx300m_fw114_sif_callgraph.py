#!/usr/bin/env python3
"""Synthetic ARM callsite/PLT graph fixtures; never ship proprietary ELFs."""
from __future__ import annotations
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_sif_callgraph as g

BASE=0x1000
SIZE=0x4000
START=0x1100
LOCAL=0x1200
PLT=0x1400
UNKNOWN=0x1800

def bl(site,target):
    delta=(target-site-8)&0xffffffff
    assert delta%4==0
    return 0xeb000000 | ((delta>>2)&0x00ffffff)

def put(buf,address,value):
    struct.pack_into("<I",buf,address-BASE,value)

def fixture():
    data=bytearray(SIZE)
    for site,target in ((START,LOCAL),(START+4,PLT),(START+8,UNKNOWN)):
        put(data,site,bl(site,target))
    # ARM PLT sequence decode is inherited from the independent ABI audit.
    for index,word in enumerate((0xe28fc600,0xe28cca3e,0xe5bcf000)):
        put(data,PLT+index*4,word)
    got=PLT+8+0x3e000
    return bytes(data),[(BASE,SIZE,0)],{LOCAL:"DscImage::SaveExifImage()"},{
        got:"_ZN8DscImage12SaveExifImageEv"
    }

class SIFCallgraphTests(unittest.TestCase):
    def test_local_and_plt_caller_edges(self):
        data,loads,local,relocs=fixture()
        d=g.collect_edges(data,loads,START,12,local,relocs)
        self.assertEqual(d["arm_direct_bl_candidate_count"],3)
        self.assertEqual(d["identified_local_bl_count"],1)
        self.assertEqual(d["identified_plt_import_bl_count"],1)
        self.assertEqual(d["unresolved_or_unnamed_target_count"],1)
        self.assertEqual(len(d["identified_callsite_evidence"]),2)
        self.assertEqual(d["identified_callsite_evidence"][0]["target_symbol"],
                         "DscImage::SaveExifImage()")
        self.assertEqual(d["identified_callsite_evidence"][1]["target_kind"],"import")
        self.assertFalse(d["thumb_blx_indirect_or_virtual_dispatch_resolved"])

    def test_wrong_plt_word_must_not_be_guessed(self):
        data,loads,local,relocs=fixture()
        b=bytearray(data)
        put(b,PLT,0xe1a00000)
        d=g.collect_edges(bytes(b),loads,START,12,local,relocs)
        self.assertEqual(d["identified_plt_import_bl_count"],0)
        self.assertEqual(d["unresolved_or_unnamed_target_count"],2)

    def test_missing_plt_relocation_does_not_prove_import(self):
        data,loads,local,_=fixture()
        d=g.collect_edges(data,loads,START,12,local,{})
        self.assertEqual(d["identified_local_bl_count"],1)
        self.assertEqual(d["identified_plt_import_bl_count"],0)
        self.assertEqual(d["unresolved_or_unnamed_target_count"],2)

    def test_wrong_alignment_and_overlong_rejected(self):
        data,loads,local,relocs=fixture()
        for a,length in ((START+1,12),(START,65540),(START,0)):
            with self.subTest(a=a,length=length),self.assertRaises(ValueError):
                g.collect_edges(data,loads,a,length,local,relocs)

    def test_target_selection_requires_unique_version_specific_symbols(self):
        s={BASE+i*0x100:key+"test)" for i,key in enumerate(g.TARGET_PREFIXES)}
        selected=g.select_targets(s)
        self.assertEqual(len(selected),len(g.TARGET_PREFIXES))
        self.assertEqual(selected[g.TARGET_PREFIXES[0]][0],BASE)
        del s[BASE]
        with self.assertRaisesRegex(ValueError,"Missing/overloaded"):
            g.select_targets(s)
        s[BASE]=g.TARGET_PREFIXES[0]+"test)"
        s[BASE+0x88]=g.TARGET_PREFIXES[0]+"other)"
        with self.assertRaisesRegex(ValueError,"Missing/overloaded"):
            g.select_targets(s)

    def test_truncated_segment_yields_no_bogus_call_evidence(self):
        data,loads,local,relocs=fixture()
        d=g.collect_edges(data,[(BASE,0x100,0)],START,12,local,relocs)
        self.assertEqual(d["arm_direct_bl_candidate_count"],0)
        self.assertFalse(d["identified_callsite_evidence"])

if __name__=="__main__":
    unittest.main(verbosity=2)
