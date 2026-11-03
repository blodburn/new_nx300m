#!/usr/bin/env python3
"""Synthetic-only FW1.14 static Capture->JPEG route regression tests."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nx300m_fw114_capture_jpeg_route as route

def fake_paths(root: Path,version: str,*,changed_capture=False) -> dict[str,Path]:
    result={}
    for name in (route.CAPTURE,route.PHOTO,route.SIF):
        dir=root/version
        dir.mkdir(exist_ok=True)
        p=dir/name
        payload=b"synthetic-not-a-camera-ELF-"+name.encode("ascii")
        if changed_capture and name==route.CAPTURE:
            payload+=b"changed"
        p.write_bytes(payload)
        result[name]=p
    return result

def manifest(paths: dict[str,Path]) -> dict[str,dict]:
    return {name:{"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            for name,path in paths.items()}

def fake_still_report() -> dict:
    return {"native_main_still_configuration":{
        "source_backed_callsite_identities":[{"callsite":i} for i in range(9)],
        "main_image_ycc_format":1,
        "main_image_address_mode":7,
    }}

def fake_jpeg_report() -> dict:
    edges=[
        "CYcc::GetY0()","CYcc::GetY1()","CYcc::GetC0()",
        "CYcc::GetC1()","CYcc::GetWidth()","CYcc::GetHeight()",
        "CYcc::GetStride()","DscImage::EncodeYCC(unsigned...)",
    ]
    return {
        "callsite_to_plt_to_relocation_evidence":[{"symbol":x} for x in edges],
        "native_jpeg_parser_sof_sampling_type_evidence":{
            "SOF_component_sampling_0x22":"YCC type 1 (4:2:0)"
        },
    }


class NativeStaticRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.p114=fake_paths(self.root,"1.14")
        self.p115=fake_paths(self.root,"1.15")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dynsym_only_exports_defined_func(self):
        source="\n".join((
            "    1: 00000000     0 FUNC    GLOBAL DEFAULT UND _Z12Undefinedv",
            "    2: 00003000    28 FUNC    GLOBAL DEFAULT  12 _ZN8DscImage9EncodeYCCEi",
            "    3: 00000000    18 OBJECT  GLOBAL DEFAULT  12 _Z4data",
            "    4: 00004000    12 FUNC    WEAK   DEFAULT   14 _Z7weakfunv",
        ))
        symbols=route.exported_dynamic_symbols(source)
        self.assertIn("_ZN8DscImage9EncodeYCCEi",symbols)
        self.assertIn("_Z7weakfunv",symbols)
        self.assertNotIn("_Z12Undefinedv",symbols)
        self.assertNotIn("_Z4data",symbols)

    def test_export_binding_requires_same_mangled_symbol(self):
        relocs={0x1110:"_ZN8DscImage9EncodeYCCEi",0x1120:"_Z7otherfnv"}
        with patch.object(route.jpeg.arm,"offline_tool",
                          return_value="otherfn()\nDscImage::EncodeYCC(int)\n"):
            self.assertEqual(route.import_mangled_encodeycc(relocs),
                             "_ZN8DscImage9EncodeYCCEi")
        with patch.object(route.jpeg.arm,"offline_tool",
                          return_value="otherfn()\nno such export\n"):
            with self.assertRaisesRegex(ValueError,"missing or ambiguous|Missing or ambiguous"):
                route.import_mangled_encodeycc(relocs)

    def test_guard_rejects_changed_capture_file_before_static_offset(self):
        self.p115=fake_paths(self.root,"1.15",changed_capture=True)
        manifests={"1.14":manifest(self.p114),"1.15":manifest(self.p115)}
        with self.assertRaisesRegex(ValueError,"ELF mismatch"):
            route.compare_versions(self.p114,self.p115,manifests)

    def test_guard_rejects_changed_file_after_inventory(self):
        manifests={"1.14":manifest(self.p114),"1.15":manifest(self.p115)}
        self.p114[route.SIF].write_bytes(b"post-inventory-tamper")
        with self.assertRaisesRegex(ValueError,"changed after inventory"):
            route.compare_versions(self.p114,self.p115,manifests)

    def test_guard_rejects_missing_version_manifest(self):
        with self.assertRaisesRegex(ValueError,"Both firmware"):
            route.compare_versions(self.p114,self.p115,{"1.14":manifest(self.p114)})

    def test_synthetic_rerun_verified_static_witness_and_no_go(self):
        manifests={"1.14":manifest(self.p114),"1.15":manifest(self.p115)}
        with patch.object(route.still,"inspect",return_value=fake_still_report()),\
             patch.object(route.jpeg,"inspect",return_value=fake_jpeg_report()),\
             patch.object(route,"exported_binding",return_value={
                 "photolib_plt_import_sif_export_mangled_equal":True}):
            report=route.compare_versions(self.p114,self.p115,manifests)
        self.assertTrue(report[
            "capture_and_photo_files_sha256_identical_between_114_and_115"])
        self.assertTrue(report["native_callsite_rechecked_on_each_version"])
        self.assertEqual(report["fw114"]["capture_recipe_calls_verified"],9)
        self.assertEqual(report["fw114"]["photo_encodeycc_edges_verified"],8)
        for key in ("camera_firmware_flash_permitted",
                    "camera_isp_format_buffer_lifetime_and_dma_verified",
                    "physical_camera_complete_recovery_verified",
                    "exif_makernote_write_compatible_verified"):
            self.assertIs(report[key],False)
        self.assertFalse(report["fw114"]["live_capture_callback_invocation_proven"])

    def test_reject_missing_expected_encodeycc_edge(self):
        broken=fake_jpeg_report()
        broken["callsite_to_plt_to_relocation_evidence"][7]["symbol"]="Wrong::Jpeg"
        with patch.object(route.still,"inspect",return_value=fake_still_report()),\
             patch.object(route.jpeg,"inspect",return_value=broken),\
             patch.object(route,"exported_binding",return_value={}):
            with self.assertRaisesRegex(ValueError,"method order"):
                route.inspect_version(self.p114)

    def test_reject_wrong_capture_mode(self):
        broken=fake_still_report()
        broken["native_main_still_configuration"]["main_image_address_mode"]=6
        with patch.object(route.still,"inspect",return_value=broken),\
             patch.object(route.jpeg,"inspect",return_value=fake_jpeg_report()),\
             patch.object(route,"exported_binding",return_value={}):
            with self.assertRaisesRegex(ValueError,"address mode"):
                route.inspect_version(self.p114)

    def test_reject_false_four_to_zero_evidence(self):
        broken=fake_jpeg_report()
        broken["native_jpeg_parser_sof_sampling_type_evidence"][
            "SOF_component_sampling_0x22"]="UNKNOWN"
        with patch.object(route.still,"inspect",return_value=fake_still_report()),\
             patch.object(route.jpeg,"inspect",return_value=broken),\
             patch.object(route,"exported_binding",return_value={}):
            with self.assertRaisesRegex(ValueError,"4:2:0"):
                route.inspect_version(self.p114)


if __name__=="__main__":
    unittest.main(verbosity=2)
