#!/usr/bin/env python3
"""Synthetic ARM still-main mode7 guards, with no vendor firmware payload."""
from __future__ import annotations
from pathlib import Path
import contextlib
import io
from unittest import mock
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_native_still_mode7_boundary_audit as audit

SIZE=0x230000
FUNC={
    audit.RECIPE+"CCapImage*)":(0x20b088,1616),
    audit.ADDR+"CCapImage*, unsigned int&)":(0x156df0,1560),
}
EXPECTED={
  "CCapImage::setImageFormat(":"CCapImage::setImageFormat(CCapImage::eCAP_IMAGE_TYPE)",
  "CCapImage::setYccFormat(":"CCapImage::setYccFormat(CCapImage::eCAP_YCC_FORMAT)",
  "CCapImage::setYccPackType(":"CCapImage::setYccPackType(CCapImage::eCAP_PACK_TYPE)",
  "CCapBuffer::setAddrType(":"CCapBuffer::setAddrType(CCapBuffer::eCAP_ADDR_TYPE)",
  "CCapImage::getBuffer(":"CCapImage::getBuffer()",
  "CCapBuffer::getAddressType(":"CCapBuffer::getAddressType()",
  "CCapImage::getYccFormat(":"CCapImage::getYccFormat()",
}

def bl(site:int,target:int)->int:
    delta=(target-site-8)&0xffffffff
    if delta%4:raise ValueError("unaligned")
    return 0xeb000000|((delta>>2)&0xffffff)

def fixture():
    buf=bytearray(SIZE)
    def write(pc:int,value:int)->None:
        struct.pack_into("<I",buf,pc,value)
    for pc,value in audit.DISPATCH.items():write(pc,value)
    imports={}
    sites=[(site,callee) for _,_,site,callee in audit.RECIPE_CALLS]
    sites.extend(audit.OTHER_CALLS)
    for i,(site,prefix) in enumerate(sites):
        target=0x220000+i*16
        write(site,bl(site,target))
        imports[0x300000+i*4]=EXPECTED[prefix]
    for pc,constant,_,_ in audit.RECIPE_CALLS:write(pc,constant)
    got={0x220000+i*16:0x300000+i*4 for i in range(len(sites))}
    return buf,[(0,SIZE,0)],write,imports,got

def verify_recipe(buf,segs,imports,got):
    with mock.patch.object(audit.abi,"plt_got",side_effect=lambda b,s,t:got[t]):
        return audit.verify_recipe(buf,segs,FUNC,imports)

class NativeStillMode7Tests(unittest.TestCase):
    def test_exact_mode7_jump_and_stride_witness(self):
        b,segs,_,_,_=fixture()
        r=audit.verify_mode7_bytes(b,segs)
        self.assertEqual(r["reference_last_mode"],7)
        self.assertTrue(r["mode7_y1_stride_add_opcode_checked"])
        self.assertTrue(r["mode7_c1_stride_add_opcode_checked"])
        self.assertTrue(r["opaque_pointer_arithmetic_not_pixel_format"])

    def test_invalid_computed_dispatch_guard_refused(self):
        b,segs,write,_,_=fixture()
        write(0x156ef4,0xe3530006)
        with self.assertRaisesRegex(ValueError,"mode7"):
            audit.verify_mode7_bytes(b,segs)

    def test_wrong_mode7_branch_target_refused(self):
        b,segs,write,_,_=fixture()
        write(0x156f1c,0xea000089)
        with self.assertRaisesRegex(ValueError,"mode7"):
            audit.verify_mode7_bytes(b,segs)

    def test_y1_c1_stride_arithmetic_and_null_checks_refused(self):
        for addr in (0x157168,0x157190,0x1571a4,0x1571a8,0x1571d4):
            b,segs,write,_,_=fixture()
            write(addr,0xe1a03002)
            with self.subTest(addr=hex(addr)):
                with self.assertRaisesRegex(ValueError,"mode7"):
                    audit.verify_mode7_bytes(b,segs)

    def test_four_setting_enums_and_nine_callees(self):
        b,segs,_,imports,got=fixture()
        x=verify_recipe(b,segs,imports,got)
        self.assertEqual(x["checked_recipe_and_mode7_getter_calls"],9)
        self.assertEqual((x["main_image_image_format"],x["main_image_ycc_format"],
                          x["main_image_ycc_pack"],x["main_image_address_mode"]),
                         (2,1,0,7))
        self.assertTrue(any("getAddressType" in row["native_method"]
                            for row in x["source_backed_callsite_identities"]))

    def test_wrong_native_setting_or_target_refused(self):
        b,segs,write,imports,got=fixture()
        write(0x20b6bc,0xe3a01006)
        with self.assertRaisesRegex(ValueError,"immediate"):
            verify_recipe(b,segs,imports,got)
        b,segs,write,imports,got=fixture()
        write(0x20b69c,0xe1a00000)
        with self.assertRaisesRegex(ValueError,"ARM BL"):
            verify_recipe(b,segs,imports,got)

    def test_misidentified_relocated_getter_and_missing_plt_refused(self):
        b,segs,_,imports,got=fixture()
        imports[got[0x220000]]="CCapImage::getBuffer()"
        with self.assertRaisesRegex(ValueError,"identity changed"):
            verify_recipe(b,segs,imports,got)
        b,segs,_,imports,got=fixture()
        del imports[got[0x220000]]
        with self.assertRaisesRegex(ValueError,"No PLT/GOT"):
            verify_recipe(b,segs,imports,got)

    def test_non_elf_symlink_rejected_and_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"bad.elf"
            p.write_bytes(b"bad")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--capture-lib",str(p)]),2)
            link=Path(directory)/"link.elf"
            link.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"bounded research ELF"):
                audit.inspect(link)

if __name__=="__main__":unittest.main(verbosity=2)
