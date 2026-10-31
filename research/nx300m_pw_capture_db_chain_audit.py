#!/usr/bin/env python3
"""Read-only NX300M capture menu -> value -> DB setter direct-call evidence.

Audits the existing MODIFIED Samsung 1.15 reference ELF, NOT the owner's
original stock 1.14. Enumerates only direct ARM-state BL targets among six
explicitly named functions. This is a static graph, not proof of reachable
Picture Wizard control flow, IPC, persistent DB writes or ISP changes.

Large DB switch routines contain embedded lookup tables that can appear to
be BL instructions in linear byte scans. Their bodies are intentionally
EXCLUDED from branch scanning. No firmware execution or patching.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

CAPTURE_INFO="UI_Set_Capture_Menu_Info_By_GUI("
CAPTURE_VALUE="UI_Set_Capture_Menu_Value("
SET_VALUE="UI_Set_Value("
SET_CAPTURE="UI_Set_Value_Capture_Menu("
GET_DB_ID="UI_Get_DB_ID_Capture_Menu("
SET_DB="UI_Set_DB_Value_Capture_Menu("
NODES=(CAPTURE_INFO,CAPTURE_VALUE,SET_VALUE,SET_CAPTURE,GET_DB_ID,SET_DB)
# Exactly these function bodies are scanned: no blind decode of DB switch
# tables or undefined symbols as function calls.
SCANNED=(CAPTURE_INFO,CAPTURE_VALUE,SET_VALUE,SET_CAPTURE)
REQUIRED={
 (CAPTURE_INFO,CAPTURE_VALUE):2,
 (CAPTURE_INFO,SET_VALUE):2,
 (CAPTURE_VALUE,SET_VALUE):18,
 (SET_VALUE,SET_CAPTURE):1,
 (SET_CAPTURE,GET_DB_ID):1,
 (SET_CAPTURE,SET_DB):1,
}

def label(full_name:str)->str|None:
    for key in NODES:
        if full_name.startswith(key):
            return key
    return None

def graph(blob:bytes,segs:list[tuple[int,int,int]],
          functions:list[tuple[int,int,str]])->dict:
    unique:dict[str,tuple[int,int,str]]={}
    for address,size,name in functions:
        key=label(name)
        if key:
            if key in unique:raise ValueError("Ambiguous named capture function symbol")
            if not (4<=size<=arm.MAX_FUNC):
                raise ValueError("Missing or unbounded source code body")
            unique[key]=(address,size,name)
    if set(unique)!=set(NODES):
        raise ValueError("Missing exact named Capture/DB function symbols")
    named_addresses={data[0]:key for key,data in unique.items()}
    weights={}
    callsite_map={}
    for src in SCANNED:
        addr,size,_=unique[src]
        for site,dest in arm.scan_direct_calls(blob,addr,size,segs):
            target=named_addresses.get(dest)
            if target is None:continue
            k=(src,target)
            weights[k]=weights.get(k,0)+1
            callsite_map.setdefault(k,[]).append(hex(site))
    results=[]
    for (src,dst),minimum in REQUIRED.items():
        count=weights.get((src,dst),0)
        results.append({
          "source":unique[src][2],"target":unique[dst][2],
          "direct_arm_bl_count":count,
          "reference_callsites":callsite_map.get((src,dst),[]),
          "minimum_expected_reference_count":minimum,
          "reference_static_evidence_verified":count==minimum,
          "runtime_control_flow_or_parameter_identity_proven":False,
        })
    pass_reference=all(x["reference_static_evidence_verified"] for x in results)
    return {
      "research_reference":"MFW modified release 1.1 / embedded Samsung NX300M 1.15",
      "function_nodes":len(unique),
      "verified_static_edge_groups":sum(x["reference_static_evidence_verified"] for x in results),
      "reference_required_edge_groups":len(REQUIRED),
      "required_direct_bl_callsite_total":sum(x["direct_arm_bl_count"] for x in results),
      "direct_call_evidence":results,
      "reference_static_pattern_verified":pass_reference,
      "db_write_body_excluded_due_to_embedded_switch_tables":True,
      "ui_picture_wizard_event_reaches_db_setter_verified":False,
      "db_function_changes_persistent_storage_verified":False,
      "camera_capture_ipc_or_isp_execution_verified":False,
      "actual_nx300m_firmware_114_abi_verified":False,
      "flash_or_camera_memory_patch_permitted":False,
      "limitations":[
        "Adjacent direct BL edges do not prove their conditional paths execute together",
        "DB value function is a named call target; its body is not interpreted as actual disk writes",
        "No ARM Thumb, indirect calls, dynamic PLT or exact Capture menu setting IDs are resolved",
        "No original stock NX300M 1.14 image or hardware recovery is verified",
      ],
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected local regular bounded ARM ELF")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    symbols=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(symbols)
    decoded=arm.offline_tool(["c++filt"],
        "\n".join(mangled for _,mangled in keys)+"\n").splitlines()
    if len(decoded)!=len(keys):raise ValueError("Demangle/symbol mismatch")
    funcs=[(address,symbols[(address,name)],dem)
           for (address,name),dem in zip(keys,decoded)]
    return graph(blob,segs,funcs)

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf",required=True,type=Path)
    p.add_argument("--summary",action="store_true")
    args=p.parse_args(argv)
    try:
        report=inspect(args.elf)
        if args.summary:
            report["direct_call_evidence"]=[
                {"source":x["source"],"target":x["target"],
                 "direct_arm_bl_count":x["direct_arm_bl_count"],
                 "reference_static_evidence_verified":x["reference_static_evidence_verified"]}
                for x in report["direct_call_evidence"]]
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0 if report["reference_static_pattern_verified"] else 3
    except (OSError,ValueError,struct.error) as exc:
        print("CAPTURE_DB_CHAIN_REJECTED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":sys.exit(main())
