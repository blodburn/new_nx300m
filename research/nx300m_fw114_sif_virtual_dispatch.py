#!/usr/bin/env python3
"""Read-only ARM32 SIF vtable and indirect branch provenance (unofficial FW).

Inspects actual, separately extracted FW1.14 / FW1.15 private libsif.so.
Object vtable slots, R_ARM_RELATIVE relocations and ARM BLX register opcodes
are separate facts. Even a matched slot AND BLX do not prove execution,
instance type, call target, Y/C buffer ownership or a safe firmware hook.
Never loads firmware, accesses a camera, emits patch bytes or uploads binaries.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct

import nx300m_fw114_function_proofs as focus
import nx300m_pw_ui_bl_call_audit as arm

SIF_MAX_BYTES=2*1024*1024
SYMBOL=re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+(FUNC|OBJECT)\s+"
    r"(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)
RELOCATION=re.compile(r"^\s*([0-9a-fA-F]+)\s+\S+\s+(R_ARM_[A-Z0-9_]+)(?:\s|$)")
VTABLE_NAME="vtable for DscJfif"
TYPEINFO_NAME="typeinfo for DscJfif"
FUNCTIONS=(
    "DscJPEG::TaskMain(",
    "DscImage::EncodeYCC(",
    "DscImage::SaveExifImage(",
    "DscJfif::JpegEncode(",
)
MAX_FUNCTION_BYTES=65536
MAX_INDIRECT=96
MAX_VTABLE_BYTES=512


def reject(message:str):
    raise ValueError(message)


def symbol_index(text:str)->dict[str,dict]:
    """Use *defined* ELF object/function symbols; duplicate conflicting=reject."""
    raw={}
    for line in text.splitlines():
        m=SYMBOL.match(line)
        if not m or m[4]=="UND":
            continue
        mangled=m[5].split("@",1)[0]
        address=int(m[1],16)
        size=int(m[2])
        key=(mangled,m[3])
        value=(address,size)
        if key in raw and raw[key]!=value:
            reject("Conflicting function/object symbol definition")
        raw[key]=value
    if not raw or len(raw)>12000:
        reject("No bounded ELF defined symbols")
    keys=list(raw)
    decoded=arm.offline_tool(["c++filt"],
        "\n".join(k[0] for k in keys)+"\n").splitlines()
    if len(decoded)!=len(keys):
        reject("C++ symbol demangling incomplete")
    result={}
    ambiguous=set()
    for key,display in zip(keys,decoded):
        value=raw[key]
        name=(display,key[1])
        if name in result and result[name]!=value:
            # C1/C2 constructors and D0/D1/D2 destructors can demangle to
            # identical names at distinct native addresses. Never silently
            # choose one, but do not discard unrelated unique symbols.
            ambiguous.add(name)
        else:
            result[name]=value
    for name in ambiguous:
        result.pop(name,None)
    return {name:{"address":value[0],"size":value[1],"kind":kind}
            for (name,kind),value in result.items()}


def select(index:dict[str,dict], name:str, kind:str)->dict:
    chosen=[dict(value,name=key) for key,value in index.items()
            if value["kind"]==kind and key.startswith(name)]
    if len(chosen)!=1:
        reject("Missing or overloaded native symbol: "+name)
    return chosen[0]


def relocations(text:str)->dict[int,str]:
    result={}
    for line in text.splitlines():
        m=RELOCATION.match(line)
        if not m:
            continue
        addr=int(m[1],16)
        rel=m[2]
        if addr in result and result[addr]!=rel:
            reject("Conflicting ELF relocation")
        result[addr]=rel
    if not result or len(result)>100000:
        reject("No bounded ARM dynamic relocations")
    return result


def relocation_symbol_targets(text:str)->dict[int,dict]:
    """Extract R_ARM_* relocation symbol identity; 0 stored addend is NOT null.

    ARM ELF32 REL R_ARM_ABS32 references may store zero in the raw vtable
    slot and acquire a function pointer only during dynamic relocation.
    Require the exact relocation offset, type and symbol, not guessed
    runtime addresses or adjacent slot positions.
    """
    found={}
    pattern=re.compile(
        r"^\s*([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+"
        r"(R_ARM_[A-Z0-9_]+)\s+([0-9a-fA-F]+)\s+(\S+)"
    )
    for line in text.splitlines():
        hit=pattern.match(line)
        if not hit:
            continue
        addr=int(hit[1],16)
        name=hit[4].split("@",1)[0]
        item={
            "relocation_type":hit[2],
            "symbol_value":"0x%08x"%int(hit[3],16),
            "mangled_symbol":name,
        }
        if addr in found and found[addr]!=item:
            reject("Conflicting relocations at same ARM vtable offset")
        found[addr]=item
    return found


def read_word(data:bytes,loads:list[tuple[int,int,int]],vaddr:int)->int:
    position=focus.file_range_for_vaddr(loads,vaddr,4)
    return struct.unpack_from("<I",data,position)[0]


def decode_ldr_immediate(op:int)->dict|None:
    """ARM preindexed LDR word, no write-back; NOT a value provenance proof."""
    if (op>>28)==0xf or ((op>>26)&3)!=1 or (op>>25)&1 or (
        not (op>>24)&1
    ) or ((op>>22)&1) or ((op>>21)&1) or not ((op>>20)&1):
        return None
    return {
        "dst":(op>>12)&15,
        "base":(op>>16)&15,
        "offset":(op&4095)*(1 if (op>>23)&1 else -1),
    }


def decode_indirect(op:int)->tuple[str,int]|None:
    """ARM-state register branch only; exclude BX LR return and BLX immediate."""
    if op>>28==0xf:
        return None
    if op&0x0ffffff0==0x012fff30:
        return "BLX_register",op&15
    if op&0x0ffffff0==0x012fff10 and op&15!=14:
        return "BX_register_tail_candidate",op&15
    load=decode_ldr_immediate(op)
    if load and load["dst"]==15 and load["base"] not in (13,15):
        return "LDR_PC_indirect_tail_candidate",load["base"]
    return None


def load_chain(words:list[int],ix:int,reg:int)->dict:
    """Report nearby two-load syntax only, without claiming actual register state.

    Basic blocks, instructions that clobber a register, and cache/DMA ownership
    are not reconstructed. Conservative output always marks this a CANDIDATE.
    """
    if ix<1:return {"nearby_register_loads":[],"two_load_chain_candidate":False}
    first=None
    for p in range(ix-1,max(-1,ix-7),-1):
        ld=decode_ldr_immediate(words[p])
        if ld and ld["dst"]==reg:
            first=(p,ld)
            break
    if first is None:
        return {"nearby_register_loads":[],"two_load_chain_candidate":False}
    records=[{"relative_word_index":first[0],
              "target_reg":"r"+str(first[1]["dst"]),
              "base_reg":"r"+str(first[1]["base"]),
              "byte_offset":first[1]["offset"]}]
    for p in range(first[0]-1,max(-1,first[0]-7),-1):
        ld=decode_ldr_immediate(words[p])
        if ld and ld["dst"]==first[1]["base"]:
            records.append({
                "relative_word_index":p,
                "target_reg":"r"+str(ld["dst"]),
                "base_reg":"r"+str(ld["base"]),
                "byte_offset":ld["offset"],
            })
            break
    return {
        "nearby_register_loads":records,
        "two_load_chain_candidate":len(records)==2,
        "vtable_target_identity_proven":False,
    }


def register_writer_candidates(words:list[int],site:int,register:int)->list[dict]:
    """Find syntactic writes in file order, NOT execution-order provenance."""
    found=[]
    for i in range(site):
        op=words[i]
        ld=decode_ldr_immediate(op)
        if ld and ld["dst"]==register:
            found.append({
                "word_index":i,"opcode":"0x%08x"%op,
                "kind":"LDR_immediate",
                "source_register":"r%d"%ld["base"],
                "source_byte_offset":ld["offset"],
            })
        elif ((op>>28)!=15 and (op&0x0fe0fff0)==0x01a00000 and (
            (op>>12)&15)==register):
            found.append({
                "word_index":i,"opcode":"0x%08x"%op,
                "kind":"MOV_register",
                "source_register":"r%d"%(op&15),
                "source_byte_offset":None,
            })
    return found[-8:]


def scan_indirect(
    data:bytes, loads:list[tuple[int,int,int]], addr:int, size:int
)->dict:
    if addr%4 or not 4<=size<=MAX_FUNCTION_BYTES or size%4:
        reject("Function not bounded ARM-state words")
    offset=focus.file_range_for_vaddr(loads,addr,size)
    words=struct.unpack_from("<"+"I"*(size//4),data,offset)
    sites=[]
    summary={"BLX_register":0,"BX_register_tail_candidate":0,
             "LDR_PC_indirect_tail_candidate":0}
    for i,op in enumerate(words):
        decoded=decode_indirect(op)
        if not decoded:
            continue
        kind,reg=decoded
        summary[kind]+=1
        if len(sites)>=MAX_INDIRECT:
            reject("Too many native indirect sites for bounded report")
        sites.append({
            "function_relative_offset":4*i,
            "site_address":"0x%08x"%(addr+4*i),
            "opcode":"0x%08x"%op,
            "branch_kind":kind,
            "register":"r"+str(reg),
            **load_chain(list(words),i,reg),
            "preceding_arm_words":[
                {"relative_pc_offset":p*4,"opcode":"0x%08x"%words[p]}
                for p in range(max(0,i-8),i)
            ],
            "prior_register_writer_candidates":
                register_writer_candidates(list(words),i,reg),
            "provenance_control_flow_reconstructed":False,
        })
    return {
        **summary,
        "observed_indirect_branch_candidates":len(sites),
        "sites":sites,
        "runtime_branch_taken":False,
        "runtime_vtable_target_proven":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or (
        not 1024<=path.stat().st_size<=SIF_MAX_BYTES
    ):
        reject("Expected private bounded FW libsif.so")
    data=path.read_bytes()
    loads=focus.program_headers(path)
    symbols=symbol_index(arm.offline_tool(["readelf","-Ws",str(path)]))
    vtable=select(symbols,VTABLE_NAME,"OBJECT")
    if vtable["size"]<12 or vtable["size"]>MAX_VTABLE_BYTES or (
        vtable["size"]&3
    ):
        reject("Unexpected DscJfif vtable symbol bounds")
    relocation_text=arm.offline_tool(["readelf","-Wr",str(path)])
    relocs=relocations(relocation_text)
    relocation_targets=relocation_symbol_targets(relocation_text)
    defined={e["address"]:name for name,e in symbols.items()
             if e["kind"]=="FUNC" and e["size"]>0}
    slots=[]
    for offset in range(0,vtable["size"],4):
        vaddr=vtable["address"]+offset
        value=read_word(data,loads,vaddr)
        dest=defined.get(value) or defined.get(value&~1)
        target=relocation_targets.get(vaddr)
        if target and target["relocation_type"]=="R_ARM_ABS32":
            decoded=arm.offline_tool(
                ["c++filt"],target["mangled_symbol"]+"\n").strip()
            # The defined target from this exact ELF is cross-checked by
            # demangled identity AND the dynamic symbol's own value.
            own=symbols.get(decoded)
            defined_target=own is not None and own["kind"]=="FUNC" and (
                target["symbol_value"]=="0x%08x"%own["address"]
            )
        else:
            decoded=None
            defined_target=False
        slots.append({
            "vtable_byte_offset":offset,
            "slot_vaddr":"0x%08x"%vaddr,
            "stored_word":"0x%08x"%value,
            "relocation":relocs.get(vaddr,"NONE"),
            "relocation_symbol":decoded,
            "relocation_symbol_value":target["symbol_value"] if target else None,
            "relocation_is_defined_function":defined_target,
            "target_defined_function":dest,
            "target_exact_function_start":dest is not None,
            "runtime_pointer_value_observed":False,
        })
    methods={}
    for prefix in ("DscJfif::JpegEncode(","DscJfif::JpegDecode(",
                   "DscJfif::RawCompress("):
        fn=select(symbols,prefix,"FUNC")
        found=[slot["vtable_byte_offset"] for slot in slots
               if (int(slot["stored_word"],16)&~1)==(fn["address"]&~1) or (
                   slot["relocation_is_defined_function"] and
                   slot["relocation_symbol"]==fn["name"]
               )]
        methods[prefix]={
            "function_address":"0x%08x"%fn["address"],
            "vtable_matching_slot_offsets":found,
            "vtable_static_relocation_target_matched":bool(found),
            "on_camera_runtime_method_target_proven":False,
        }
    funcs={}
    for prefix in FUNCTIONS:
        fn=select(symbols,prefix,"FUNC")
        funcs[prefix]={
            "function_address":"0x%08x"%fn["address"],
            "function_bytes":fn["size"],
            **scan_indirect(data,loads,fn["address"],fn["size"])
        }
    return {
        "source_scope":"UNOFFICIAL_MIRROR_PRIVATE_SIF_ELF",
        "libsif_sha256":hashlib.sha256(data).hexdigest(),
        "vtable_name":VTABLE_NAME,
        "vtable_start":"0x%08x"%vtable["address"],
        "vtable_bytes":vtable["size"],
        "vtable_slots":slots,
        "recognized_methods":methods,
        "indirect_elf_functions":funcs,
        "dynamic_dispatch_between_encode_and_codec_proven":False,
        "camera_buffer_ownership_verified":False,
        "on_camera_runtime_execution_verified":False,
        "camera_patch_or_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    results={"fw114":inspect(fw114),"fw115":inspect(fw115)}
    methods={}
    for prefix in results["fw114"]["recognized_methods"]:
        methods[prefix]={
            "fw114_slots":results["fw114"]["recognized_methods"][prefix][
                "vtable_matching_slot_offsets"],
            "fw115_slots":results["fw115"]["recognized_methods"][prefix][
                "vtable_matching_slot_offsets"],
        }
    return {
        "source":"UNOFFICIAL_MIRROR_UNAUTHENTICATED",
        **results,
        "method_vtable_slot_comparison":methods,
        "camera_function_pointer_runtime_identity_proven":False,
        "camera_firmware_modification_permitted":False,
    }
