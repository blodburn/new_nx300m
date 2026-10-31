#!/usr/bin/env python3
"""NX300M read-only ARM32 Capture DB jump table and preference API evidence.

Inspects an existing private modified-MFW 1.1 / Samsung SLP 1.15 ARM ELF.
It does not execute, write, unpack, install or patch proprietary firmware.
No result implies original NX300M 1.14 ABI or observed runtime persistence.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import re
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

TARGET="UI_Set_DB_Value_Capture_Menu("
PREF_SET="pref_set_long"
PREF_GET="pref_get_long"
DEBUG="slpcam_print_info"
EXPECTED_TABLE=205
EXPECTED_SIMPLE=192
EXPECTED_DEFAULT=12
EXPECTED_SPECIAL=1
MAX_FUNC=64*1024

def read_u32(blob:bytes,loads:list[tuple[int,int,int]],addr:int)->int:
    for base,size,offset in loads:
        if base<=addr and addr+4<=base+size:
            return struct.unpack_from("<I",blob,offset+addr-base)[0]
    raise ValueError("Unmapped executable instruction/table entry")

def plt_symbols(text:str)->dict[int,str]:
    """Use dynamic JUMP_SLOT relocation symbol and resolved ELF PLT address.

    Never use arithmetic guesses about the PLT entry index or symbol name.
    """
    result={}
    inside=False
    for line in text.splitlines():
        if line.startswith("Relocation section '"):
            inside=line.startswith("Relocation section '.rel.plt'")
            continue
        if not inside:continue
        m=re.match(
            r"^\s*[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+R_ARM_JUMP_SLOT\s+"
            r"([0-9A-Fa-f]+)\s+(\S+)",line)
        if not m:continue
        vaddr=int(m.group(1),16)
        symbol=m.group(2).split("@")[0]
        if vaddr in result and result[vaddr]!=symbol:
            raise ValueError("Conflicting PLT relocation symbols")
        result[vaddr]=symbol
    if not result:
        raise ValueError("Missing JUMP_SLOT symbol table")
    return result

def check_jump_table(blob:bytes,loads:list[tuple[int,int,int]],
                     entry:int,length:int)->tuple[list[int],int]:
    if entry&3 or length<0x380 or length>MAX_FUNC:
        raise ValueError("Function bounds invalid")
    # Evidence from exact older reference machine code. If a build changes,
    # refuse to infer a jump table instead of guessing at its range.
    prologue={
        0x0:0xe92d4800,    # push {r11,lr}
        0x4:0xe28db004,    # add r11,sp,#4
        0x8:0xe24dd018,    # sub sp,sp,#0x18
        0xc:0xe50b0008,    # str r0,[r11,#-8]
        0x10:0xe50b100c,   # str r1,[r11,#-12]
        0x14:0xe51b3008,   # ldr r3,[r11,#-8]
        0x18:0xe2433001,   # sub r3,r3,#1
        0x1c:0xe35300cc,   # cmp r3,#204
        0x20:0x979ff103,   # ldrls pc,[pc,r3,lsl#2]
        0x24:0xea0004b1,   # b outside switch-table range
    }
    for relative,word in prologue.items():
        if read_u32(blob,loads,entry+relative)!=word:
            raise ValueError("Unrecognized or changed ARM jump table prologue")
    table_start=entry+0x28
    first_code=table_start+EXPECTED_TABLE*4
    if first_code>=entry+length:
        raise ValueError("Table exceeds function bounds")
    table=[read_u32(blob,loads,table_start+4*i)
           for i in range(EXPECTED_TABLE)]
    for addr in table:
        if addr<first_code or addr>=entry+length or addr%4:
            raise ValueError("Jump table contains invalid or noncode offset")
    return table,first_code

def decode_simple(blob:bytes,loads:list[tuple[int,int,int]],
                  target:int,pref_set_plt:int)->dict|None:
    ops=[read_u32(blob,loads,target+i*4) for i in range(5)]
    if ops[0]!=0xe3a00001 or ops[2]!=0xe51b200c:
        return None
    if arm.decode_arm_bl(ops[3],target+12)!=pref_set_plt:
        return None
    if (ops[4]>>28)!=14 or ((ops[4]>>24)&15)!=10: # unconditional B
        return None
    keyop=ops[1]
    # Only syntactic immediate register r1; "preference key" interpretation
    # beyond the called API remains unverified.
    if keyop>>28!=14 or ((keyop>>12)&15)!=1:
        return None
    if (keyop&0x0ff00000)==0x03000000: # MOVW
        immediate=((keyop>>4)&0xf000)|(keyop&0xfff)
    elif (keyop&0x0fe00000)==0x03a00000: # ARM MOV immediate
        shift=((keyop>>8)&15)*2
        raw=keyop&255
        immediate=((raw>>shift)|(raw<<(32-shift)))&0xffffffff if shift else raw
    else:
        return None
    return {"local_pref_key_immediate":immediate,
            "direct_pref_set_long":True}

def classify_table(blob:bytes,loads:list[tuple[int,int,int]],
                   entry:int,length:int,plt:dict[int,str])->dict:
    table,first_code=check_jump_table(blob,loads,entry,length)
    reverse=collections.defaultdict(list)
    for addr,name in plt.items():reverse[name].append(addr)
    for sym in (PREF_SET,PREF_GET,DEBUG):
        if len(reverse[sym])!=1:
            raise ValueError("Ambiguous or missing external preference/log PLT symbol")
    pref=reverse[PREF_SET][0]
    get=reverse[PREF_GET][0]
    logger=reverse[DEBUG][0]
    default_candidates=[v for v in set(table)
                        if v+12<=entry+length
                        and read_u32(blob,loads,v)==0xe1a00000
                        and read_u32(blob,loads,v+4)==0xe24bd004
                        and read_u32(blob,loads,v+8)==0xe8bd8800]
    if len(default_candidates)!=1:
        raise ValueError("Default return block not uniquely identified")
    default=default_candidates[0]
    simple=[]
    skipped=[]
    exceptional=[]
    for i,addr in enumerate(table,1):
        if addr==default:
            skipped.append(i)
            continue
        match=decode_simple(blob,loads,addr,pref)
        if match:
            simple.append({"case_index":i,**match})
        else:
            exceptional.append({"case_index":i,"code_address":addr})
    if len(simple)!=EXPECTED_SIMPLE or len(skipped)!=EXPECTED_DEFAULT or len(exceptional)!=EXPECTED_SPECIAL:
        raise ValueError("Reference code/path classification does not match; fail closed")
    special=exceptional[0]
    addr=special["code_address"]
    # Branch-specific special handler (case 124 in this modified reference).
    # Check only immediate direct-branch call targets in its bounded subregion.
    special_calls=[]
    for pc in range(addr,addr+0x94,4):
        dest=arm.decode_arm_bl(read_u32(blob,loads,pc),pc)
        if dest is not None:
            special_calls.append((pc,plt.get(dest,"other symbol/unknown")))
    histogram=collections.Counter(sym for _,sym in special_calls)
    if histogram[PREF_SET]!=1 or histogram[PREF_GET]!=2 or histogram[DEBUG]!=1:
        raise ValueError("Special-case preference/get/log code does not match")
    return {
        "source":"modified MFW release 1.1 / embedded Samsung NX300M SLP 1.15, NOT stock 1.14",
        "jump_table_entries":len(table),
        "jump_table_first_code_offset":first_code-entry,
        "simple_pref_set_long_cases":len(simple),
        "simple_case_key_values":simple,
        "default_noop_case_indices":skipped,
        "exceptional_case_index":special["case_index"],
        "exceptional_case_direct_call_targets":dict(histogram),
        "jump_table_unique_block_targets":len(set(table)),
        "unique_pref_set_long_plt_symbol_found":True,
        "verified_pref_set_long_calls_in_function":len(simple)+histogram[PREF_SET],
        "verified_pref_get_long_calls_in_special_case":histogram[PREF_GET],
        "verified_debug_log_calls_in_special_case":histogram[DEBUG],
        "reference_pattern_fully_checked":True,
        "picture_wizard_specific_db_key_identified":False,
        "runtime_persistent_write_proven":False,
        "capture_ipc_or_isp_execution_proven":False,
        "original_firmware_114_abi_verified":False,
        "device_flash_or_memory_patch_permitted":False,
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected bounded local regular ARM32 ELF")
    blob=path.read_bytes()
    loads=arm.validate_header(blob)
    entries=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    syms=list(entries)
    names=arm.offline_tool(["c++filt"],
        "\n".join(raw for _,raw in syms)+"\n").splitlines()
    candidates=[(a,entries[a,raw]) for (a,raw),name in zip(syms,names)
                if name.startswith(TARGET)]
    if len(candidates)!=1:raise ValueError("Expected exactly one Capture DB setter")
    plt=plt_symbols(arm.offline_tool(["readelf","-Wr",str(path)]))
    return classify_table(blob,loads,candidates[0][0],candidates[0][1],plt)

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf",required=True,type=Path)
    ap.add_argument("--summary",action="store_true")
    args=ap.parse_args(argv)
    try:
        report=inspect(args.elf)
        if args.summary:
            report["simple_case_key_values"]={
                "count":len(report["simple_case_key_values"]),
                "distinct_local_pref_key_immediates":len(set(
                    x["local_pref_key_immediate"] for x in report["simple_case_key_values"]))}
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,struct.error) as exc:
        print("CAPTURE_PREF_TABLE_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
