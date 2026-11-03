#!/usr/bin/env python3
"""No-real-ELF regression for safely mapped ARM32 symbol-body comparison."""
from __future__ import annotations
from pathlib import Path
import struct
import tempfile
import unittest

import nx300m_fw114_function_proofs as focus


def fake_arm_elf(path: Path) -> None:
    """ELF32 with one PT_LOAD file segment, never executable camera code."""
    buf=bytearray(2048)
    buf[:4]=b"\x7fELF";buf[4]=1;buf[5]=1;buf[6]=1
    struct.pack_into("<H",buf,16,3)  # ET_DYN
    struct.pack_into("<H",buf,18,40) # ARM
    struct.pack_into("<I",buf,20,1)
    struct.pack_into("<I",buf,28,52) # PHDR
    struct.pack_into("<I",buf,36,0x05000000)
    struct.pack_into("<HH",buf,40,52,32)
    struct.pack_into("<H",buf,44,1)
    struct.pack_into("<IIIIIIII",buf,52,
                     1,0x100,0x20000,0,0x700,0x700,5,0x1000)
    buf[0x120:0x128]=bytes(range(8))
    path.write_bytes(buf)


class FunctionProofTests(unittest.TestCase):
    def test_load_range_maps_in_bounds_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"libfake.so"
            fake_arm_elf(path)
            loads=focus.program_headers(path)
            self.assertEqual(loads,[(0x20000,0x700,0x100)])
            self.assertEqual(focus.file_range_for_vaddr(loads,0x20020,8),0x120)

    def test_outside_load_and_overlarge_body_rejected(self):
        loads=[(0x20000,0x400,0x100)]
        with self.assertRaisesRegex(ValueError,"outside"):
            focus.file_range_for_vaddr(loads,0x30000,8)
        with self.assertRaisesRegex(ValueError,"range"):
            focus.file_range_for_vaddr(loads,0x20020,0)
        with self.assertRaisesRegex(ValueError,"range"):
            focus.file_range_for_vaddr(loads,0x20020,focus.MAX_FUNCTION+1)

    def test_wrong_machine_header_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"not-ARM.so"
            fake_arm_elf(path)
            data=bytearray(path.read_bytes())
            struct.pack_into("<H",data,18,62)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,"ARM32"):
                focus.program_headers(path)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"actual.so"
            fake_arm_elf(path)
            link=Path(temp)/"linked.so"
            link.symlink_to(path)
            with self.assertRaisesRegex(ValueError,"Invalid"):
                focus.program_headers(link)

    def test_targeted_function_body_sha_diff_and_static_no_go(self):
        a={"functions":{
            "DscJfifHal::Parse()":{"symbol_address":"0x00029000",
                                  "function_bytes":140,
                                  "code_sha256":"1"*64}}}
        b={"functions":{
            "DscJfifHal::Parse()":{"symbol_address":"0x00029100",
                                  "function_bytes":140,
                                  "code_sha256":"1"*64}}}
        r=focus.compare(a,b)
        self.assertEqual(r["common_function_count"],1)
        self.assertTrue(r["functions"][0]["function_code_sha256_equal"])
        self.assertFalse(r["functions"][0]["symbol_address_equal"])
        self.assertFalse(r["native_camera_abi_and_memory_contract_proven"])
        self.assertFalse(r["camera_flash_permitted"])

    def test_old_reference_signature_is_exact_twelve_points(self):
        self.assertEqual(len(focus.OLD_SOFS),12)
        self.assertEqual(focus.OLD_SOFS[0x294c8],0xe3530022)
        self.assertEqual(focus.OLD_SOFS[0x294ac],0xe3530021)


if __name__=="__main__":
    unittest.main(verbosity=2)
