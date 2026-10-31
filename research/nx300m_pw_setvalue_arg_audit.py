#!/usr/bin/env python3
"""Conservative ARM32 static callsite argument and menu-dispatch audit.

Works OFFLINE on a separately held, already extracted research ELF. No vendor
bytes published, executed, patched or uploaded. The inferred r0-r3 immediate
values are ONLY local straight-line instructions, not proven runtime values.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

SOURCES=(
 "CAPPGUIGadgetPWState::handle(",
 "CAPPGUIGadgetPWState::onEnter(",
 "CAPPGUIGadgetPWState::Set_PWSlider_Minus(",
 "CAPPGUIGadgetPWState::Set_PWSlider_Plus(",
)
GENERAL="GUI_Set_System_Value("
DISPATCH="UI_Set_Menu_Info_By_GUI("
CAPTURE="UI_Set_Capture_Menu_Info_By_GUI("
COMMON="UI_Set_Common_Menu_Info_By_GUI("
WINDOW=20

def ror32(value:int,rotate:int)->int:
    rotate%=32
    return ((value>>rotate)|(value<<(32-rotate)))&0xffffffff if rotate else value

def imm_writer(word:int)->dict[int,int|None]:
    """Model ARM r0-r3 writes, never read source operands or branch states.

    Return only assignments that are definitely an ARM data-processing MOV/MVN
    immediate with AL condition. Others are unknown, not silently reused.
    """
    condition=word>>28
    # ARM MOVW/MOVT are *not* ARM data-processing MOV immediates. They write
    # their destination register, but this limited tracer treats the result
    # as unknown instead of reusing an earlier constant.
    if (word&0x0ff00000) in (0x03000000,0x03400000):
        dest=(word>>12)&15
        return {dest:None} if dest<4 else {}
    cls=(word>>26)&3
    if cls==0:
        # Data processing only, excluding multiply, BX/BLX and related
        # special encodings that are outside a conservative register trace.
        if (word&0x0fc000f0)==0x00000090:
            return {r:None for r in range(4)}
        opcode=(word>>21)&15
        if opcode in (8,9,10,11):return {}
        rd=(word>>12)&15
        if rd>=4:return {}
        imm=((word>>25)&1)==1
        if condition==14 and imm and opcode in (13,15):
            raw=ror32(word&255,((word>>8)&15)*2)
            return {rd:raw if opcode==13 else (~raw)&0xffffffff}
        return {rd:None}
    if cls==1:
        if word&(1<<20):
            rd=(word>>12)&15
            return {rd:None} if rd<4 else {}
    if (word>>25)&7==4 and word&(1<<20):
        return {r:None for r in range(4) if word&(1<<r)}
    # Unmodeled instructions are never promoted to an immediate constant.
    return {}

def read_word(blob:bytes,segments:list[tuple[int,int,int]],pc:int)->int|None:
    for base,length,offset in segments:
        if base<=pc and pc+4<=base+length:
            return struct.unpack_from("<I",blob,offset+pc-base)[0]
    return None

def trace_locals(blob:bytes,segments:list[tuple[int,int,int]],
                 callsite:int,function_start:int)->dict[str,int|None]:
    if callsite%4 or function_start>callsite:
        raise ValueError("Invalid ARM callsite or function extent")
    output:dict[int,int|None]={}
    for index in range(1,WINDOW+1):
        pc=callsite-4*index
        if pc<function_start:break
        word=read_word(blob,segments,pc)
        if word is None:break
        # Branch or other call creates a basic-block boundary. Avoid
        # incorrectly propagating values from a different control flow.
        if (word>>25)&7==5:break
        for reg,value in imm_writer(word).items():
            if reg not in output:output[reg]=value
        if len(output)==4:break
    return {f"r{i}":output.get(i) for i in range(4)}

def build_report(blob:bytes,segments:list[tuple[int,int,int]],
                 funcs:list[tuple[int,int,str]])->dict:
    # Defined ELF functions; match direct BL calls to exact symbol entrypoint.
    known={addr:(size,name) for addr,size,name in funcs if size>0}
    matches=lambda text,prefixes:any(text.startswith(p) for p in prefixes)
    selected=sorted((a,n,name) for a,n,name in funcs
                    if matches(name,(*SOURCES,GENERAL,DISPATCH)))
    rows=[]
    edges=[]
    for address,size,name in selected:
        for callsite,target in arm.scan_direct_calls(blob,address,size,segments):
            info=known.get(target)
            if info is None:continue
            to=info[1]
            if (matches(name,SOURCES) and to.startswith(GENERAL)):
                rows.append({"source":name,"callsite":hex(callsite),
                             "instruction_args":trace_locals(blob,segments,callsite,address),
                             "known_values_are_runtime_proven":False})
            if ((matches(name,SOURCES) and to.startswith(GENERAL)) or
                (name.startswith(GENERAL) and to.startswith(DISPATCH)) or
                (name.startswith(DISPATCH) and
                 matches(to,(CAPTURE,COMMON)))):
                edges.append({"from":name,"to":to,"callsite":hex(callsite),
                              "relationship":"direct ARM BL, control flow unverified"})
    rows.sort(key=lambda x:int(x["callsite"],16))
    edges.sort(key=lambda x:int(x["callsite"],16))
    by_source=collections.Counter(x["source"].split("(")[0] for x in rows)
    constant_pairs=collections.Counter()
    for row in rows:
        r=row["instruction_args"]
        pair=(r["r0"],r["r1"])
        constant_pairs[pair]+=1
    pair_summary=[
        {"r0":a,"r1":b,"callsite_count":count,
         "native_parameter_semantics_proven":False}
        for (a,b),count in sorted(constant_pairs.items(),
                                   key=lambda pair:(pair[0][0] is None,
                                                    pair[0][0] or 0,
                                                    pair[0][1] is None,
                                                    pair[0][1] or 0))
    ]
    return {
        "evidence_source":"modified MFW 1.1 reference; Samsung SLP 1.15",
        "pw_ui_to_generic_setter_callsites":len(rows),
        "pw_ui_source_counts":dict(sorted(by_source.items())),
        "callsite_register_immediates":rows,
        "r0_r1_syntactic_immediate_pairs":pair_summary,
        "two_hop_menu_dispatch_edges":edges,
        "capture_menu_dispatch_edge_count":sum(
           x["from"].startswith(DISPATCH) and x["to"].startswith(CAPTURE)
           for x in edges),
        "actual_picture_wizard_parameter_id_verified":False,
        "per_callsite_runtime_values_verified":False,
        "capture_ipc_or_isp_execution_verified":False,
        "firmware_114_abi_verified":False,
        "device_write_or_flash_authorized":False,
        "limitations":[
            "Local immediate MOV/MVN r0-r3 only, within a bounded straight-line ARM instruction window",
            "Unknown registers and conditional paths are deliberately left null",
            "GUI_Set_System_Value also handles non-Picture-Wizard settings",
            "Two direct BL edges do not prove a reachable runtime path through switch/if conditions",
            "Capture menu dispatch is not proof of any hardware ISP register update",
            "Older modified Samsung 1.15 addresses are not NX300M stock 1.14 ABI",
        ],
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected bounded local ARM32 ELF regular file")
    blob=path.read_bytes()
    segments=arm.validate_header(blob)
    funcs=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(funcs)
    names=arm.offline_tool(["c++filt"],
        "\n".join(n for _,n in keys)+"\n").splitlines()
    if len(names)!=len(keys):raise ValueError("Symbol demangling failed")
    rows=[(address,funcs[(address,mangled)],name)
          for (address,mangled),name in zip(keys,names)]
    return build_report(blob,segments,rows)

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf",required=True,type=Path)
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=inspect(args.elf)
        if args.summary:
            result["callsite_register_immediates"]=len(result["callsite_register_immediates"])
            result["two_hop_menu_dispatch_edges"]=len(result["two_hop_menu_dispatch_edges"])
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0 if result["pw_ui_to_generic_setter_callsites"] else 3
    except (ValueError,OSError,struct.error) as exc:
        print("PW_REGISTER_EVIDENCE_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
