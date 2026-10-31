#!/usr/bin/env python3
"""Synthetic direct BL graph fixtures. No vendor ELF code or firmware data."""
from __future__ import annotations
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_pw_capture_db_chain_audit as analyzer

BASE=0x1000
ADDRS={key:BASE+0x400*i for i,key in enumerate(analyzer.NODES)}
SIZE=0x300
SEGS=[(BASE,0x2000,0)]
NAMES={key:key+"synthetic)" for key in analyzer.NODES}

def bl(site:int,target:int)->int:
    disp=(target-site-8)&0xffffffff
    assert disp&3==0
    return 0xeb000000|((disp>>2)&0xffffff)

def fixture():
    blob=bytearray(0x2000)
    index={key:0 for key in analyzer.NODES}
    for (src,dst),count in analyzer.REQUIRED.items():
        for _ in range(count):
            site=ADDRS[src]+index[src]*4
            index[src]+=1
            struct.pack_into("<I",blob,site-BASE,bl(site,ADDRS[dst]))
    funcs=[(ADDRS[key],SIZE,NAMES[key]) for key in analyzer.NODES]
    return blob,funcs

class CaptureDatabaseChainTests(unittest.TestCase):
    def test_all_six_reference_edges_detected(self):
        blob,funcs=fixture()
        result=analyzer.graph(blob,SEGS,funcs)
        self.assertEqual(result["function_nodes"],6)
        self.assertEqual(result["verified_static_edge_groups"],6)
        self.assertEqual(result["required_direct_bl_callsite_total"],25)
        self.assertTrue(result["reference_static_pattern_verified"])
        self.assertFalse(result["ui_picture_wizard_event_reaches_db_setter_verified"])
        self.assertFalse(result["db_function_changes_persistent_storage_verified"])
        self.assertFalse(result["camera_capture_ipc_or_isp_execution_verified"])
        self.assertFalse(result["actual_nx300m_firmware_114_abi_verified"])
        self.assertFalse(result["flash_or_camera_memory_patch_permitted"])

    def test_removed_reference_call_is_detected(self):
        blob,funcs=fixture()
        src=ADDRS[analyzer.SET_CAPTURE]
        struct.pack_into("<I",blob,src+4-BASE,0xe1a00000)
        result=analyzer.graph(blob,SEGS,funcs)
        self.assertEqual(result["verified_static_edge_groups"],5)
        self.assertFalse(result["reference_static_pattern_verified"])

    def test_db_body_embedded_machine_like_words_are_not_scanned(self):
        blob,funcs=fixture()
        # These are BL encodings inside a fake DB jump-table area.
        # They must NOT count as real calls in a linear-disassembly graph.
        db_addr=ADDRS[analyzer.SET_DB]
        for i in range(100):
            site=db_addr+i*4
            struct.pack_into("<I",blob,site-BASE,
                             bl(site,ADDRS[analyzer.SET_VALUE]))
        result=analyzer.graph(blob,SEGS,funcs)
        self.assertEqual(result["required_direct_bl_callsite_total"],25)
        self.assertTrue(result["db_write_body_excluded_due_to_embedded_switch_tables"])

    def test_alternate_symbol_target_does_not_count(self):
        blob,funcs=fixture()
        src=ADDRS[analyzer.SET_VALUE]
        struct.pack_into("<I",blob,src-BASE,
                         bl(src,ADDRS[analyzer.SET_CAPTURE]+4))
        result=analyzer.graph(blob,SEGS,funcs)
        self.assertEqual(result["verified_static_edge_groups"],5)

    def test_missing_symbol_is_rejected(self):
        blob,funcs=fixture()
        with self.assertRaisesRegex(ValueError,"Missing exact"):
            analyzer.graph(blob,SEGS,funcs[:-1])

    def test_duplicate_symbol_is_rejected(self):
        blob,funcs=fixture()
        duplicate=(0x1c00,128,NAMES[analyzer.SET_CAPTURE])
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            analyzer.graph(blob,SEGS,funcs+[duplicate])

    def test_bounded_function_source_is_enforced(self):
        blob,funcs=fixture()
        funcs[0]=(funcs[0][0],analyzer.arm.MAX_FUNC+1,funcs[0][2])
        with self.assertRaisesRegex(ValueError,"unbounded"):
            analyzer.graph(blob,SEGS,funcs)

    def test_cli_rejects_nonelf_and_symlink(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-dbgraph-") as d:
            p=Path(d)/"vendor.elf"
            p.write_bytes(b"not an ELF")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(analyzer.main(["--elf",str(p)]),2)
            alias=Path(d)/"link.elf"
            alias.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"local regular"):
                analyzer.inspect(alias)

if __name__=="__main__":
    unittest.main(verbosity=2)
