#!/usr/bin/env python3
"""Tests for read-only ARM/Tizen firmware ELF inventory and identity guard."""
from __future__ import annotations
import importlib.util
import io
import json
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
import struct
import tempfile
import unittest

AUDIT_PATH = Path(__file__).with_name("nx300m_tizen_elf_audit.py")
SPEC = importlib.util.spec_from_file_location("nx_tizen_elf_audit",AUDIT_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

def make_elf(machine:int=40,flags:int=0x05000002,endianness:int=1)->bytes:
    data=bytearray(100)
    data[:4]=b"\x7fELF"
    data[4]=1
    data[5]=endianness
    prefix="<" if endianness==1 else ">"
    struct.pack_into(prefix+"H",data,18,machine)
    struct.pack_into(prefix+"I",data,36,flags)
    return bytes(data)

class AuditTest(unittest.TestCase):
    def test_arm_eabi5_candidate_not_tizen_proof(self)->None:
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            (p/"lib").mkdir()
            (p/"lib/libcamera.so").write_bytes(make_elf())
            (p/"lib/libhost.so").write_bytes(make_elf(62))
            before=(p/"lib/libcamera.so").read_bytes()
            got=audit.inventory(p)
            self.assertEqual(got["elf_count"],2)
            self.assertEqual(got["arm32_eabi5_little_count"],1)
            self.assertFalse(got["tizen_confirmed_from_elf_alone"])
            self.assertEqual((p/"lib/libcamera.so").read_bytes(),before)
    def test_wrong_eabi_and_big_endian(self)->None:
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            (p/"v4.so").write_bytes(make_elf(flags=0x04000002))
            (p/"big.so").write_bytes(make_elf(endianness=2))
            got=audit.inventory(p)
            self.assertEqual(got["arm32_eabi5_little_count"],0)
    def test_firmware_identity_never_authorized_by_matching_library(self)->None:
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            old=p/"firmware_1_1"
            target=p/"firmware_1_14"
            for folder in (old,target):
                (folder/"lib").mkdir(parents=True)
            (old/"lib/libcamera.so").write_bytes(make_elf())
            (target/"lib/libcamera.so").write_bytes(make_elf())
            result=audit.compare(old,target,audit.inventory(old))
            self.assertEqual(result["bit_identical"],["lib/libcamera.so"])
            self.assertFalse(result["reuse_firmware_offsets_permitted"])
            (target/"lib/libcamera.so").write_bytes(make_elf(flags=0x05000006))
            result=audit.compare(old,target,audit.inventory(old))
            self.assertEqual(result["different"],["lib/libcamera.so"])
    def test_no_files_return_nonzero(self)->None:
        with tempfile.TemporaryDirectory() as t:
            out=io.StringIO()
            with redirect_stdout(out):
                rc=audit.main(["--root",t,"--summary"])
            self.assertEqual(rc,2)
            self.assertEqual(json.loads(out.getvalue())["elf_count"],0)
    def test_comparison_mismatch_return_nonzero_and_no_writes(self)->None:
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            a=p/"a";b=p/"b"
            a.mkdir();b.mkdir()
            (a/"lib.so").write_bytes(make_elf())
            (b/"lib.so").write_bytes(make_elf(flags=0x05000006))
            orig_a=(a/"lib.so").read_bytes()
            orig_b=(b/"lib.so").read_bytes()
            out=io.StringIO()
            with redirect_stdout(out):
                rc=audit.main(["--root",str(a),"--compare-to",str(b),"--summary"])
            self.assertEqual(rc,3)
            self.assertEqual(json.loads(out.getvalue())["comparison"]["different_count"],1)
            self.assertEqual((a/"lib.so").read_bytes(),orig_a)
            self.assertEqual((b/"lib.so").read_bytes(),orig_b)
    def test_tizen_marker_is_only_supporting_evidence(self)->None:
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            (p/"etc").mkdir()
            (p/"etc/tizen-release").write_text("Tizen Camera Platform",encoding="utf-8")
            (p/"camera.so").write_bytes(make_elf())
            got=audit.inventory(p)
            self.assertIn("etc/tizen-release",got["tizen_markers_found"])
            self.assertFalse(got["tizen_confirmed_from_elf_alone"])

if __name__=="__main__":
    unittest.main(verbosity=2)
