#!/usr/bin/env python3
"""Host-only tests of FW CYcc GetType/GetScanMode static ARM decoding."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_cycc_getter_field_offsets as m


def method(name, words, addr):
    return {
        "name":name,
        "address":f"0x{addr:08x}",
        "function_bytes":4*len(words),
        "offline_native_ARM_body":{
            "arm_word_count":len(words),
            "arm_instruction_words":[
                {"pc":f"0x{addr+4*i:08x}","opcode":f"0x{w:08x}"}
                for i,w in enumerate(words)
            ],
            "direct_ARM_BL_edges":[],
            "register_indirect_branches":[],
        },
    }


def provider(type_words=None,scan_words=None):
    if type_words is None:
        type_words=m.TYPE_WORDS
    if scan_words is None:
        scan_words=(
            *m.FRAME,0xe5933024,*m.EPILOGUE
        )
    return {"provider_elfs":{
        "libmm-type.so":{
            "present":True,
            "target_symbols":[
                method(m.GETTERS[0],type_words,m.TYPE_SITE),
                method(m.GETTERS[1],scan_words,0x33a0),
            ],
        },
    }}


class CyccGetterFieldTests(unittest.TestCase):
    def test_native_gettype_reads_this_plus32_and_returns_r0(self):
        result=m.inspect_method(
            m.getter_method(provider(),m.GETTERS[0]),m.GETTERS[0]
        )
        self.assertEqual(result["function_site"],"0x000031d8")
        self.assertEqual(result["field_read_site"],"0x000031ec")
        self.assertEqual(result["field_read_opcode"],"0xe5933020")
        self.assertEqual(result["field_offset_from_this_bytes"],32)
        self.assertTrue(result["return_field_via_r3_to_r0"])
        self.assertFalse(result["runtime_cycc_object_identity_proven"])
        self.assertFalse(result["firmware_flash_permitted"])

    def test_independent_scanmode_field_and_two_version_contrast(self):
        proof=m.compare_versions(provider(),provider())
        self.assertTrue(proof["same_GetType_code"])
        self.assertTrue(proof["same_GetScanMode_code"])
        self.assertTrue(proof["GetType_object_field_plus32_verified"])
        self.assertTrue(proof["GetScanMode_object_field_offset_verified"])
        self.assertEqual(
            proof["fw114"][m.GETTERS[1]]["field_offset_from_this_bytes"],
            36
        )
        self.assertFalse(proof["live_getter_results_or_enum_semantics_verified"])
        self.assertFalse(proof["native_DMA_cache_coherency_verified"])

    def test_real_gettype_byte_change_is_fatal(self):
        words=list(m.TYPE_WORDS)
        words[5]=0xe5933024
        with self.assertRaisesRegex(ValueError,"GetType"):
            m.compare_versions(provider(type_words=words),provider())

    def test_getter_calls_or_indirect_branches_refused(self):
        x=provider()
        body=x["provider_elfs"]["libmm-type.so"]["target_symbols"][1][
            "offline_native_ARM_body"]
        body["direct_ARM_BL_edges"]=[{"pc":"0x33c0"}]
        with self.assertRaisesRegex(ValueError,"unmodeled"):
            m.compare_versions(x,provider())
        body["direct_ARM_BL_edges"]=[]
        body["register_indirect_branches"]=[{"pc":"0x33c0"}]
        with self.assertRaisesRegex(ValueError,"unmodeled"):
            m.compare_versions(x,provider())

    def test_missing_ambiguous_or_missing_executable_body_is_refused(self):
        with self.assertRaisesRegex(ValueError,"Missing"):
            m.compare_versions({"provider_elfs":{}},provider())
        x=provider()
        p=x["provider_elfs"]["libmm-type.so"]["target_symbols"]
        p.append(dict(p[1]))
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            m.compare_versions(x,provider())
        p.pop()
        del p[1]["offline_native_ARM_body"]
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            m.compare_versions(x,provider())

    def test_unknown_scanmode_pattern_does_not_invent_field_offset(self):
        words=(*m.FRAME,0xe1a03004,*m.EPILOGUE)
        x=m.compare_versions(provider(scan_words=words),provider(scan_words=words))
        self.assertFalse(x["GetScanMode_object_field_offset_verified"])
        self.assertIsNone(
            x["fw114"][m.GETTERS[1]]["field_offset_from_this_bytes"]
        )
        self.assertFalse(x["physical_camera_buffer_format_or_stride_verified"])

    def test_non_contiguous_arm_code_and_invalid_bounds_rejected(self):
        x=provider()
        body=x["provider_elfs"]["libmm-type.so"]["target_symbols"][1][
            "offline_native_ARM_body"]
        body["arm_instruction_words"][5]["pc"]="0x000033ff"
        with self.assertRaisesRegex(ValueError,"Non-contiguous"):
            m.compare_versions(x,provider())
        x=provider()
        x["provider_elfs"]["libmm-type.so"]["target_symbols"][1][
            "function_bytes"]=4
        with self.assertRaisesRegex(ValueError,"size"):
            m.compare_versions(x,provider())

    def test_gettype_and_scanmode_byte_hashes_differ_only_when_changed(self):
        altered=( *m.FRAME,0xe5933028,*m.EPILOGUE)
        x=m.compare_versions(provider(),provider(scan_words=altered))
        self.assertTrue(x["same_GetType_code"])
        self.assertFalse(x["same_GetScanMode_code"])
        self.assertTrue(x["GetScanMode_object_field_offset_verified"])
        self.assertFalse(x["live_getter_results_or_enum_semantics_verified"])


if __name__=="__main__":
    unittest.main(verbosity=2)
