#!/usr/bin/env python3
"""Static reference-only UI numeric selector 39 -> preference key candidate chain.

Read-only analysis of PRIVATE modified MFW 1.1 / embedded Samsung SLP 1.15.
A syntactically connected case table does not establish that Picture Wizard
calls this numeric selector, nor that the preference API changes camera ISP.
No camera execution, patching, firmware extraction or network calls.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

import nx300m_pw_ui_bl_call_audit as arm
import nx300m_capture_ui_db_id_audit as ui
import nx300m_capture_pref_jump_table_audit as prefs

UI_GET_VALUE_NAME="UI_Get_Value(eUI_VALUE_ITEM)"
HELPER_UI_NUMERIC=39
HELPER_READ_ITEM=37
BRANCH_COUNT=12
DEFAULT_DB_ID=52

def get_word(blob:bytes,segs:list[tuple[int,int,int]],pc:int)->int:
    return ui.u32(blob,segs,pc)

def check_arm_b(word:int,pc:int,target:int)->bool:
    if (word>>28)!=14 or ((word>>24)&15)!=10:
        return False
    delta=(word&0xffffff)<<2
    if delta&0x2000000:delta-=0x4000000
    return (pc+8+delta)&0xffffffff==target

def parse_helper(blob:bytes,segs:list[tuple[int,int,int]],
                 entry:int,get_value:int)->dict:
    # Exact modified 1.15 ARM helper prologue; reject alternate binaries.
    fixed={
      0x00:0xe92d4800,0x04:0xe28db004,0x08:0xe24dd008,
      0x0c:0xe50b0008,0x10:0xe3a00025, # read eUI item decimal 37
      0x18:0xe1a03000,0x1c:0xe2433001,
      0x20:0xe353000b, # compare (value-1) to 11
      0x24:0x979ff103, # conditional computed PC load
      0x28:0xea000023, # default
      0xc0:0xe1a00003, # return r3
      0xc4:0xe24bd004,0xc8:0xe8bd8800,
      0xbc:0xe3a03034, # default ID 52
    }
    if any(get_word(blob,segs,entry+off)!=expected
           for off,expected in fixed.items()):
        raise ValueError("Unexpected UI39 helper ARM prologue, switch or return")
    if arm.decode_arm_bl(get_word(blob,segs,entry+0x14),entry+0x14)!=get_value:
        raise ValueError("UI39 helper does not call UI_Get_Value")
    first_block=entry+0x5c
    table=[get_word(blob,segs,entry+0x2c+i*4)
           for i in range(BRANCH_COUNT)]
    if table!=[first_block+i*8 for i in range(BRANCH_COUNT)]:
        raise ValueError("Wrong UI39 dynamic 12-entry jump table")
    db=[]
    for offset,address in enumerate(table):
        expected_id=53+offset
        if get_word(blob,segs,address)!=0xe3a03000|expected_id:
            raise ValueError("Unexpected value-to-DB selector constant")
        if not check_arm_b(get_word(blob,segs,address+4),
                           address+4,entry+0xc0):
            raise ValueError("UI39 helper does not return via common epilogue")
        db.append({"ui_get_value_37_result":offset+1,"db_selector":expected_id})
    return {
      "reference_ui_numeric_item":HELPER_UI_NUMERIC,
      "helper_reads_ui_item_numeric":HELPER_READ_ITEM,
      "helper_branch_count":BRANCH_COUNT,
      "conditional_return_mapping":db,
      "other_value_default_db_selector":DEFAULT_DB_ID,
      "does_not_prove_picture_wizard_item":True,
      "helper_body_signature_verified":True,
    }

def join_preference_keys(helper:dict,pref_report:dict)->dict:
    rows=pref_report["simple_case_key_values"]
    keyed={}
    for row in rows:
        key=row["case_index"]
        if key in keyed:raise ValueError("Duplicate Capture DB preference case")
        keyed[key]=row["local_pref_key_immediate"]
    selectors=[helper["other_value_default_db_selector"]]+[
        x["db_selector"] for x in helper["conditional_return_mapping"]]
    if selectors!=list(range(52,65)):
        raise ValueError("Unexpected UI39 helper DB selector IDs")
    mapped=[]
    for selector in selectors:
        if selector not in keyed:
            raise ValueError("DB selector has no checked pref_set_long case")
        mapped.append({
           "db_selector":selector,
           "syntactic_pref_set_long_key":keyed[selector],
           "runtime_persistence_verified":False,
        })
    expected=[868]+[236+i*4 for i in range(12)]
    if [x["syntactic_pref_set_long_key"] for x in mapped]!=expected:
        raise ValueError("Preference keys do not match modified 1.15 reference")
    return {
        "db_selector_to_syntactic_pref_set_long_key":mapped,
        "reference_key_mapping_verified":True,
        "picture_wizard_specific_preference_key_verified":False,
        "hardware_isp_effect_verified":False,
        "original_firmware_114_abi_verified":False,
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected existing local ARM32 ELF file")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    syms=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(syms)
    names=arm.offline_tool(["c++filt"],
        "\n".join(m for _,m in keys)+"\n").splitlines()
    if len(names)!=len(keys):raise ValueError("Invalid ELF symbol demangle count")
    named=[(addr,syms[addr,m],name) for (addr,m),name in zip(keys,names)]
    def one(prefix:str)->tuple[int,int]:
        matching=[(addr,size) for addr,size,name in named if name.startswith(prefix)]
        if len(matching)!=1:raise ValueError("Missing unique camera UI symbol "+prefix)
        return matching[0]
    get_value,_=one(UI_GET_VALUE_NAME)
    ui_addr,ui_size=one(ui.NAME)
    ids=ui.inspect_switch(blob,segs,ui_addr,ui_size)
    helper_addr=int(ids["numeric_index_39_helper_target"],16)
    parsed=parse_helper(blob,segs,helper_addr,get_value)
    pref_report=prefs.inspect(path)
    mapping=join_preference_keys(parsed,pref_report)
    return {
      "scope":"private modified MFW 1.1 / embedded Samsung NX300M SLP 1.15",
      "reference_ui39_to_db_selector":parsed,
      "db_selector_to_preference":mapping,
      "ui39_is_picture_wizard_confirmed":False,
      "ui_pw_event_to_ui39_dataflow_confirmed":False,
      "native_capture_ipc_execution_confirmed":False,
      "real_firmware_114_matching_confirmed":False,
      "safe_camera_firmware_patch_permitted":False,
      "limitations":[
        "Numerical item 39 is not established as Picture Wizard",
        "Static helper and pref_set_long switch code do not prove live control-flow reachability",
        "Preference-key values are raw reference constants, not Samsung public API contracts",
        "No owner firmware 1.14 extraction, safe recovery or physical camera execution",
      ],
    }

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf",required=True,type=Path)
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=inspect(args.elf)
        if args.summary:
            result["reference_ui39_to_db_selector"]["conditional_return_mapping"]=\
                len(result["reference_ui39_to_db_selector"]["conditional_return_mapping"])
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (OSError,ValueError,struct.error) as exc:
        print("UI39_PREF_KEY_CHAIN_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":
    sys.exit(main())
