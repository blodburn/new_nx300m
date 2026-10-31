#!/usr/bin/env python3
"""Synthetic host fixtures for ARM32 BL callsite graph; no vendor binary."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec=importlib.util.spec_from_file_location(
    "nx_ui_bl",Path(__file__).with_name("nx300m_pw_ui_bl_call_audit.py"))
assert spec and spec.loader
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def encode_bl(site:int,target:int)->int:
    relative=(target-site-8)&0xffffffff
    if relative&3:
        raise ValueError("Invalid ARM alignment")
    if relative<0x02000000 or relative>=0xfe000000:
        return 0xeb000000|((relative>>2)&0xffffff)
    raise ValueError("Outside ARM BL range")

def fake_elf(code:bytes,base:int=0x1000)->bytes:
    result=bytearray(256+len(code))
    result[:4]=b"\x7fELF"
    result[4]=1;result[5]=1;result[6]=1
    struct.pack_into("<HHI",result,16,3,40,1)
    struct.pack_into("<I",result,28,52)
    struct.pack_into("<I",result,36,5<<24)
    struct.pack_into("<HH",result,42,32,1)
    struct.pack_into("<IIIIIIII",result,52,1,256,base,base,
                     len(code),len(code),5,0x1000)
    result[256:]=code
    return bytes(result)

class ArmCallsiteTests(unittest.TestCase):
    def test_bl_forward_and_backward(self):
        for source,destination in ((0x1000,0x101c),(0x2000,0x1ff0),
                                   (0x4000,0x4008),(0x7000,0x7000)):
            instruction=encode_bl(source,destination)
            self.assertEqual(audit.decode_arm_bl(instruction,source),destination)

    def test_blx_and_branch_and_random_words_ignored(self):
        for instruction in (0xea000001,0xfa000003,0xe12fff1e,
                            0xffffffff,0xe1a00000,0):
            self.assertIsNone(audit.decode_arm_bl(instruction,0x2000))

    def test_scan_emits_real_direct_target_only(self):
        instructions=[encode_bl(0x1000,0x1030),0xe1a00000,
                      encode_bl(0x1008,0x0ff4),0xea000000]
        data=fake_elf(struct.pack("<IIII",*instructions))
        segments=audit.validate_header(data)
        self.assertEqual(audit.scan_direct_calls(data,0x1000,16,segments),
                         [(0x1000,0x1030),(0x1008,0x0ff4)])

    def test_bounded_segment_and_unaligned_function_rejected(self):
        data=fake_elf(struct.pack("<III",encode_bl(0x1000,0x1010),0,0))
        segments=audit.validate_header(data)
        self.assertEqual(audit.scan_direct_calls(data,0x1000,100,segments),[])
        self.assertEqual(audit.scan_direct_calls(data,0x1001,8,segments),[])
        self.assertEqual(audit.scan_direct_calls(data,0x1000,audit.MAX_FUNC+1,segments),[])

    def test_header_checks_and_truncated_load_rejected(self):
        base=fake_elf(struct.pack("<I",0))
        self.assertEqual(len(audit.validate_header(base)),1)
        broken=bytearray(base);broken[18]=3
        with self.assertRaisesRegex(ValueError,"ARM"):
            audit.validate_header(broken)
        broken=bytearray(base)
        struct.pack_into("<I",broken,52+16,999999)
        with self.assertRaises(ValueError):
            audit.validate_header(broken)

    def test_parse_defined_function_symbols(self):
        rows=(
            "   12: 00001000   20 FUNC GLOBAL DEFAULT 12 _Z18set_picture_wizardi\n"
            "   13: 00002000   32 FUNC GLOBAL DEFAULT UND _ignored\n"
            "   14: 00002010   52 FUNC WEAK DEFAULT 12 _Z20GUI_Set_System_Valueiiii\n"
        )
        d=audit.parse_functions(rows)
        self.assertEqual(len(d),2)
        self.assertEqual(d[(0x1000,"_Z18set_picture_wizardi")],20)
        self.assertEqual(d[(0x2010,"_Z20GUI_Set_System_Valueiiii")],52)

    def test_role_classifier_does_not_equate_ui_and_isp(self):
        self.assertEqual(audit.classify("CAPPGUIGadgetPWState::handle(ISAFEvent const*)"),
                         "CAPPGUIGadgetPWState::handle(")
        self.assertEqual(audit.classify("GUI_Set_System_Value(int,int,int,int)"),
                         "GUI_Set_System_Value(")
        self.assertEqual(audit.TARGET_ROLE["GUI_Set_System_Value("],
                         "generic_system_value_dispatch")
        self.assertIsNone(audit.classify("SamsungISP::ApplyRealCameraFrame()"))

    def test_reject_nonelf_and_symlink_without_camera_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"fake.elf";p.write_bytes(b"not a camera ELF")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--elf",str(p)]),2)
            alias=Path(temp)/"alias.elf";alias.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"regular"):
                audit.analyze(alias)

if __name__=="__main__":
    unittest.main(verbosity=2)
