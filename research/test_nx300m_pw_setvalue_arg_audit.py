#!/usr/bin/env python3
"""Synthetic tests of conservative Picture Wizard ARM register callsite evidence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import struct
import unittest
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
SPEC=importlib.util.spec_from_file_location(
    "pw_register_audit",HERE/"nx300m_pw_setvalue_arg_audit.py")
assert SPEC and SPEC.loader
audit=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

def mov_imm(reg:int,value:int)->int:
    assert 0<=value<=255 and 0<=reg<=3
    return 0xe3a00000|(reg<<12)|value

def bl(site:int,dest:int)->int:
    delta=(dest-site-8)&0xffffffff
    assert (delta&3)==0
    return 0xeb000000|((delta>>2)&0xffffff)

def elf_blob(insns:dict[int,int],origin:int=0x1000,size:int=0x600):
    # Code resides at file offset 0; scan function directly by a single
    # executable PT_LOAD segment mapping 0x1000 to file offset zero.
    blob=bytearray(size)
    for pc,op in insns.items():
        struct.pack_into("<I",blob,pc-origin,op)
    return bytes(blob),[(origin,size,0)]

class ArgEvidenceTests(unittest.TestCase):
    def test_ror_and_imm_mov(self):
        self.assertEqual(audit.ror32(0x12,0),0x12)
        self.assertEqual(audit.ror32(0x80,8),0x80000000)
        self.assertEqual(audit.imm_writer(mov_imm(0,4)),{0:4})
        self.assertEqual(audit.imm_writer(mov_imm(2,0x27)),{2:39})
        self.assertEqual(audit.imm_writer(0xe3e03000),{3:0xffffffff})

    def test_register_mov_load_and_cmp_not_guessed(self):
        self.assertEqual(audit.imm_writer(0xe1a02003),{2:None})
        self.assertEqual(audit.imm_writer(0xe5932004),{2:None})
        self.assertEqual(audit.imm_writer(0xe30a30b8),{3:None})
        self.assertEqual(audit.imm_writer(0xe340304d),{3:None})
        self.assertEqual(audit.imm_writer(0xe352000c),{})
        self.assertEqual(audit.imm_writer(0xe0833002),{3:None})

    def test_four_constant_args_after_linear_slice(self):
        data,segs=elf_blob({0x1010:mov_imm(0,11),
                            0x1014:mov_imm(1,4),
                            0x1018:mov_imm(2,13),
                            0x101c:mov_imm(3,0),
                            0x1020:bl(0x1020,0x1100)})
        x=audit.trace_locals(data,segs,0x1020,0x1000)
        self.assertEqual(x,{"r0":11,"r1":4,"r2":13,"r3":0})

    def test_last_register_write_unknown_overrides_old_constant(self):
        data,segs=elf_blob({0x1008:mov_imm(2,99),
                            0x100c:0xe5932004,
                            0x1010:mov_imm(0,4),
                            0x1014:mov_imm(1,4),
                            0x1018:bl(0x1018,0x1100)})
        x=audit.trace_locals(data,segs,0x1018,0x1000)
        self.assertEqual(x["r2"],None)
        self.assertEqual((x["r0"],x["r1"]),(4,4))

    def test_basic_block_boundary_blocks_stale_constant(self):
        data,segs=elf_blob({0x1008:mov_imm(0,4),
                            0x100c:0xea000000,
                            0x1010:mov_imm(1,4),
                            0x1014:bl(0x1014,0x1100)})
        x=audit.trace_locals(data,segs,0x1014,0x1000)
        self.assertIsNone(x["r0"])
        self.assertEqual(x["r1"],4)

    def test_unknown_conditional_mov_never_claimed_constant(self):
        # MOVNE r0,#4 may or may not execute.
        data,segs=elf_blob({0x1008:mov_imm(0,4),
                            0x100c:0x13a00007,
                            0x1010:bl(0x1010,0x1100)})
        self.assertIsNone(audit.trace_locals(data,segs,0x1010,0x1000)["r0"])

    def test_symbol_graph_three_hops_are_not_capture_proof(self):
        source="CAPPGUIGadgetPWState::handle(ISAFEvent const*)"
        generic="GUI_Set_System_Value(int, int, int, int)"
        menu="UI_Set_Menu_Info_By_GUI(tag_MENU_INFO*)"
        capture="UI_Set_Capture_Menu_Info_By_GUI(tag_MENU_INFO)"
        data,segs=elf_blob({
            0x1000:mov_imm(0,4),
            0x1004:mov_imm(1,4),
            0x1008:mov_imm(2,39),
            0x100c:0xe3e03000,
            0x1010:bl(0x1010,0x1100),
            0x1110:bl(0x1110,0x1200),
            0x1210:bl(0x1210,0x1300),
        })
        funcs=[(0x1000,24,source),(0x1100,32,generic),
               (0x1200,32,menu),(0x1300,32,capture)]
        result=audit.build_report(data,segs,funcs)
        self.assertEqual(result["pw_ui_to_generic_setter_callsites"],1)
        self.assertEqual(result["capture_menu_dispatch_edge_count"],1)
        self.assertEqual(len(result["two_hop_menu_dispatch_edges"]),3)
        self.assertEqual(result["callsite_register_immediates"][0]["instruction_args"],
                         {"r0":4,"r1":4,"r2":39,"r3":0xffffffff})
        self.assertFalse(result["actual_picture_wizard_parameter_id_verified"])
        self.assertFalse(result["capture_ipc_or_isp_execution_verified"])
        self.assertFalse(result["device_write_or_flash_authorized"])

    def test_fail_closed_invalid_callsite_and_other_functions(self):
        data,segs=elf_blob({})
        with self.assertRaises(ValueError):
            audit.trace_locals(data,segs,0x1013,0x1000)
        result=audit.build_report(data,segs,
             [(0x1000,64,"GUI_Set_System_Value(int,int,int,int)")])
        self.assertEqual(result["pw_ui_to_generic_setter_callsites"],0)
        self.assertFalse(result["firmware_114_abi_verified"])

if __name__=="__main__":
    unittest.main(verbosity=2)
