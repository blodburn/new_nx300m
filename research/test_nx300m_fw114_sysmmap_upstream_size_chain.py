#!/usr/bin/env python3
"""Synthetic safety tests for bounded offline native SYSMMAP call windows."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_sysmmap_upstream_size_chain as c


class UpstreamSizeChain(unittest.TestCase):
    def test_all_static_function_callsites_are_explicit(self):
        self.assertEqual(len(c.CHAINS),9)
        self.assertEqual(c.CHAINS["sysmmap_segment_alloc"][2],
                         {"sysmmap_osif_alloc":(0x0000a344,)})
        self.assertEqual(c.CHAINS["sysmmap_segment_free"][2],
                         {"sysmmap_osif_free":(0x0000a93c,0x0000a9e4)})
        self.assertEqual(c.CHAINS["sysmmap_alloc"][2],
                         {"sysmmap_mgr_alloc":(0x00003360,)})
        for function,(start,size,callees) in c.CHAINS.items():
            self.assertEqual(start%4,0,function)
            self.assertGreater(size,0,function)
            self.assertLessEqual(size,c.MAX_FUNCTION,function)
            for sites in callees.values():
                self.assertTrue(all(start<=site<start+size
                                    for site in sites))

    def test_synthetic_aapcs_r1_snapshot_is_not_runtime_proof(self):
        words=(0xe92d4800,0xe50b1014,0xe51b1014,0xeb000002)
        window=c.callsite_window(words,0x1000,0x100c)
        self.assertEqual(window["callsite"],"0x0000100c")
        self.assertEqual(len(window["first_12_function_arm_words"]),3)
        self.assertEqual(
            window["candidate_argument_writers"]["r1"][-1]["site"],
            "0x00001008")
        self.assertFalse(
            window["r1_is_actual_allocated_byte_count_proven"])
        self.assertFalse(
            window["same_value_as_listener_descriptor_plus4_proven"])
        self.assertFalse(window["runtime_camera_mmap_size_verified"])

    def test_all_exact_native_r1_pre_call_writers(self):
        self.assertEqual(set(c.R1_WRITER_WITNESSES),set(c.CHAINS))
        for name,(start,size,_) in c.CHAINS.items():
            words=[0xe1a00000]*(size//4)
            for callsite,(writer,opcode) in c.R1_WRITER_WITNESSES[name].items():
                words[(writer-start)//4]=opcode
                words[(callsite-start)//4]=0xeb000001
            raw=tuple(words)
            for callsite,(writer,opcode) in c.R1_WRITER_WITNESSES[name].items():
                with self.subTest(name=name,callsite=callsite):
                    item=c.last_r1_writer_witness(raw,start,callsite,name)
                    self.assertEqual(item["writer_site"],f"0x{writer:08x}")
                    self.assertEqual(item["writer_opcode"],f"0x{opcode:08x}")
                    self.assertFalse(
                        item["same_length_as_listener_descriptor_proven"])
                    self.assertFalse(item["live_allocated_bytes_measured"])
                    changed=list(raw)
                    changed[(writer-start)//4]=0xe1a00000
                    with self.assertRaises(ValueError):
                        c.last_r1_writer_witness(
                            tuple(changed),start,callsite,name)
                    if callsite-writer>=8:
                        alternate=list(raw)
                        alternate[(callsite-start)//4-1]=0xe1a01000
                        with self.assertRaises(ValueError):
                            c.last_r1_writer_witness(
                                tuple(alternate),start,callsite,name)

    def test_reject_invalid_synthetic_callsite(self):
        words=(0xe1a00000,0xe1a01002,0xe1a01003,0xeb000002)
        for site in (0x1001,0x0ffc,0x1010,0x1008):
            with self.subTest(site=site),self.assertRaises(ValueError):
                c.callsite_window(words,0x1000,site)


if __name__=="__main__":
    unittest.main(verbosity=2)
