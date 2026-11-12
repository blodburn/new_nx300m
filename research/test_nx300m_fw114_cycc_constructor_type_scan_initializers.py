#!/usr/bin/env python3
"""No-device, synthetic regression for ARM CYcc constructor field writes."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_cycc_constructor_type_scan_initializers as m


def make_provider():
    words=[0xe1a00000]*(m.SIZE//4)
    for pc,op in (m.ENTRY_SAVE, *(
        x for _,_,_,triple in m.INITIALIZERS for x in triple
    )):
        words[(pc-m.START)//4]=op
    return {"provider_elfs":{
        m.PROVIDER:{
            "present":True,
            "target_symbols":[{
                "name":m.NAME,
                "address":f"0x{m.START:08x}",
                "function_bytes":m.SIZE,
                "offline_native_ARM_body":{
                    "arm_word_count":len(words),
                    "arm_instruction_words":[
                        {"pc":f"0x{m.START+4*i:08x}",
                         "opcode":f"0x{word:08x}"}
                        for i,word in enumerate(words)
                    ],
                },
            }],
        },
    }}


def change(provider,pc,word):
    rows=provider["provider_elfs"][m.PROVIDER]["target_symbols"][0][
        "offline_native_ARM_body"]["arm_instruction_words"]
    rows[(pc-m.START)//4]["opcode"]=f"0x{word:08x}"


class CyccConstructorFieldTests(unittest.TestCase):
    def test_exact_initializers_scan1_and_type0_only_this_overload(self):
        proof=m.compare_versions(make_provider(),make_provider())
        self.assertTrue(proof["same_constructor_arm_body"])
        self.assertTrue(proof["same_single_overload_field_initializers"])
        p=proof["fw114"]
        self.assertTrue(p["incoming_this_r0_saved_to_fp_minus16"])
        self.assertEqual(
            [(x["field"],x["native_object_offset"],
              x["adjacent_mov_immediate"]) for x in p["local_initializers"]],
            [("scan_mode",28,1),("type",32,0)]
        )
        self.assertFalse(p["all_constructor_overloads_analyzed"])
        self.assertFalse(p["init_path_executes_on_live_camera_proven"])
        self.assertFalse(p["native_dma_ownership_verified"])
        self.assertFalse(proof["camera_flash_permitted"])

    def test_any_changed_source_opcode_is_refused(self):
        pcs=[m.ENTRY_SAVE[0]]+[pc for _,_,_,triple in m.INITIALIZERS
                                 for pc,_ in triple]
        for pc in pcs:
            with self.subTest(pc=hex(pc)):
                p=make_provider()
                change(p,pc,0xe1a00000)
                with self.assertRaisesRegex(ValueError,"constructor"):
                    m.compare_versions(p,make_provider())

    def test_missing_duplicate_or_out_of_range_constructor_rejected(self):
        p=make_provider()
        syms=p["provider_elfs"][m.PROVIDER]["target_symbols"]
        syms.append(dict(syms[0]))
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            m.compare_versions(p,make_provider())
        syms.pop()
        syms[0]["function_bytes"]-=4
        with self.assertRaisesRegex(ValueError,"size"):
            m.compare_versions(p,make_provider())
        with self.assertRaisesRegex(ValueError,"Missing"):
            m.compare_versions({"provider_elfs":{}},make_provider())

    def test_uncaptured_arm_word_not_reported_as_valid(self):
        p=make_provider()
        rows=p["provider_elfs"][m.PROVIDER]["target_symbols"][0][
            "offline_native_ARM_body"]["arm_instruction_words"]
        rows[42]["pc"]="0x00f00000"
        with self.assertRaisesRegex(ValueError,"instruction stream"):
            m.compare_versions(p,make_provider())

    def test_same_initializer_does_not_imply_identical_full_constructor(self):
        first=make_provider()
        second=make_provider()
        change(second,m.START+4*15,0xe1a00001)
        proof=m.compare_versions(first,second)
        self.assertFalse(proof["same_constructor_arm_body"])
        self.assertTrue(proof["same_single_overload_field_initializers"])
        self.assertFalse(proof["runtime_constructor_usage_proven"])
        self.assertFalse(proof["other_overloads_and_pixel_pack_verified"])


if __name__=="__main__":
    unittest.main(verbosity=2)
