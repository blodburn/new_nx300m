#!/usr/bin/env python3
"""Host-only synthetic regression for target libc / loader linkage inventory."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nx300m_fw114_runtime_linkage_audit as runtime


def fake_elf_file(path:Path,marker:int=1) -> Path:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b"\x7fELF"+bytes([marker])*100)
    return path

def fake_abi(path):
    name=Path(path).name
    needed=["libc.so.6","libm.so.6"] if name in runtime.REQUIRED_ROOT else []
    return {
        "arm32_eabi5_little_endian":True,
        "tag_cpu_arch":"v7",
        "float_abi_eflags":"unspecified",
        "elf_soname":name,
        "needed_sonames":needed,
    }


class FirmwareRuntimeLinkageTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.root=Path(self.t.name)
    def tearDown(self):
        self.t.cleanup()

    def test_glic_version_tag_natural_order(self):
        tags=runtime.version_tags(
            "GLIBC_2.12 GLIBC_2.9 GLIBC_2.34 GLIBC_2.3.4 "
            "GLIBC_2.34 bad GLIBC_X GLIBC_2.0")
        self.assertEqual(tags,["GLIBC_2.0","GLIBC_2.3.4",
                               "GLIBC_2.9","GLIBC_2.12","GLIBC_2.34"])

    def test_readelf_definition_and_need_sections_not_conflated(self):
        evidence=("Version symbols section '.gnu.version' contains 3 entries:\n"
                  " 000:  2 (GLIBC_2.41) 3 (GLIBC_2.39)\n"
                  "Version definition section '.gnu.version_d' contains 2 entries:\n"
                  "  Name: libc.so.6\n  Name: GLIBC_2.17\n"
                  "  Name: GLIBC_2.3\n"
                  "Version needs section '.gnu.version_r' contains 1 entry:\n"
                  "  File: ld-linux.so.3\n  Name: GLIBC_2.7\n")
        with patch.object(runtime.arm,"tool",return_value=evidence):
            actual=runtime.inspect_versions(self.root/"fake.so")
        self.assertEqual(actual["max_defined_glibc_tag"],"GLIBC_2.17")
        self.assertEqual(actual["max_required_glibc_tag"],"GLIBC_2.7")
        self.assertFalse(actual["symbol_version_binding_verified"])

    def test_report_separate_unverified_loader_and_sysroot(self):
        for name in (*runtime.REQUIRED_ROOT,"libc.so.6","libm.so.6"):
            fake_elf_file(self.root/"usr/lib"/name)
        with patch.object(runtime.arm,"inspect_elf",side_effect=fake_abi),\
             patch.object(runtime,"inspect_versions",return_value={
                 "max_defined_glibc_tag":"GLIBC_2.17",
                 "defined_glibc_versions":["GLIBC_2.17"]
             }):
            r=runtime.audit(self.root)
        self.assertTrue(r["firmware_libc_discovered"])
        self.assertEqual(r["libc_max_glibc_version_static"],"GLIBC_2.17")
        self.assertTrue(r["runtime_libraries"]["libc.so.6"]["present"])
        self.assertFalse(r["runtime_libraries"]["ld-linux.so.3"]["present"])
        self.assertEqual(len(r["camera_dependency_roots"]),3)
        for name in ("exact_camera_dynamic_loader_path_verified",
                     "external_arm_gnu_executable_loader_compatible",
                     "target_tizen_sdk_sysroot_verified",
                     "full_dependency_closure_verified",
                     "camera_flash_permitted"):
            self.assertIs(r[name],False)

    def test_unexpected_duplicate_libc_candidates_rejected(self):
        a=fake_elf_file(self.root/"lib"/"libc.so.6")
        fake_elf_file(self.root/"usr/lib"/"libc.so.6",marker=2)
        indexed,_=runtime.index_libs(self.root)
        with self.assertRaisesRegex(ValueError,"Multiple distinct"):
            runtime.choose(indexed,self.root,"libc.so.6")

    def test_benign_internal_relative_symlink_allowed(self):
        real=fake_elf_file(self.root/"lib"/"libc-2.17.so")
        link=self.root/"lib"/"libc.so.6"
        link.symlink_to("libc-2.17.so")
        indexed,_=runtime.index_libs(self.root)
        self.assertEqual(runtime.choose(indexed,self.root,"libc.so.6"),real)

    def test_symlink_escaping_root_refused(self):
        outside=self.root.parent/"outside-nx300m-synthetic.txt"
        # Use an existing but not-created outside file to avoid test collisions.
        with tempfile.TemporaryDirectory() as other:
            external=fake_elf_file(Path(other)/"evil.so")
            lib=self.root/"usr/lib"
            lib.mkdir(parents=True)
            (lib/"libc.so.6").symlink_to(external)
            indexed,_=runtime.index_libs(self.root)
            with self.assertRaisesRegex(ValueError,"escapes"):
                runtime.choose(indexed,self.root,"libc.so.6")

    def test_nonexistent_library_reports_missing_not_safe(self):
        indexed,count=runtime.index_libs(self.root)
        self.assertEqual(count,0)
        self.assertIsNone(runtime.choose(indexed,self.root,"libc.so.6"))
        with self.assertRaisesRegex(ValueError,"Camera library missing"):
            runtime.audit(self.root)

    def test_root_symlink_refused(self):
        link=self.root/"another"
        link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"symlinked"):
            runtime.check_root(link)

    def test_overlong_elf_refused(self):
        lib=fake_elf_file(self.root/"usr/lib"/"libc.so.6")
        # This test never allocates a large file.
        with patch.object(runtime,"MAX_ELF_BYTES",25):
            with self.assertRaisesRegex(ValueError,"ELF size"):
                runtime.safe_file(self.root,lib)


if __name__=="__main__":
    unittest.main(verbosity=2)
