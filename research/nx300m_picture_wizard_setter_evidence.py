#!/usr/bin/env python3
"""Offline NX300M Picture Wizard setter ARM disassembly evidence checker.

Analyze saved Ghidra JSON only. Never call the target routine or modify an
ELF, firmware or device. This does NOT determine whether a different call
site or firmware 1.14 changes Picture Wizard modes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

MAX_JSON_BYTES=8*1024*1024
INSTR=re.compile(r"^(0x[0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$",re.I)
MOV_W=re.compile(r"\br3\s*,\s*0x([0-9a-f]+)",re.I)
IMM12=re.compile(r"\bcmp\s+r3\s*,\s*#0xc\b",re.I)
# Evidence only: no heuristics that imply an executable firmware patch.
def inspect(doc:dict)->dict:
    if not isinstance(doc,dict):
        raise ValueError("Not a Ghidra evidence object")
    normalized=doc.get("normalized_result")
    if not isinstance(normalized,dict):
        raise ValueError("Missing normalized procedure")
    proc=normalized.get("procedure")
    if not isinstance(proc,dict) or proc.get("name")!="_Z18set_picture_wizardi":
        raise ValueError("Not the expected Ghidra Picture Wizard setter")
    assembly=normalized.get("assembly")
    if not isinstance(assembly,list) or not (8<=len(assembly)<=4096):
        raise ValueError("Missing/bounded machine instructions")
    records=[]
    for line in assembly:
        if not isinstance(line,str) or len(line)>250:
            raise ValueError("Invalid instruction line")
        m=INSTR.match(line.strip())
        if not m:
            raise ValueError("Unrecognized Ghidra ARM instruction")
        records.append((int(m.group(1),16),m.group(2).lower(),m.group(3).strip()))
    if any(a>=b for (a,_,_),(b,_,_) in zip(records,records[1:])):
        raise ValueError("Instruction addresses not strictly ascending")
    direct_calls=[hex(a) for a,op,operand in records
                  if op in ("bl","blx") or op.startswith(("bl.","blx."))]
    branch_targets=[hex(a) for a,op,operand in records
                    if op in ("b","blt","ble","beq","bne","bgt","bge","bx")]
    pointer_lows=[]
    pointer_highs=[]
    for _,op,args in records:
        if op in ("movw","movt") and MOV_W.search(args):
            values=tuple(int(v,16) for v in MOV_W.findall(args))
            if len(values)!=1:
                raise ValueError("Ambiguous pointer initializer")
            (pointer_lows if op=="movw" else pointer_highs).append(values[0])
    # Verify the visible stores are only stack-relative. Some stored pointers
    # use r3, whose provenance is known only in this exact prologue sequence:
    # sub r3,r11,#0x38; sequential add r3,r3,#0x4 and str r2,[r3].
    store_ops=[(hex(addr),args) for addr,op,args in records if op.startswith("str")]
    stack_setup=sum(1 for _,op,args in records
                    if op=="sub" and re.fullmatch(r"r3\s*,\s*r11\s*,\s*#0x38",args))
    stack_pointer_step=sum(1 for _,op,args in records
                           if op=="add" and re.fullmatch(r"r3\s*,\s*r3\s*,\s*#0x4",args))
    stack_store_form=all(
        re.search(r"\[(?:sp|r11|r3)\s*(?:,|\])",args) is not None
        for _,args in store_ops
    )
    has_cmp12=any(op=="cmp" and re.fullmatch(r"r3\s*,\s*#0xc",args)
                  for _,op,args in records)
    has_neg_branch=any(op=="blt" for _,op,_ in records)
    clamps_12=has_cmp12 and has_neg_branch and any(
        op=="movge" and re.fullmatch(r"r3\s*,\s*#0xc",args)
        for _,op,args in records)
    # "no outward effect observed" is intentionally narrower than "no side
    # effects proven": static extraction can have unresolved references.
    strict_local_pattern=(
        len(pointer_lows)==13 and len(pointer_highs)==13 and
        len(direct_calls)==0 and stack_setup==1 and
        stack_pointer_step==13 and stack_store_form and
        len(store_ops)>=13 and records[-1][1]=="bx" and
        records[-1][2]=="lr" and clamps_12
    )
    reported_callers=normalized.get("callers")
    reported_callees=normalized.get("callees")
    return {
        "input_kind":"existing offline Ghidra evidence JSON",
        "procedure":proc.get("name"),
        "instruction_count":len(records),
        "clamp_lower_bound":0 if clamps_12 else None,
        "clamp_upper_bound":12 if clamps_12 else None,
        "pointer_initializer_lows":len(pointer_lows),
        "pointer_initializer_highs":len(pointer_highs),
        "candidate_pointer_count":min(len(pointer_lows),len(pointer_highs)),
        "direct_calls":direct_calls,
        "reported_callers":len(reported_callers) if isinstance(reported_callers,list) else None,
        "reported_callees":len(reported_callees) if isinstance(reported_callees,list) else None,
        "stack_relative_store_count":len(store_ops) if stack_store_form else None,
        "exact_reference_local_only_pattern":strict_local_pattern,
        "native_picture_wizard_mode_count_verified":False,
        "real_picture_wizard_setter_effect_verified":False,
        "firmware_114_equivalence_verified":False,
        "device_patching_authorized":False,
        "interpretation":(
          "This research reference's setter builds 13 pointer values locally, "
          "clamps an index to 0..12 and returns without a visible direct call. "
          "This is NOT evidence of an effective native style setter, 13 active "
          "native Picture Wizard styles, or any firmware 1.14 compatibility."
          if strict_local_pattern else
          "Insufficient static evidence for the known local-only reference pattern; "
          "no interface or device behavior may be assumed."
        ),
    }

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        path=args.evidence
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_JSON_BYTES:
            raise ValueError("Expected a bounded local JSON evidence file")
        doc=json.loads(path.read_text(encoding="utf8"))
        result=inspect(doc)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0 if result["exact_reference_local_only_pattern"] else 3
    except (ValueError,OSError,TypeError,json.JSONDecodeError) as e:
        print("SETTER_EVIDENCE_REJECTED: "+str(e),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
