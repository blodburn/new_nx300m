#!/usr/bin/env python3
"""Synthetic branch-witness fixtures, not redistributions of firmware code."""
from __future__ import annotations
import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_pw_capture_branch_audit as witness

BASE=0x1000
STATE=0x1700
CAPTURE=0x1800
FIRST=0x1400
SECOND=0x1500

def branch(pc:int,to:int,cond:int)->int:
    delta=(to-pc-8)&0xffffffff
    assert (delta&3)==0
    return (cond<<28)|0x0a000000|((delta>>2)&0xffffff)

def arm_bl(pc:int,to:int)->int:
    return branch(pc,to,14)|(1<<24)

def fixture():
    instructions={}
    def put(address,value):
        assert address not in instructions
        instructions[address]=value
    first={
        -44:0xe3a00002,-36:0xe1a03000,-32:0xe3530007,
        -28:0x13a03000,-24:0x03a03001,-20:0xe6ef3073,
        -16:0xe3530000,-8:0xe24b3024,-4:0xe893000f,
    }
    for off,word in first.items():put(FIRST+off,word)
    put(FIRST-40,arm_bl(FIRST-40,STATE))
    put(FIRST-12,branch(FIRST-12,FIRST+12,0))
    put(FIRST,arm_bl(FIRST,CAPTURE))
    second={
        -72:0xe51b2014,-68:0xe3003383,-64:0xe1520003,
        -56:0xe51b2014,-52:0xe30033b6,-48:0xe1520003,
        -40:0xe55b300d,-36:0xe3530000,
        -28:0xe24b3024,-24:0xe893000f,
        -16:0xe1a00000,-8:0xe24b3024,-4:0xe893000f,
    }
    for off,word in second.items():put(SECOND+off,word)
    put(SECOND-60,branch(SECOND-60,SECOND-40,13))
    put(SECOND-44,branch(SECOND-44,SECOND-28,13))
    put(SECOND-32,branch(SECOND-32,SECOND-8,0))
    put(SECOND-20,arm_bl(SECOND-20,0x1a00))
    put(SECOND-12,branch(SECOND-12,SECOND+28,14))
    put(SECOND,arm_bl(SECOND,CAPTURE))
    data=bytearray(0x1000)
    for address,word in instructions.items():
        struct.pack_into("<I",data,address-BASE,word)
    segs=[(BASE,len(data),0)]
    names=[
        (0x13a0,SECOND-0x13a0+8,witness.ENTRY+"tag_MENU_INFO*)"),
        (STATE,32,witness.GET_STATE+"eUI_STATE_ITEM)"),
        (CAPTURE,32,witness.CAPTURE+"tag_MENU_INFO)"),
        (0x1a00,32,witness.COMMON+"tag_MENU_INFO)"),
    ]
    return data,segs,names

class BranchWitnessTests(unittest.TestCase):
    def test_state_guard_positive(self):
        data,segs,_=fixture()
        s=witness.state7_branch(data,segs,FIRST,STATE)
        self.assertTrue(s["exact_instruction_sequence_verified"])
        self.assertEqual(s["expected_ui_state_selector_immediate"],2)
        self.assertEqual(s["expected_comparison_immediate"],7)
        self.assertFalse(s["condition_result_is_picture_wizard_runtime_value_proven"])

    def test_second_range_and_flag_branch_positive(self):
        data,segs,_=fixture()
        r=witness.range_flag_branch(data,segs,SECOND)
        self.assertTrue(r["exact_instruction_sequence_verified"])
        self.assertEqual(r["signed_comparison_immediates"],[899,950])
        self.assertFalse(r["field_meanings_or_picture_wizard_route_proven"])

    def test_complete_dispatcher_has_exact_two_static_edges_not_runtime_proof(self):
        data,segs,names=fixture()
        r=witness.build_report(data,segs,names)
        self.assertEqual(r["static_direct_capture_menu_callsites"],2)
        self.assertEqual(r["verified_conditional_instruction_witnesses"],2)
        self.assertFalse(r["ui_pw_event_reaches_capture_branch_verified"])
        self.assertFalse(r["capture_ipc_or_isp_execution_verified"])
        self.assertFalse(r["original_firmware_114_abi_verified"])
        self.assertFalse(r["flash_or_camera_memory_patch_permitted"])

    def test_changed_state_comparison_invalidates_guard(self):
        data,segs,_=fixture()
        struct.pack_into("<I",data,FIRST-32-BASE,0xe3530009)
        self.assertFalse(witness.state7_branch(data,segs,FIRST,STATE)["exact_instruction_sequence_verified"])

    def test_wrong_state_callee_invalidates_guard(self):
        data,segs,_=fixture()
        self.assertFalse(witness.state7_branch(data,segs,FIRST,0x1710)["exact_instruction_sequence_verified"])

    def test_branch_must_skip_over_capture_call(self):
        data,segs,_=fixture()
        struct.pack_into("<I",data,FIRST-12-BASE,
                         branch(FIRST-12,FIRST-4,0))
        self.assertFalse(witness.state7_branch(data,segs,FIRST,STATE)["exact_instruction_sequence_verified"])

    def test_altered_flag_or_range_invalidates_second_witness(self):
        for address,word in ((SECOND-68,0xe3003384),(SECOND-36,0xe3530001),
                             (SECOND-32,branch(SECOND-32,SECOND+12,0))):
            data,segs,_=fixture()
            struct.pack_into("<I",data,address-BASE,word)
            self.assertFalse(witness.range_flag_branch(data,segs,SECOND)["exact_instruction_sequence_verified"])

    def test_reject_missing_state_symbol_or_incorrect_callsites(self):
        data,segs,names=fixture()
        with self.assertRaisesRegex(ValueError,"one menu-dispatcher"):
            witness.build_report(data,segs,names[:1]+names[2:])
        struct.pack_into("<I",data,SECOND-BASE,0xe1a00000)
        with self.assertRaisesRegex(ValueError,"two direct"):
            witness.build_report(data,segs,names)

if __name__=="__main__":
    unittest.main(verbosity=2)
