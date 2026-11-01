#!/usr/bin/env python3
"""Synthetic ARM PLT/JPEG ABI evidence fixtures; no Samsung ELF is shipped."""
from __future__ import annotations
import io
import contextlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_native_jpeg_abi_boundary_audit as audit

BASE=0x26000
PLT_ADDR=[0x29818,0x2836c,0x28b04,0x29800,
          0x27c88,0x28f84,0x26b84,0x27e50]
FUNCTION_START=0x34b18
SIF_BASE=0x29000

def bl(site:int,target:int)->int:
    offset=(target-site-8)&0xffffffff
    assert offset%4==0
    return 0xeb000000|((offset>>2)&0xffffff)

def write(data:bytearray,base:int,addr:int,value:int)->None:
    struct.pack_into("<I",data,addr-base,value)

def test_encoder():
    blob=bytearray(0x10000)
    segments=[(BASE,len(blob),0)]
    got={}
    for (site,symbol),target in zip(audit.EDGES,PLT_ADDR):
        write(blob,BASE,site,bl(site,target))
        # Model genuine ARM three-word PLT format. Extract its own GOT
        # from the resolver rather than assigning an assumed PLT index.
        for k,op in enumerate((0xe28fc600,0xe28cca3e,0xe5bcf000)):
            write(blob,BASE,target+k*4,op)
        addr=audit.plt_got(blob,segments,target)
        got[addr]=symbol
    functions={audit.ENCODER+"CYcc&, unsigned int)":
               (FUNCTION_START,644)}
    return blob,segments,functions,got

class NativeJpegAbiTests(unittest.TestCase):
    def test_arm_rotated_immediate_and_plt_got(self):
        self.assertEqual(audit.immediate(0xe28fc600),0)
        self.assertEqual(audit.immediate(0xe28cca3e),0x3e000)
        blob,segments,_,_=test_encoder()
        self.assertEqual(audit.plt_got(blob,segments,0x29818),
                         0x29818+8+0x3e000)

    def test_resolve_eight_calls_to_named_imports(self):
        blob,seg,functions,got=test_encoder()
        result=audit.resolved_calls(blob,seg,functions,got)
        self.assertEqual(len(result),8)
        self.assertEqual(result[0]["symbol"],"CYcc::GetY0()")
        self.assertTrue(result[-1]["symbol"].startswith("DscImage::EncodeYCC("))

    def test_wrong_branch_target_fails_closed(self):
        blob,seg,functions,got=test_encoder()
        write(blob,BASE,audit.EDGES[0][0],bl(audit.EDGES[0][0],PLT_ADDR[1]))
        with self.assertRaisesRegex(ValueError,"wrong imported"):
            audit.resolved_calls(blob,seg,functions,got)

    def test_missing_relocation_fails_closed(self):
        blob,seg,functions,got=test_encoder()
        del got[audit.plt_got(blob,seg,PLT_ADDR[0])]
        with self.assertRaisesRegex(ValueError,"absent in relocations"):
            audit.resolved_calls(blob,seg,functions,got)

    def test_corrupt_plt_refused(self):
        blob,seg,_,_=test_encoder()
        write(blob,BASE,PLT_ADDR[0],0xe1a00000)
        with self.assertRaisesRegex(ValueError,"Unknown ARM PLT"):
            audit.plt_got(blob,seg,PLT_ADDR[0])

    def test_elf_relplt_jump_slot_parser(self):
        data=(
          "Relocation section '.rel.dyn' at offset 0x0 contains 1 entry:\n"
          "00010000  00000015 R_ARM_GLOB_DAT  00000000 ignored\n"
          "Relocation section '.rel.plt' at offset 0x100 contains 2 entries:\n"
          "00068410  0000a516 R_ARM_JUMP_SLOT 00000000 _ZN4CYcc5GetY0Ev\n"
          "00067d2c  00006116 R_ARM_JUMP_SLOT 00000000 _ZN4CYcc5GetY1Ev\n"
        )
        self.assertEqual(audit.relocations(data),{
            0x68410:"_ZN4CYcc5GetY0Ev",
            0x67d2c:"_ZN4CYcc5GetY1Ev",
        })
        with self.assertRaisesRegex(ValueError,"Missing ARM"):
            audit.relocations("Relocation section '.rel.dyn'\n")

    def test_jpeg_sof_422_and_420_branch_exact(self):
        blob=bytearray(0x1000)
        for addr,value in audit.SOF.items():write(blob,SIF_BASE,addr,value)
        segments=[(SIF_BASE,len(blob),0)]
        funcs={audit.PARSER+"params)": (0x29084,1216)}
        x=audit.validate_sof_switch(blob,segments,funcs)
        self.assertTrue(x["SOF_component_sampling_0x21"].endswith("(4:2:2)"))
        self.assertTrue(x["SOF_component_sampling_0x22"].endswith("(4:2:0)"))
        self.assertFalse(x["decoder_known_current_camera_114"])
        write(blob,SIF_BASE,0x294c8,0xe3530021)
        with self.assertRaisesRegex(ValueError,"branch changed"):
            audit.validate_sof_switch(blob,segments,funcs)

    def test_refuse_nonelf_and_symlink_without_patching(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/"mm.elf"
            b=Path(d)/"sif.elf"
            a.write_bytes(b"broken")
            b.write_bytes(b"broken")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--mm-photo",str(a),
                                           "--sif",str(b)]),2)
            alias=Path(d)/"fake.elf"
            alias.symlink_to(a)
            with self.assertRaisesRegex(ValueError,"bounded research ELF"):
                audit.inspect(alias,b)

if __name__=="__main__":
    unittest.main(verbosity=2)
