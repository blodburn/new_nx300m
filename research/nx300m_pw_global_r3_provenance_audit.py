#!/usr/bin/env python3
"""Read-only Picture Wizard event r3 provenance and BSS slider-state witnesses.

ONLY an old modified MFW 1.1 / Samsung SLP 1.15 ARM ELF; stock 1.14
compatibility and live camera behavior are unverified. Does not execute,
change, publish, patch or flash original firmware.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

PW="CAPPGUIGadgetPWState::handle("
GUI="GUI_Set_System_Value("
EVENT_WRITE=(5,4,39)
CLEAR_WRITE=(2,4,39,0)
EXPECTED_TOTAL=71
EXPECTED_READ=48
EXPECTED_WRITE=18
EXPECTED_UNRESOLVED=5

def imm16(op:int)->int:
    return ((op>>4)&0xf000)|(op&0xfff)

def movw_movt_address(low:int,high:int)->tuple[int,int]|None:
    if (low>>28)!=14 or (high>>28)!=14:
        return None
    if (low&0x0ff00000)!=0x03000000 or (high&0x0ff00000)!=0x03400000:
        return None
    r=(low>>12)&15
    if r>=15 or ((high>>12)&15)!=r:return None
    return r,((imm16(high)<<16)|imm16(low))

def access_kind(instruction:int,base_register:int)->str:
    # ARM immediate, unconditional, preindexed, word, positive offset zero,
    # no writeback, address base equal to the reconstructed pointer register.
    if ((instruction>>28)!=14 or ((instruction>>26)&3)!=1
        or ((instruction>>25)&1)!=0 or ((instruction>>24)&1)!=1
        or ((instruction>>23)&1)!=1 or ((instruction>>22)&1)!=0
        or ((instruction>>21)&1)!=0 or ((instruction>>16)&15)!=base_register
        or (instruction&0xfff)!=0):
        return "unresolved"
    return "direct_read" if ((instruction>>20)&1) else "direct_write"

def bss_ranges(blob:bytes)->list[tuple[int,int]]:
    if len(blob)<52 or blob[:4]!=b"\x7fELF" or blob[4:6]!=b"\x01\x01":
        raise ValueError("Expected little-endian ELF32")
    offset=struct.unpack_from("<I",blob,32)[0]
    stride,total=struct.unpack_from("<HH",blob,46)
    if stride<40 or total>2048 or offset+stride*total>len(blob):
        raise ValueError("Invalid ELF section headers")
    result=[]
    for i in range(total):
        k=offset+i*stride
        typ,flags,addr,_,size=struct.unpack_from("<IIIII",blob,k+4)
        if typ==8 and flags&3==3 and size>0 and addr+size<=0x100000000:
            result.append((addr,addr+size))
    return result

def read_instruction(blob:bytes,segs:list[tuple[int,int,int]],pc:int)->int:
    for base,size,offset in segs:
        if base<=pc and pc+4<=base+size:
            return struct.unpack_from("<I",blob,offset+pc-base)[0]
    raise ValueError("Instruction outside file-backed executable load segment")

def verify_calls(blob:bytes,segs:list[tuple[int,int,int]],handler:int,
                 general_setter:int,global_address:int)->dict:
    dynamic=handler+0x5d0
    clear=handler+0x604
    expected=[
        (dynamic-24,0xe30a30b4),  # MOVW r3,#a0b4
        (dynamic-20,0xe340304d),  # MOVT r3,#004d
        (dynamic-16,0xe5933000),  # LDR r3,[r3] (not known at build time)
        (dynamic-12,0xe3a00005),
        (dynamic-8,0xe3a01004),
        (dynamic-4,0xe3a02027),
        (clear-16,0xe3a00002),
        (clear-12,0xe3a01004),
        (clear-8,0xe3a02027),
        (clear-4,0xe3a03000),
    ]
    for pc,w in expected:
        if read_instruction(blob,segs,pc)!=w:
            raise ValueError("Changed Picture Wizard event register provenance")
    if global_address!=0x004da0b4:
        raise ValueError("Unexpected reference BSS slider address")
    for pc in (dynamic,clear):
        if arm.decode_arm_bl(read_instruction(blob,segs,pc),pc)!=general_setter:
            raise ValueError("Picture Wizard event no longer calls GUI setter")
    return {
      "dynamic_event_r0_r1_r2":[5,4,39],
      "dynamic_event_r3_source":"ARM LDR word from writable BSS global address",
      "dynamic_event_r3_runtime_value_known":False,
      "clear_event_r0_r1_r2_r3":[2,4,39,0],
      "both_events_call_gui_set_system_value":True,
    }

def scan_global(blob:bytes,segs:list[tuple[int,int,int]],
                function_symbols:list[tuple[int,int,str]],
                global_address:int)->dict:
    starts=sorted((a,size,name) for a,size,name in function_symbols if size>0)
    addrs=[a for a,_,_ in starts]
    rows=[]
    for base,length,offset in segs:
        for i in range(0,length-12,4):
            low=struct.unpack_from("<I",blob,offset+i)[0]
            high=struct.unpack_from("<I",blob,offset+i+4)[0]
            computed=movw_movt_address(low,high)
            if not computed or computed[1]!=global_address:continue
            reg=computed[0]
            opcode=struct.unpack_from("<I",blob,offset+i+8)[0]
            pc=base+i
            j=bisect.bisect_right(addrs,pc)-1
            name=starts[j][2] if j>=0 and pc<starts[j][0]+starts[j][1] else "not_in_defined_function"
            rows.append({"reference_address":hex(pc),
                         "function":name,
                         "access":access_kind(opcode,reg)})
    counts=collections.Counter(x["access"] for x in rows)
    by_func=collections.defaultdict(collections.Counter)
    for x in rows:by_func[x["function"]][x["access"]]+=1
    return {
        "total_movw_movt_global_references":len(rows),
        "access_kind_counts":dict(counts),
        "per_function":{fn:dict(data) for fn,data in sorted(by_func.items())},
        "unresolved_immediate_following_instructions_are_not_assumed_writes":True,
        "reference_static_access_pattern_verified": (
            len(rows)==EXPECTED_TOTAL and
            counts["direct_read"]==EXPECTED_READ and
            counts["direct_write"]==EXPECTED_WRITE and
            counts["unresolved"]==EXPECTED_UNRESOLVED),
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected existing bounded local ARM ELF file")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    symbols=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(symbols)
    names=arm.offline_tool(["c++filt"],
        "\n".join(m for _,m in keys)+"\n").splitlines()
    if len(keys)!=len(names):raise ValueError("Symbol demangling mismatch")
    functions=[(addr,symbols[addr,m],name)
               for (addr,m),name in zip(keys,names)]
    def one(prefix:str)->int:
        matches=[addr for addr,_,name in functions if name.startswith(prefix)]
        if len(matches)!=1:raise ValueError("Expected unique relevant ARM function")
        return matches[0]
    pointer=0x004da0b4
    if not any(lo<=pointer and pointer+4<=hi for lo,hi in bss_ranges(blob)):
        raise ValueError("PW state pointer not in validated writable ELF BSS")
    event=verify_calls(blob,segs,one(PW),one(GUI),pointer)
    refs=scan_global(blob,segs,functions,pointer)
    if not refs["reference_static_access_pattern_verified"]:
        raise ValueError("Global reference counts changed: refuse version equivalence")
    return {
      "scope":"modified MFW 1.1, embedded Samsung NX300M SLP 1.15 only",
      "volatile_reference_address":hex(pointer),
      "address_is_in_elf_writable_bss":True,
      "event_parameter_provenance":event,
      "reference_counts":refs,
      "value_is_persistent_preference_at_runtime_verified":False,
      "actual_picture_wizard_event_reaches_capture_verified":False,
      "capture_ipc_or_isp_execution_verified":False,
      "original_nx300m_114_abi_verified":False,
      "device_write_patch_or_flash_permitted":False,
      "limitations":[
        "BSS is writable uninitialized memory, not saved preference contents",
        "68+ symbol references do not establish runtime execution counts",
        "Five MOVW/MOVT address uses have an intervening instruction and require deeper local control flow",
        "No original stock NX300M 1.14, target camera test, capture IPC or ISP effect verified",
      ],
    }

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf",type=Path,required=True)
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=inspect(args.elf)
        if args.summary:result["reference_counts"].pop("per_function",None)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (OSError,ValueError,struct.error) as exc:
        print("PW_GLOBAL_PROVENANCE_REJECTED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":sys.exit(main())
