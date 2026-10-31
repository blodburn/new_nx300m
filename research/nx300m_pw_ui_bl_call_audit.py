#!/usr/bin/env python3
"""Read-only NX300M ARM32 direct-branch evidence for Picture Wizard UI.

Analyzes an existing, separately obtained private ARM ELF and its defined
function symbol ranges. Reports only static direct ARM BL instructions to
named functions. No firmware code is executed, patched, exported or uploaded.
No paths, offsets, call addresses or symbol names imply compatibility with
the owner's original firmware 1.14.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

MAX_BYTES = 32 * 1024 * 1024
MAX_SYMS = 25000
MAX_FUNC = 1024 * 1024
SYM = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+"
    r"(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)
NEEDLES = (
    "CAPPGUIGadgetPWState::handle(",
    "CAPPGUIGadgetPWState::onEnter(",
    "CAPPGUIGadgetPWState::Set_PWSlider_Minus(",
    "CAPPGUIGadgetPWState::Set_PWSlider_Plus(",
    "CAPPGUIGadgetPWState::Set_PWSlider(",
    "CAPPGUIGadgetView::set_gg_picture_wizard()",
    "CAPPGUIGadgetView::set_gg_picture_wizard_focus(",
    "CAPPGUIGadgetView::init(",
    "GUI_Set_System_Value(",
    "UI_Get_MM_Picture_wizard(",
    "set_picture_wizard(int)",
)
TARGET_ROLE = {
    "GUI_Set_System_Value(":"generic_system_value_dispatch",
    "CAPPGUIGadgetView::set_gg_picture_wizard_focus(":"picture_wizard_visual_focus",
    "CAPPGUIGadgetView::set_gg_picture_wizard()":"picture_wizard_visual_layout",
    "CAPPGUIGadgetPWState::Set_PWSlider_Minus(":"picture_wizard_ui_minus",
    "CAPPGUIGadgetPWState::Set_PWSlider_Plus(":"picture_wizard_ui_plus",
    "CAPPGUIGadgetPWState::Set_PWSlider(":"picture_wizard_ui_slider",
    "set_picture_wizard(int)":"older_local_only_setter_not_validated",
    "UI_Get_MM_Picture_wizard(":"get_picture_wizard_value_not_setter",
}

def offline_tool(argv:list[str],input_text:str|None=None)->str:
    try:
        cp=subprocess.run(argv,input=input_text,text=True,capture_output=True,
                          timeout=25,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError("Local symbol metadata tool unavailable") from exc
    if cp.returncode or len(cp.stdout)>25_000_000:
        raise ValueError("Local ELF symbols failed to decode")
    return cp.stdout

def validate_header(blob:bytes)->list[tuple[int,int,int]]:
    if len(blob)<52 or blob[:4]!=b"\x7fELF" or blob[4]!=1 or blob[5]!=1:
        raise ValueError("Expected little-endian ARM ELF32")
    kind,machine=struct.unpack_from("<HH",blob,16)
    flags=struct.unpack_from("<I",blob,36)[0]
    if kind not in (2,3) or machine!=40 or flags>>24!=5:
        raise ValueError("ELF is not an ARM EABI5 executable/shared object")
    phoff=struct.unpack_from("<I",blob,28)[0]
    entsize,count=struct.unpack_from("<HH",blob,42)
    if count>256 or entsize<32 or phoff+count*entsize>len(blob):
        raise ValueError("Invalid program header range")
    loads=[]
    for i in range(count):
        kind,off,vaddr,_,filesz,memsz,flags,_=struct.unpack_from(
            "<IIIIIIII",blob,phoff+i*entsize)
        if kind!=1:continue
        if off+filesz>len(blob) or filesz>memsz:
            raise ValueError("Invalid file-backed segment")
        # Only machine-code execution segments; never inspect data or DMA.
        if filesz and flags&1:
            loads.append((vaddr,filesz,off))
    if not loads:raise ValueError("No executable PT_LOAD segments")
    return loads

def decode_arm_bl(op:int,pc:int)->int|None:
    """ARM state, immediate BL only (not BLX, Thumb, indirect calls)."""
    if op>>28==15 or (op>>24)&15!=11:return None
    delta=(op&0xffffff)<<2
    if delta&0x2000000:delta-=0x4000000
    return (pc+8+delta)&0xffffffff

def scan_direct_calls(blob:bytes,addr:int,length:int,
                      segs:list[tuple[int,int,int]])->list[tuple[int,int]]:
    if addr%4 or length<4 or length>MAX_FUNC:
        return []
    segment=next(((base,off) for base,filesz,off in segs
                  if base<=addr and addr+length<=base+filesz),None)
    if segment is None:return []
    base,off=segment
    out=[]
    for rel in range(0,length-length%4,4):
        pos=off+addr-base+rel
        if pos+4>len(blob):raise ValueError("Truncated function body")
        word=struct.unpack_from("<I",blob,pos)[0]
        target=decode_arm_bl(word,addr+rel)
        if target is not None:
            out.append((addr+rel,target))
    return out

def parse_functions(metadata:str)->dict[tuple[int,str],int]:
    values={}
    for line in metadata.splitlines():
        m=SYM.match(line)
        if not m or m.group(3)=="UND":continue
        addr=int(m.group(1),16)
        length=int(m.group(2))
        if addr&1 or not (4<=length<=MAX_FUNC):continue
        name=m.group(4).split("@")[0]
        values[(addr,name)]=length
        if len(values)>MAX_SYMS:raise ValueError("Too many ELF functions")
    if not values:raise ValueError("No usable defined function symbols")
    return values

def classify(name:str)->str|None:
    for key in NEEDLES:
        if key in name:
            return key
    return None

def analyze(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
        raise ValueError("Expected a bounded local regular ELF file")
    blob=path.read_bytes()
    segs=validate_header(blob)
    entries=parse_functions(offline_tool(["readelf","-Ws",str(path)]))
    mangled=list(entries)
    demangled=offline_tool(["c++filt"], "\n".join(name for _,name in mangled)+"\n").splitlines()
    if len(demangled)!=len(mangled):raise ValueError("Symbol demangling length mismatch")
    named=[(addr,entries[(addr,name)],d) for (addr,name),d in zip(mangled,demangled)]
    relevant=[(addr,size,name) for addr,size,name in named if classify(name)]
    if not relevant:raise ValueError("No Picture Wizard UI candidate symbols found")
    target_names={}
    for addr,size,name in relevant:
        if any(name.startswith(k) for k in TARGET_ROLE):
            target_names.setdefault(addr,name)
    # A function may have weak duplicate/alias names. De-duplicate (addr,len,name).
    relevant=sorted(set(relevant))
    nodes=[]
    edges=[]
    for addr,size,name in relevant:
        calls=scan_direct_calls(blob,addr,size,segs)
        node={"function":name,"reference_address":hex(addr),"body_length":size,
              "direct_bl_total":len(calls)}
        nodes.append(node)
        for site,target in calls:
            if target not in target_names:continue
            to=target_names[target]
            edges.append({"from":name,"to":to,"callsite_address":hex(site),
                          "target_address":hex(target),
                          "target_role":next((v for key,v in TARGET_ROLE.items()
                                              if to.startswith(key)),"ui_related"),
                          "evidence_type":"ARM32 direct BL immediate in ELF function body"})
    edges.sort(key=lambda x:(x["from"],int(x["callsite_address"],16)))
    def count_matching(source_contains:str,target_prefix:str)->int:
        return sum(source_contains in x["from"] and x["to"].startswith(target_prefix)
                   for x in edges)
    return {
        "source_kind":"offline older modified MFW 1.1 / embedded Samsung SLP 1.15",
        "file_role":"private di-camera-app-nx300 ELF",
        "elf_sha256":hashlib.sha256(blob).hexdigest(),
        "function_candidates":nodes,
        "direct_bl_edges":edges,
        "direct_call_counts":{
          "pw_handle_to_generic_system_value":count_matching(
              "CAPPGUIGadgetPWState::handle(", "GUI_Set_System_Value("),
          "pw_minus_to_generic_system_value":count_matching(
              "CAPPGUIGadgetPWState::Set_PWSlider_Minus(", "GUI_Set_System_Value("),
          "pw_plus_to_generic_system_value":count_matching(
              "CAPPGUIGadgetPWState::Set_PWSlider_Plus(", "GUI_Set_System_Value("),
          "pw_handle_to_visual_focus":count_matching(
              "CAPPGUIGadgetPWState::handle(",
              "CAPPGUIGadgetView::set_gg_picture_wizard_focus("),
        },
        "generic_system_value_is_confirmed_picture_wizard_parameter":False,
        "gui_to_native_isp_end_to_end_verified":False,
        "firmware_114_abi_verified":False,
        "device_execution_or_firmware_patch_authorized":False,
        "limitations":[
          "ARM state direct BL instructions only, not indirect or Thumb calls",
          "A call to a generic system-setting function does not prove the parameter ID or effect",
          "All call addresses apply to this older modified reference, not stock NX300M 1.14",
          "ELF symbol coverage is not a complete dynamically linked call graph",
        ],
    }

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf",type=Path,required=True)
    ap.add_argument("--summary",action="store_true")
    a=ap.parse_args(argv)
    try:
        report=analyze(a.elf)
        if a.summary:
            report["direct_bl_edges"]=len(report["direct_bl_edges"])
            report["function_candidates"]=len(report["function_candidates"])
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,OSError,struct.error) as exc:
        print("UI_IPC_EVIDENCE_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":
    sys.exit(main())
