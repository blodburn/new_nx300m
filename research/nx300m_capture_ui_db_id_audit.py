#!/usr/bin/env python3
"""Read-only NX300M Capture UI item -> DB ID switch classification.

This is older modified MFW 1.1 with SLP Samsung 1.15 reference ONLY.
A syntactic table case is not a Picture Wizard-specific ID; do not execute
or install firmware. No paths or binary blobs are published.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

NAME="UI_Get_DB_ID_Capture_Menu("
TOTAL=209
START_UI=3
DEFAULT_EXPECTED=102
STATIC_EXPECTED=89
HELPER_EXPECTED=16
CONDITIONAL_EXPECTED=2

def u32(blob:bytes,segs:list[tuple[int,int,int]],pc:int)->int:
    for base,n,off in segs:
        if base<=pc and pc+4<=base+n:
            return struct.unpack_from("<I",blob,off+pc-base)[0]
    raise ValueError("Read outside file-backed executable")

def inspect_case(blob,segs,addr:int,default:int)->dict:
    if addr==default:return {"kind":"default_zero"}
    words=[u32(blob,segs,addr+4*i) for i in range(5)]
    if words[0]==0xe51b300c and words[1]==0xe1a00003:
        target=arm.decode_arm_bl(words[2],addr+8)
        if target is None or words[3]!=0xe1a03000 or not (
             words[4]>>28==14 and ((words[4]>>24)&15)==10):
            raise ValueError("Unrecognized helper-return case")
        return {"kind":"helper_call","target_address":hex(target)}
    if (words[0]&0x0ff00000)==0x03a00000 and (
        (words[0]>>12)&15)==0 and words[2]==0xe1a03000 and (
        (words[3]&0x0ff00000)==0x03500000):
        helper=arm.decode_arm_bl(words[1],addr+4)
        if helper is None:raise ValueError("Unrecognized conditional helper target")
        return {"kind":"conditional_helper","target_address":hex(helper)}
    if (words[0]&0x0ff00000)==0x03a00000 and (
        words[0]>>12)&15==3 and words[1]>>28==14 and (
          (words[1]>>24)&15)==10:
        return {"kind":"constant_return"}
    raise ValueError("Unknown UI-to-DB ID switch case pattern")

def inspect_switch(blob,segs,start:int,size:int)->dict:
    if size<1500 or size>arm.MAX_FUNC:
        raise ValueError("Invalid expected function size")
    check={
        0x30:0xe51b3008, # ldr r3,[fp,#-8] after optional ID fallback
        0x34:0xe2433003, # sub r3,r3,#3
        0x38:0xe35300d0, # cmp r3,#208
        0x3c:0x979ff103, # ldrls pc,[pc,r3,lsl#2]
    }
    if any(u32(blob,segs,start+k)!=v for k,v in check.items()):
        raise ValueError("Wrong UI->DB jump dispatch prologue")
    base=start+0x44
    end=base+TOTAL*4
    if end>=start+size:raise ValueError("UI->DB jump table exceeds function")
    entries=[u32(blob,segs,base+i*4) for i in range(TOTAL)]
    if any(t<end or t>=start+size or t&3 for t in entries):
        raise ValueError("Invalid UI->DB jump table address")
    freq=collections.Counter(entries)
    most,count=freq.most_common(1)[0]
    if count!=DEFAULT_EXPECTED or [u32(blob,segs,most+4*j)
                                   for j in range(4)]!=[
        0xe3a03000,0xe1a00003,0xe24bd004,0xe8bd8800]:
        raise ValueError("Expected default-zero return case missing")
    kinds=collections.Counter()
    helpers=[]
    for i,address in enumerate(entries):
        result=inspect_case(blob,segs,address,most)
        kind=result["kind"];kinds[kind]+=1
        if kind in ("helper_call","conditional_helper"):
            helpers.append({"ui_value_numeric_index":i+START_UI,
                            "local_target_address":result["target_address"]})
    expected={"default_zero":DEFAULT_EXPECTED,"constant_return":STATIC_EXPECTED,
              "helper_call":HELPER_EXPECTED,"conditional_helper":CONDITIONAL_EXPECTED}
    if dict(kinds)!=expected:
        raise ValueError("Reference UI->DB case classification changed")
    candidate=[p for p in helpers if p["ui_value_numeric_index"]==39]
    if len(candidate)!=1:raise ValueError("UI numeric index 39 not a helper case")
    return {
        "source":"modified MFW 1.1 based on Samsung SLP 1.15, NOT original NX300M 1.14",
        "function":"UI_Get_DB_ID_Capture_Menu(eUI_VALUE_ITEM,int)",
        "selector_first_numeric_index":START_UI,
        "selector_last_numeric_index":START_UI+TOTAL-1,
        "switch_entry_count":TOTAL,
        "distinct_case_targets":len(freq),
        "case_kind_counts":dict(kinds),
        "numeric_index_39_case_kind":"helper_call",
        "numeric_index_39_helper_target":candidate[0]["local_target_address"],
        "all_helper_cases":helpers,
        "picture_wizard_specific_ui_index_verified":False,
        "helper_to_preference_key_mapping_verified":False,
        "picture_wizard_preference_key_verified":False,
        "capture_ipc_or_isp_execution_verified":False,
        "original_firmware_114_abi_verified":False,
        "device_flash_or_memory_patch_permitted":False,
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected bounded local ELF, not camera or firmware")
    blob=path.read_bytes();segs=arm.validate_header(blob)
    symbols=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(symbols)
    names=arm.offline_tool(["c++filt"],
        "\n".join(raw for _,raw in keys)+"\n").splitlines()
    found=[(address,symbols[address,raw])
           for (address,raw),name in zip(keys,names)
           if name.startswith(NAME)]
    if len(found)!=1:raise ValueError("UI->DB ID resolver not unique")
    return inspect_switch(blob,segs,*found[0])

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf",required=True,type=Path)
    ap.add_argument("--summary",action="store_true")
    args=ap.parse_args(argv)
    try:
        result=inspect(args.elf)
        if args.summary:result["all_helper_cases"]=len(result["all_helper_cases"])
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (OSError,ValueError,struct.error) as exc:
        print("CAPTURE_UI_DB_ID_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
