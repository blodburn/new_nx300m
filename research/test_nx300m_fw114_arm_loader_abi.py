#!/usr/bin/env python3
"""No-camera ARM EABI and userspace loader audit regression suite."""
from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import nx300m_fw114_arm_loader_abi as abi


def synthetic_elf(path: Path, flags: int = 0x05000200,
                  machine: int = 40, elfclass: int = 1) -> None:
    header = bytearray(52)
    header[:4] = b"\x7fELF"
    header[4] = elfclass
    header[5] = 1
    header[6] = 1
    struct.pack_into("<H",header,16,3)
    struct.pack_into("<H",header,18,machine)
    struct.pack_into("<I",header,20,1)
    struct.pack_into("<I",header,36,flags)
    path.write_bytes(header)

def metadata(attr: str = "Tag_CPU_arch: v7\nTag_ABI_VFP_args: base AAPCS",
             dyn: str = " 0x00000001 (NEEDED) Shared library: [libc.so.6]\n",
             ph: str = "  [Requesting program interpreter: /lib/ld-linux.so.3]\n"):
    def fake(cmd):
        if "-A" in cmd:return attr
        if "-d" in cmd:return dyn
        if "-l" in cmd:return ph
        raise RuntimeError("unknown tool")
    return fake


class AbiAuditTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.path=Path(self.t.name)/"sample.so"
        synthetic_elf(self.path)

    def tearDown(self):
        self.t.cleanup()

    def test_soft_eabi5_loader_and_soname(self):
        with patch.object(abi,"tool",side_effect=metadata()):
            found=abi.inspect_elf(self.path)
        self.assertEqual(found["arm32_eabi5_little_endian"],True)
        self.assertEqual(found["float_abi_eflags"],"soft")
        self.assertEqual(found["float_abi_attributes"],"base_aapcs")
        self.assertEqual(found["tag_cpu_arch"],"v7")
        self.assertEqual(found["program_interpreter"],"/lib/ld-linux.so.3")
        self.assertEqual(found["needed_sonames"],["libc.so.6"])
        self.assertFalse(found["target_sysroot_or_loader_compatibility_verified"])

    def test_absent_float_flag_and_attributes_do_not_guess(self):
        synthetic_elf(self.path,0x05000000)
        with patch.object(abi,"tool",side_effect=metadata(attr="Tag_CPU_arch: v5TE")):
            found=abi.inspect_elf(self.path)
        self.assertEqual(found["float_abi_attributes"],"not_declared")
        self.assertEqual(found["float_abi_eflags"],"unspecified")

    def test_hardfloat_vfp(self):
        synthetic_elf(self.path,0x05000400)
        with patch.object(abi,"tool",side_effect=metadata(attr=(
            "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3\n"
            "Tag_ABI_VFP_args: VFP registers\n"))):
            found=abi.inspect_elf(self.path)
        self.assertEqual(found["float_abi_eflags"],"hard")
        self.assertEqual(found["float_abi_attributes"],"vfp_registers")

    def test_hard_soft_conflict_rejected(self):
        synthetic_elf(self.path,0x05000600)
        with self.assertRaisesRegex(ValueError,"Contradictory"):
            abi.source_header(self.path)

    def test_eabi_version_not_5_rejected(self):
        synthetic_elf(self.path,0x04000200)
        with self.assertRaisesRegex(ValueError,"version 5"):
            abi.source_header(self.path)

    def test_not_arm32_rejected(self):
        synthetic_elf(self.path,machine=62)
        with self.assertRaisesRegex(ValueError,"ARM32"):
            abi.source_header(self.path)
        synthetic_elf(self.path,elfclass=2)
        with self.assertRaisesRegex(ValueError,"ARM32"):
            abi.source_header(self.path)

    def test_symlink_rejected(self):
        linked=Path(self.t.name)/"linked.so"
        linked.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,"non-symlink"):
            abi.source_header(linked)

    def test_attribute_conflict_rejected(self):
        with patch.object(abi,"tool",side_effect=metadata(
            attr="Tag_CPU_arch: v7\nTag_CPU_arch: v6\n")):
            with self.assertRaisesRegex(ValueError,"Conflicting"):
                abi.inspect_elf(self.path)

    def test_eflags_attribute_contradiction_rejected(self):
        with patch.object(abi,"tool",side_effect=metadata(
            attr="Tag_ABI_VFP_args: VFP registers\n")):
            with self.assertRaisesRegex(ValueError,"Contradictory"):
                abi.inspect_elf(self.path)

    def test_compare_versions_differing_loader_dependencies(self):
        source={"arm32_eabi5_little_endian":True,
                "e_flags_hex":"0x05000200","ei_osabi":0,
                "float_abi_eflags":"soft","float_abi_attributes":"base_aapcs",
                "tag_cpu_arch":"v7","tag_fp_arch":"not_declared",
                "program_interpreter":None,"needed_sonames":["libc.so.6"]}
        other=source.copy()
        other["needed_sonames"]=["libc.so.6","libm.so.6"]
        diff=abi.compare_abi(source,other)
        self.assertEqual(diff["different_static_abi_fields"],["needed_sonames"])
        self.assertFalse(diff["two_firmware_versions_static_arm_abi_identical"])
        self.assertFalse(diff["runtime_loader_compatibility_verified"])
        self.assertFalse(diff["firmware_flash_permitted"])

    def test_same_static_signature_is_not_camera_compatibility(self):
        a={"arm32_eabi5_little_endian":True,
           "e_flags_hex":"0x05000200","ei_osabi":0,
           "float_abi_eflags":"soft","float_abi_attributes":"base_aapcs",
           "tag_cpu_arch":"v7","tag_fp_arch":"not_declared",
           "program_interpreter":None,"needed_sonames":[]}
        result=abi.compare_abi(a,a)
        self.assertTrue(result["two_firmware_versions_static_arm_abi_identical"])
        self.assertFalse(result["runtime_loader_compatibility_verified"])
        self.assertFalse(result["on_camera_buffer_hook_safe"])

    def test_untrusted_needed_and_interp_cannot_be_unbounded(self):
        malicious=" 0x1 (NEEDED) Shared library: ["+"a"*200+"]\n"
        with patch.object(abi,"tool",side_effect=metadata(dyn=malicious)):
            out=abi.inspect_elf(self.path)
        self.assertEqual(out["needed_sonames"],[])
        with patch.object(abi,"tool",side_effect=metadata(
            ph="[Requesting program interpreter: ../../relative-ld.so]\n")):
            with self.assertRaisesRegex(ValueError,"loader path"):
                abi.inspect_elf(self.path)


if __name__=="__main__":
    unittest.main(verbosity=2)
