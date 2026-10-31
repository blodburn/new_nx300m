#!/usr/bin/env python3
"""Conservative NX300M Picture Wizard UI -> capture-menu branch witnesses.

Read-only inspection of a PREEXISTING, PRIVATE modified Samsung SLP 1.15
reference ELF. A static branch witness is not evidence that a PW event takes
that branch at runtime, nor evidence of NX300M original 1.14 ABI or ISP writes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

ENTRY="UI_Set_Menu_Info_By_GUI("
CAPTURE="UI_Set_Capture_Menu_Info_By_GUI("
GET_STATE="UI_Get_State("
COMMON="UI_Set_Common_Menu_Info_By_GUI("

def at(blob:bytes,segs:list[tuple[int,int,int]],address:int)->int:
    for base,size,offset in segs:
        if base<=address and address+4<=base+size:
            return struct.unpack_from("<I",blob,offset+address-base)[0]
    raise ValueError("Expected executable instruction not mapped to file")

def branch_target(word:int,address:int,cond:int)->int|None:
    if (word>>28)!=cond or ((word>>25)&7)!=5:
        return None
    disp=(word&0xffffff)<<2
    if disp&0x2000000:disp-=0x4000000
    return (address+8+disp)&0xffffffff

def code_matches(blob,segs,addr,offsets:dict[int,int])->bool:
    try:return all(at(blob,segs,addr+rel)==word for rel,word in offsets.items())
    except ValueError:return False

def state7_branch(blob,segs,callsite:int,state_fn:int)->dict:
    # Anchored on the *capture* BL call, not old absolute addresses.
    # This witnesses a comparison of UI_Get_State(2) to 7 and a conditional
    # branch SKIPPING the capture BL if the comparison returns non-7.
    fixed={
        -44:0xe3a00002, # mov r0,#2
        -36:0xe1a03000, # mov r3,r0
        -32:0xe3530007, # cmp r3,#7
        -28:0x13a03000, # movne r3,#0
        -24:0x03a03001, # moveq r3,#1
        -20:0xe6ef3073, # uxtb r3,r3
        -16:0xe3530000, # cmp r3,#0
        -8:0xe24b3024,  # sub r3,r11,#0x24
        -4:0xe893000f,  # ldm r3,{r0-r3}
    }
    matched=code_matches(blob,segs,callsite,fixed)
    try:
        state_call=arm.decode_arm_bl(at(blob,segs,callsite-40),callsite-40)
        skip=branch_target(at(blob,segs,callsite-12),callsite-12,0)
        capture=arm.decode_arm_bl(at(blob,segs,callsite),callsite)
    except ValueError:
        state_call=skip=capture=None
    verified=bool(matched and state_call==state_fn and
                  skip is not None and skip>callsite)
    return {
        "branch_kind":"get_ui_state_2_equals_7_guard",
        "reference_callsite":hex(callsite),
        "preceding_ui_get_state_direct_bl":state_call==state_fn,
        "expected_ui_state_selector_immediate":2 if verified else None,
        "expected_comparison_immediate":7 if verified else None,
        "branch_skips_capture_when_comparison_false":verified,
        "exact_instruction_sequence_verified":verified,
        "condition_result_is_picture_wizard_runtime_value_proven":False,
        "native_capture_ipc_proven":False,
    }

def range_flag_branch(blob,segs,callsite:int)->dict:
    # A distinct capture call is reached after comparisons involving the
    # MENU_INFO field at [r11,#-0x14] and a byte flag [r11,#-0xd].
    # This is a syntax witness only: exact field semantics and path
    # reachability from Picture Wizard are not proven.
    fixed={
        -72:0xe51b2014,
        -68:0xe3003383, # movw r3,#0x383 = 899
        -64:0xe1520003, # cmp r2,r3
        -56:0xe51b2014,
        -52:0xe30033b6, # movw r3,#0x3b6 = 950
        -48:0xe1520003,
        -40:0xe55b300d, # ldrb r3,[r11,#-0xd]
        -36:0xe3530000, # cmp r3,#0
        -28:0xe24b3024,
        -24:0xe893000f,
        -16:0xe1a00000,
        -8:0xe24b3024,
        -4:0xe893000f,
    }
    # The branch that reaches the CAPTURE call uses the flag, but nearby
    # other BL target and branch displacements change between builds.
    matched=code_matches(blob,segs,callsite,fixed)
    try:
        before1=branch_target(at(blob,segs,callsite-60),callsite-60,13)
        before2=branch_target(at(blob,segs,callsite-44),callsite-44,13)
        flag_eq=branch_target(at(blob,segs,callsite-32),callsite-32,0)
        parallel=arm.decode_arm_bl(at(blob,segs,callsite-20),callsite-20)
        endskip=branch_target(at(blob,segs,callsite-12),callsite-12,14)
        # guard includes a skip-path call (UI_Set_Common...). Capture path
        # starts exactly at -8, directly before capture BL.
    except ValueError:
        before1=before2=flag_eq=parallel=endskip=None
    verified=bool(matched and before1==callsite-40 and
        before2==callsite-28 and flag_eq==callsite-8 and
        parallel is not None and endskip is not None and endskip>callsite)
    return {
        "branch_kind":"menu_field_range_and_flag_guard",
        "reference_callsite":hex(callsite),
        "signed_comparison_immediates": [899,950] if verified else None,
        "byte_flag_compared_to_zero":verified,
        "branch_to_capture_call_if_flag_zero_in_one_path":verified,
        "exact_instruction_sequence_verified":verified,
        "field_meanings_or_picture_wizard_route_proven":False,
        "native_capture_ipc_proven":False,
    }

def build_report(blob:bytes,segs:list[tuple[int,int,int]],
                 functions:list[tuple[int,int,str]])->dict:
    relevant=[(a,n,name) for a,n,name in functions if name.startswith(ENTRY)]
    state={a for a,n,name in functions if name.startswith(GET_STATE)}
    capture={a for a,n,name in functions if name.startswith(CAPTURE)}
    if len(relevant)!=1 or len(state)!=1 or len(capture)!=1:
        raise ValueError("Expected one menu-dispatcher, capture handler and state getter")
    address,size,name=relevant[0]
    sites=[(pc,to) for pc,to in arm.scan_direct_calls(blob,address,size,segs)
           if to in capture]
    if len(sites)!=2:
        raise ValueError("Expected exactly two direct capture-menu BL callsites")
    witnesses=[]
    for pc,to in sites:
        a=state7_branch(blob,segs,pc,next(iter(state)))
        b=range_flag_branch(blob,segs,pc)
        witnesses.append(a if a["exact_instruction_sequence_verified"] else b)
    witnesses.sort(key=lambda d:d["branch_kind"])
    verified=sum(x["exact_instruction_sequence_verified"] for x in witnesses)
    kinds={x["branch_kind"] for x in witnesses if x["exact_instruction_sequence_verified"]}
    return {
        "source":"modified MFW 1.1 reference with Samsung SLP 1.15",
        "dispatcher_symbol":name,
        "static_direct_capture_menu_callsites":len(sites),
        "verified_conditional_instruction_witnesses":verified,
        "verified_kinds":sorted(kinds),
        "witnesses":witnesses,
        "ui_pw_event_reaches_capture_branch_verified":False,
        "capture_ipc_or_isp_execution_verified":False,
        "original_firmware_114_abi_verified":False,
        "flash_or_camera_memory_patch_permitted":False,
        "limitations":[
            "Machine-code sequence matches are static and specific to an older modified build",
            "State selector 2 and comparison 7 do not identify their semantic meaning",
            "Comparison values 899 and 950 do not establish Picture Wizard parameter IDs",
            "A guarded dispatcher call is not proof an actual Picture Wizard event reaches it",
            "No indirect calls, state mutation, hardware capture or camera original 1.14 verified",
        ],
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected private local bounded ARM ELF file")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    symbols=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(symbols)
    names=arm.offline_tool(["c++filt"],
        "\n".join(raw for _,raw in keys)+"\n").splitlines()
    if len(keys)!=len(names):raise ValueError("Demangling count mismatch")
    functions=[(address,symbols[(address,raw)],name)
               for (address,raw),name in zip(keys,names)]
    return build_report(blob,segs,functions)

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        report=inspect(args.elf)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["verified_conditional_instruction_witnesses"]==2 else 3
    except (OSError,ValueError,struct.error) as e:
        print("CAPTURE_MENU_BRANCH_AUDIT_REJECTED: "+str(e),file=sys.stderr)
        return 2

if __name__=="__main__":sys.exit(main())
