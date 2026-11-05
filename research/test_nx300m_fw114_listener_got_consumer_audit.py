#!/usr/bin/env python3
"""No vendor ELF required: synthetic ARM32 PIC / GLOB_DAT source tests."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_listener_got_consumer_audit as got


class NativeListenerGotLoads(unittest.TestCase):
    def fixture(self, words, literal_addr, literal_value):
        data = bytearray(128)
        for i, word in enumerate(words):
            struct.pack_into("<I", data, i * 4, word)
        struct.pack_into("<I", data, literal_addr - 0x1000, literal_value)
        return bytes(data), [(0x1000, len(data), 0)]

    def test_literal_add_pc_then_ldr_immediate_reads_exact_got(self):
        # pc(ADD)=0x100c, literal = 0x6868c - 0x100c.
        words=(0xe59f4008, 0xe08f4004, 0xe5943000, 0xe1a00000,
               0xe1a00000)
        data, segments=self.fixture(words, 0x1010, 0x6868c-0x100c)
        out=got.scan_words(data, segments, 0x1000, words,
                           {0x6868c:"AllocListener"}, "mock::register")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["read_type"], "LDR_IMM")
        self.assertEqual(out[0]["load_site"], "0x00001008")
        self.assertEqual(out[0]["GLOB_DAT_slot"], "0x0006868c")
        self.assertFalse(out[0]["is_registration_or_runtime_invocation_proof"])

    def test_literal_add_pc_then_register_indexed_ldr(self):
        # r4 = GOT base (0x68688); r3 = 4; r2 = [r4+r3].
        words=(0xe59f400c,0xe08f4004,0xe3a03004,0xe7942003,
               0xe1a00000,0xe1a00000)
        data,segs=self.fixture(words,0x1014,0x68688-0x100c)
        out=got.scan_words(data,segs,0x1000,words,
                           {0x6868c:"AllocListener"},"mock::indexed")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["read_type"],"LDR_REG")
        self.assertEqual(out[0]["load_site"],"0x0000100c")

    def test_mismatched_slot_and_branch_not_proof(self):
        words=(0xe59f4008,0xe08f4004,0xe5943000,0xe1a00000,
               0xe1a00000)
        data,segs=self.fixture(words,0x1010,0x68690-0x100c)
        self.assertEqual(got.scan_words(
            data,segs,0x1000,words,{0x6868c:"AllocListener"},"negative"),[])
        branch=(0xe59f4008,0xe08f4004,0xea000000,0xe5943000,
                0xe1a00000)
        data,segs=self.fixture(branch,0x1010,0x6868c-0x100c)
        self.assertEqual(got.scan_words(
            data,segs,0x1000,branch,{0x6868c:"AllocListener"},"branch"),[])

    def test_registration_opcode_window_bounded(self):
        words=(0xe1a00000,0xe59f4008,0xe08f4004,0xe5943000,
               0xe1a00000,0xe1a00000)
        excerpt=got.bounded_arm_window(words,0x1000,0x100c,
                                       before=2,after=1)
        self.assertEqual([x["pc"] for x in excerpt],
                         ["0x00001004","0x00001008",
                          "0x0000100c","0x00001010"])
        with self.assertRaisesRegex(ValueError,"Invalid bounded"):
            got.bounded_arm_window(words,0x1000,0x1002)
        with self.assertRaisesRegex(ValueError,"Invalid bounded"):
            got.bounded_arm_window(words,0x1000,0x100c,before=100)

    def test_native_r1_r2_registration_argument_mapping(self):
        start=0x350d8
        words=[0xe1a00000]*55
        exact={
            0x350f4:0xe1a00003,0x350f8:0xe59f309c,
            0x350fc:0xe7943003,0x35100:0xe1a01003,
            0x35104:0xe59f3094,0x35108:0xe7943003,
            0x3510c:0xe1a02003,0x35110:0xebffc896,
        }
        for pc,op in exact.items():
            words[(pc-start)//4]=op
        matched=[
            {"target_listener":"AllocListener","load_site":"0x000350fc",
             "GLOB_DAT_slot":"0x0006868c"},
            {"target_listener":"FreeListener","load_site":"0x00035108",
             "GLOB_DAT_slot":"0x00068684"},
        ]
        calls=[
            {"callsite":"0x00035110","target_kind":"import",
             "target_symbol":"sysmmap_client_callback_register"},
        ]
        p=got.prove_native_register_listener_args(
            tuple(words),start,matched,calls)
        self.assertTrue(p["native_static_BL_and_r1_r2_pointer_transfer_proven"])
        self.assertEqual(p["static_registration_arguments"],
                         {"r1":"AllocListener","r2":"FreeListener"})
        self.assertFalse(p["real_camera_registration_executed_or_succeeded"])
        bad=words.copy()
        bad[(0x3510c-start)//4]=0xe1a01003
        with self.assertRaisesRegex(ValueError,"Changed native"):
            got.prove_native_register_listener_args(
                tuple(bad),start,matched,calls)
        with self.assertRaisesRegex(ValueError,"registration BL missing"):
            got.prove_native_register_listener_args(
                tuple(words),start,matched,[])

    def test_malformed_instruction_and_input_rejected(self):
        self.assertEqual(got.arm_register_ldr(0xe5943000),None)
        self.assertEqual(got.arm_data_processing(0xe59f4008),None)
        self.assertEqual(got.arm_operand2_immediate(0xe3a03004),4)
        with self.assertRaisesRegex(ValueError,"Invalid bounded"):
            got.scan_words(b"",[],0x1001,(0xe1a00000,),
                           {0x6868c:"AllocListener"},"bad")
        with self.assertRaisesRegex(ValueError,"Invalid bounded"):
            got.scan_words(b"",[],0x1000,tuple(),
                           {0x6868c:"AllocListener"},"bad")


if __name__ == "__main__":
    unittest.main(verbosity=2)
