#!/usr/bin/env python3
"""Synthetic ARM event-to-Capture-route witness tests; no Samsung firmware."""
from __future__ import annotations
import struct
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_pw_ui39_capture_route_audit as proof

BASE=0x1000
ADDRS={
    proof.PW:0x1000,proof.GUI:0x2000,proof.MENU:0x3000,
    proof.CAPTURE:0x4000,proof.VALUE:0x5000,
    proof.STATE:0x6000,proof.GET_VALUE:0x7000,
}
SIZE=0x8000

def branch(site:int,target:int,cond:int=14,link:bool=False)->int:
    rel=(target-site-8)&0xffffffff
    if rel&3:raise ValueError("Unaligned synthetic branch")
    return (cond<<28) | 0x0a000000 | (0x01000000 if link else 0) | ((rel>>2)&0xffffff)

def fixture():
    data=bytearray(SIZE)
    def put(pc:int,instruction:int):
        struct.pack_into("<I",data,pc-BASE,instruction)
    p=ADDRS[proof.PW];g=ADDRS[proof.GUI]
    m=ADDRS[proof.MENU];c=ADDRS[proof.CAPTURE]
    v=ADDRS[proof.VALUE];state=ADDRS[proof.STATE];get=ADDRS[proof.GET_VALUE]
    for delta,opcode in {
        0x5c4:0xe3a00005,0x5c8:0xe3a01004,0x5cc:0xe3a02027,
    }.items():put(p+delta,opcode)
    put(p+0x5d0,branch(p+0x5d0,g,link=True))
    for delta,opcode in {
         0x0c:0xe50b0010,0x10:0xe50b1014,0x14:0xe50b2018,0x18:0xe50b301c,
         0x3c:0xe5832000,0x48:0xe5832004,
         0x54:0xe5832008,0x60:0xe583200c,0xb8:0xe51b0008,
    }.items():put(g+delta,opcode)
    put(g+0xbc,branch(g+0xbc,m,link=True))
    for delta,opcode in {
        0x24:0xe5933000,0x28:0xe50b3024,
        0x30:0xe5933008,0x34:0xe50b301c,
        0x44:0xe593300c,0x48:0xe50b3018,
        0x50:0xe5933004,0x54:0xe50b3020,
        0x5c:0xe353000a,0x190:0xe3a00e3f,
        0x19c:0xe243301e,0x1a0:0xe353000d,0x1a4:0x979ff103,
        0x1ac:m+0x420,
        0x420:0xe3a00002,0x428:0xe1a03000,0x42c:0xe3530007,
        0x43c:0xe3530000,0x440:0x0a00001b,
        0x444:0xe24b3024,0x448:0xe893000f
    }.items():put(m+delta,opcode)
    put(m+0x60,branch(m+0x60,m+0x140,cond=1))
    put(m+0x194,branch(m+0x194,get,link=True))
    put(m+0x424,branch(m+0x424,state,link=True))
    put(m+0x44c,branch(m+0x44c,c,link=True))
    put(m+0x49c,branch(m+0x49c,c,link=True))
    for delta,opcode in {
        0x0c:0xe24bc02c,0x10:0xe88c000f,
        0x20:0xe51b3024,0x24:0xe50b3008,
        0x28:0xe51b3020,0x2c:0xe50b3010,
        0xe4:0xe51b302c,0xe8:0xe2433001,
        0xec:0xe3530006,0xf0:0x979ff103,
        0x2b0:0xe51b3008,0x2b4:0xe353002c,
        0x2b8:0x1a000004,
        0x2d0:0xe51b3008,0x2d4:0xe35300ca,0x2d8:0x1a000003,
        0x2ec:0xe51b3008,0x2f0:0xe3530003,0x2f4:0x1a000002,
        0x304:0xe51b3008,0x308:0xe3530016,0x30c:0x1a000006,
        0x32c:0xe51b3008,0x330:0xe3530008,0x334:0x0a00000c,
        0x338:0xe51b3008,0x33c:0xe3530007,0x340:0x0a000009,
        0x344:0xe51b3008,0x348:0xe35300bb,0x34c:0x0a000006,
        0x360:0xe51b0008,0x364:0xe51b1010
    }.items():put(c+delta,opcode)
    put(c+0x108,c+0x2b0) # switch case command 5
    put(c+0x368,branch(c+0x368,v,link=True))
    return data,[(BASE,len(data),0)],{key:(v,0x900) for key,v in ADDRS.items()},put

class PictureWizardConditionalRouteTests(unittest.TestCase):
    def test_reference_witness_does_not_prove_runtime(self):
        data,segments,nodes,_=fixture()
        x=proof.verify(data,segments,nodes)
        self.assertEqual(x["picture_wizard_ui_calls_gui_with_known_first_three_args"],[5,4,39])
        self.assertTrue(x["reference_static_conditional_route_witness_verified"])
        self.assertTrue(x["capture_menu_forwards_item_39_if_guarded_branch_reached"])
        self.assertFalse(x["picture_wizard_runtime_route_executed_verified"])
        self.assertFalse(x["capture_ipc_or_isp_effect_verified"])
        self.assertFalse(x["original_nx300m_114_firmware_abi_verified"])
        self.assertFalse(x["device_patch_or_flash_permitted"])

    def test_wrong_ui_item_39_immediate_rejected(self):
        data,segments,nodes,put=fixture()
        put(ADDRS[proof.PW]+0x5cc,0xe3a02026)
        with self.assertRaisesRegex(ValueError,"Changed critical"):
            proof.verify(data,segments,nodes)

    def test_wrong_ui_event_callee_rejected(self):
        data,segments,nodes,put=fixture()
        at=ADDRS[proof.PW]+0x5d0
        put(at,branch(at,ADDRS[proof.GUI]+4,link=True))
        with self.assertRaisesRegex(ValueError,"no longer targets"):
            proof.verify(data,segments,nodes)

    def test_gui_menu_field_write_is_required(self):
        data,segments,nodes,put=fixture()
        put(ADDRS[proof.GUI]+0x54,0xe5831008)
        with self.assertRaisesRegex(ValueError,"Changed critical"):
            proof.verify(data,segments,nodes)

    def test_dynamic_ui_state_gate_not_implicitly_satisfied(self):
        data,segments,nodes,put=fixture()
        put(ADDRS[proof.MENU]+0x42c,0xe3530006)
        with self.assertRaisesRegex(ValueError,"Changed critical"):
            proof.verify(data,segments,nodes)

    def test_missing_guarded_capture_dispatch_rejected(self):
        data,segments,nodes,put=fixture()
        at=ADDRS[proof.MENU]+0x44c
        put(at,branch(at,ADDRS[proof.VALUE],link=True))
        with self.assertRaisesRegex(ValueError,"guarded Capture BL"):
            proof.verify(data,segments,nodes)

    def test_wrong_type_five_case_rejected(self):
        data,segments,nodes,put=fixture()
        put(ADDRS[proof.CAPTURE]+0x108,ADDRS[proof.CAPTURE]+0x2d0)
        with self.assertRaisesRegex(ValueError,"type=5 case"):
            proof.verify(data,segments,nodes)

    def test_no_capture_value_call_is_not_proven(self):
        data,segments,nodes,put=fixture()
        at=ADDRS[proof.CAPTURE]+0x368
        put(at,branch(at,ADDRS[proof.VALUE]+4,link=True))
        with self.assertRaisesRegex(ValueError,"forwarding callsite"):
            proof.verify(data,segments,nodes)

if __name__=="__main__":
    unittest.main(verbosity=2)
