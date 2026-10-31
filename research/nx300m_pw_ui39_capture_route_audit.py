#!/usr/bin/env python3
"""Conservative reference-only Picture Wizard event to Capture item 39 path witness.

Checks a distinct conditional *possible* route across UI event, generic
menu record, menu selector, and Capture menu dispatch. This is STATIC ARM32
machine code evidence from modified MFW1.1 / Samsung SLP1.15 research; not
stock NX300M 1.14, not observed runtime reachability or ISP operation.
Never executes, writes or flashes firmware.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

PW="CAPPGUIGadgetPWState::handle("
GUI="GUI_Set_System_Value("
MENU="UI_Set_Menu_Info_By_GUI("
CAPTURE="UI_Set_Capture_Menu_Info_By_GUI("
VALUE="UI_Set_Capture_Menu_Value("
STATE="UI_Get_State("
GET_VALUE="UI_Get_Value("

def word(blob:bytes,segments:list[tuple[int,int,int]],address:int)->int:
    for base,length,off in segments:
        if base<=address and address+4<=base+length:
            return struct.unpack_from("<I",blob,off+address-base)[0]
    raise ValueError("Instruction outside file-backed ARM executable segment")

def check_words(blob:bytes,segs:list[tuple[int,int,int]],base:int,
                expected:dict[int,int])->None:
    for offset,value in expected.items():
        if word(blob,segs,base+offset)!=value:
            raise ValueError("Changed critical ARM reference instruction")

def direct(blob,segs,source:int,target:int)->bool:
    return arm.decode_arm_bl(word(blob,segs,source),source)==target

def branch(blob,segs,source:int,target:int,condition:int)->bool:
    op=word(blob,segs,source)
    if op>>28!=condition or ((op>>24)&15)!=10:return False
    disp=(op&0xffffff)<<2
    if disp&0x2000000:disp-=0x4000000
    return ((source+8+disp)&0xffffffff)==target

def verify(blob:bytes,segs:list[tuple[int,int,int]],
           nodes:dict[str,tuple[int,int]])->dict:
    for k in (PW,GUI,MENU,CAPTURE,VALUE,STATE,GET_VALUE):
        if k not in nodes:raise ValueError("Missing uniquely named ARM UI function")
    pw=nodes[PW][0]
    gui=nodes[GUI][0]
    menu=nodes[MENU][0]
    capture=nodes[CAPTURE][0]
    value=nodes[VALUE][0]
    state=nodes[STATE][0]
    get_value=nodes[GET_VALUE][0]
    # Specific callsite in PWState::handle; no assumptions about unrelated
    # GUI_Set_System_Value calls which set different menu commands.
    pw_call=pw+0x5d0
    check_words(blob,segs,pw_call,{
         -12:0xe3a00005, -8:0xe3a01004, -4:0xe3a02027})
    if not direct(blob,segs,pw_call,gui):
        raise ValueError("Picture Wizard 5/4/39 callsite no longer targets generic GUI setter")
    # Generic wrapper saves 4 input registers and copies exactly to local
    # tag_MENU_INFO[0..3] before invoking menu dispatcher with the struct.
    check_words(blob,segs,gui,{
         0x0c:0xe50b0010,0x10:0xe50b1014,0x14:0xe50b2018,0x18:0xe50b301c,
         0x3c:0xe5832000,0x48:0xe5832004,
         0x54:0xe5832008,0x60:0xe583200c,
         0xb8:0xe51b0008})
    if not direct(blob,segs,gui+0xbc,menu):
        raise ValueError("GUI menu record not sent to known dispatcher")
    # Menu dispatcher copies source fields to locals, excludes type=10 and
    # consults a *dynamic* UI value to select conditional Capture route.
    check_words(blob,segs,menu,{
        0x24:0xe5933000, 0x28:0xe50b3024,
        0x30:0xe5933008, 0x34:0xe50b301c,
        0x44:0xe593300c, 0x48:0xe50b3018,
        0x50:0xe5933004, 0x54:0xe50b3020,
        0x5c:0xe353000a, # compare menu command to 10
        0x190:0xe3a00e3f, # mov r0, #0x3f0 (UI item 1008)
        0x19c:0xe243301e, # UI_Get_Value result -30
        0x1a0:0xe353000d, # 14 switch cases
        0x1a4:0x979ff103,
        0x1ac:menu+0x420, # UI_Get_Value(1008)==30 -> state guard
    })
    if not branch(blob,segs,menu+0x60,menu+0x140,1):
        raise ValueError("Menu command!=10 conditional branch no longer matches")
    if not direct(blob,segs,menu+0x194,get_value):
        raise ValueError("Menu state switch no longer reads UI_Get_Value")
    # Menu dynamic state=30 case: check UI_Get_State(2)==7 before Capture.
    condition_start=menu+0x420
    check_words(blob,segs,condition_start,{
        0:0xe3a00002, 8:0xe1a03000,12:0xe3530007,
        0x1c:0xe3530000,0x24:0xe24b3024,
        0x28:0xe893000f,0x20:0x0a00001b
    })
    if not direct(blob,segs,condition_start+4,state):
        raise ValueError("Expected UI_Get_State(2) not called")
    if not direct(blob,segs,condition_start+0x2c,capture):
        raise ValueError("State-guarded Capture BL not found")
    # A separate dynamic state branch also calls Capture, only under a
    # menu record value range/flag check. No runtime selector established.
    if not direct(blob,segs,menu+0x49c,capture):
        raise ValueError("Second conditional Capture dispatch not found")
    # Capture handler receives the same 4 fields via register block copy.
    # Source field r0=5 is a type=5 switch arm; field r2=39 (third
    # register) becomes local item [-8]. r3 is the still-unknown value.
    check_words(blob,segs,capture,{
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
        0x360:0xe51b0008,0x364:0xe51b1010,
    })
    table_start=capture+0xf8
    case5=word(blob,segs,table_start+4*4)
    if case5!=capture+0x2b0:
        raise ValueError("Capture menu type=5 case target changed")
    if not direct(blob,segs,capture+0x368,value):
        raise ValueError("Capture item forwarding callsite no longer matches")
    special_values=[44,202,3,22,8,7,187]
    if 39 in special_values:raise ValueError("Reference item 39 became a special-case")
    return {
      "source":"MFW 1.1 modified research ELF, embedded Samsung NX300M SLP 1.15",
      "picture_wizard_ui_calls_gui_with_known_first_three_args":[5,4,39],
      "fourth_argument_value_statically_known":False,
      "gui_wrapper_copies_four_args_into_menu_record":True,
      "menu_dispatch_depends_on_global_ui_state":True,
      "menu_state_selector_ui_value_numeric":1008,
      "menu_state_guard_ui_get_state_selector":2,
      "menu_state_guard_expected_state_value":7,
      "capture_menu_type_5_switch_entry_checked":True,
      "capture_menu_forwards_item_39_if_guarded_branch_reached":True,
      "capture_menu_forwards_actual_fourth_argument_value_unverified":True,
      "capture_menu_checked_exceptions_not_equal_39":special_values,
      "reference_static_conditional_route_witness_verified":True,
      "picture_wizard_runtime_route_executed_verified":False,
      "capture_value_to_persistent_pref_key_runtime_verified":False,
      "capture_ipc_or_isp_effect_verified":False,
      "original_nx300m_114_firmware_abi_verified":False,
      "device_patch_or_flash_permitted":False,
      "limitations":[
        "A dynamic global UI state determines if menu record reaches Capture",
        "The fourth GUI_Set_System_Value parameter remains unknown at the callsite",
        "Static condition/BL matches do not prove executed events or persistent writes",
        "Older modified 1.15 ARM instruction offsets are not valid firmware 1.14 hooks",
      ],
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected bounded local ARM32 executable")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    symbols=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(symbols)
    names=arm.offline_tool(["c++filt"],"\n".join(x[1] for x in keys)+"\n").splitlines()
    if len(keys)!=len(names):raise ValueError("ELF symbol demangle count changed")
    nodes={}
    for (addr,mangled),demangled in zip(keys,names):
        for prefix in (PW,GUI,MENU,CAPTURE,VALUE,STATE,GET_VALUE):
            if demangled.startswith(prefix):
                if prefix in nodes:raise ValueError("Duplicate relevant ELF symbol")
                nodes[prefix]=(addr,symbols[(addr,mangled)])
    return verify(blob,segs,nodes)

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf",required=True,type=Path)
    args=ap.parse_args(argv)
    try:
        print(json.dumps(inspect(args.elf),ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,struct.error) as exc:
        print("PW_TO_CAPTURE_ROUTE_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":
    sys.exit(main())
