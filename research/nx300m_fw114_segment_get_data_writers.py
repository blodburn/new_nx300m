#!/usr/bin/env python3
"""Read-only discovery of FW1.14/1.15 SYSMMAP segment record +12 writers.

Only reads bounded native ELF32 ARM-state opcodes from privately extracted
third-party firmware. An apparent STR [reg,#12] is a candidate store, NOT
evidence it modifies the record returned by sysmmap_segment_get_data.
No device access, firmware modification, flash, or vendor ELF export.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_pw_ui_bl_call_audit as arm
import nx300m_native_jpeg_abi_boundary_audit as jpeg

GET_DATA = "sysmmap_segment_get_data"
PREFIX = "sysmmap_segment_"
MAX_SYM_LINES = 50000
MAX_CANDIDATES = 128
MAX_FUNCTIONS = 100
MAX_FUNC_SIZE = 8192
# Includes LOCAL defined function symbols, not just externally exported.
FUNC = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+"
    r"(?:LOCAL|GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(.+?)\s*$"
)

ACCESSOR_ADDRESS=0x00009ed4
ACCESSOR_SIZE=72
STORE_FUNCTION="sysmmap_segment_update_empty_seg"
STORE_ADDRESS=0x0000b19c
ACCESSOR_EXACT_WORDS={
    0x9ee0:0xe50b0010,  # stack save input r0
    0x9ef0:0xe3530000,  # CMP r3,#0
    0x9ef4:0x0a000003,  # BEQ 0x9f08 (returns initialized zero)
    0x9ef8:0xe51b3010,  # LDR r3,[fp,#-16]
    0x9efc:0xe5933000,  # LDR r3,[r3]
    0x9f00:0xe5933004,  # LDR r3,[r3,#4]
    0x9f04:0xe50b3008,  # STR r3,[fp,#-8]
    0x9f08:0xe51b3008,  # LDR r3,[fp,#-8]
    0x9f0c:0xe1a00003,  # MOV r0,r3
    0x9f18:0xe12fff1e,  # BX LR
}
STORED_WORD=0xe583200c  # STR r2,[r3,#12], NOT an SP write


def accessor_static_pointer_witness(words:tuple[int,...],start:int)->dict:
    if start!=ACCESSOR_ADDRESS or len(words)!=ACCESSOR_SIZE//4:
        raise ValueError("Wrong native segment accessor definition")
    for address,expected in ACCESSOR_EXACT_WORDS.items():
        idx=(address-start)//4
        if idx<0 or idx>=len(words) or words[idx]!=expected:
            raise ValueError("Changed native segment get_data pointer chain")
    return {
        "get_data_start":f"0x{start:08x}",
        "non_null_arm_pointer_dereference":
            "r0_return = *( *(input_r0 + 0) + 4 )",
        "null_arg_returns_zero_candidate":True,
        "native_input_pointer_ownership_proven":False,
        "record_plus12_writer_alias_proven":False,
        "actual_camera_mapped_bytes_proven":False,
    }


def target_writer_context(
    words:tuple[int,...],start:int,site:int=STORE_ADDRESS,
)->dict:
    index=(site-start)//4
    if (start<0 or start%4 or site<start or site%4 or
        index>=len(words) or index<0 or words[index]!=STORED_WORD):
        raise ValueError("Changed native segment record+12 store")
    lo=max(0,index-40)
    hi=min(len(words),index+13)
    return {
        "site":f"0x{site:08x}",
        "opcode":f"0x{STORED_WORD:08x}",
        "prior_arm_words":[
            {"pc":f"0x{start+4*i:08x}","opcode":f"0x{words[i]:08x}"}
            for i in range(lo,index)],
        "following_arm_words":[
            {"pc":f"0x{start+4*i:08x}","opcode":f"0x{words[i]:08x}"}
            for i in range(index+1,hi)],
        "record_return_alias_to_writer_r3_proven":False,
        "stored_r2_runtime_value_observed":False,
        "write_always_executed_proven":False,
    }


def segment_functions(symbol_table:str)->list[dict]:
    """Deduplicate .dynsym / .symtab without making up symbol addresses."""
    found={}
    for index,line in enumerate(symbol_table.splitlines()):
        if index>MAX_SYM_LINES:
            raise ValueError("Unbounded firmware symbol inventory")
        m=FUNC.match(line)
        if not m:
            continue
        name=m.group(4).split("@",1)[0]
        if not name.startswith(PREFIX) or m.group(3)=="UND":
            continue
        addr,size=int(m.group(1),16),int(m.group(2))
        if not (addr%4==0 and 4<=size<=MAX_FUNC_SIZE and size%4==0):
            continue
        key=(name,addr,size)
        found[key]={"symbol":name,"address":addr,"size":size}
        if len(found)>MAX_FUNCTIONS:
            raise ValueError("Unbounded SYSMMAP segment function inventory")
    return sorted(found.values(),key=lambda x:(x["address"],x["symbol"]))


def arm_word_offset12(word:int)->dict|None:
    """Strict A32 immediate word LDR/STR [Rn,#12] (no writeback)."""
    if not isinstance(word,int) or word<0 or word>0xffffffff:
        raise ValueError("Invalid ARM opcode")
    # single-word data transfer, immediate, pre-indexed positive offset,
    # no writeback and no byte access. Can be conditional.
    if ((word>>26)&3)!=1 or ((word>>25)&1)!=0 or (
        (word>>24)&1)!=1 or ((word>>23)&1)!=1 or (
        (word>>22)&1)!=0 or ((word>>21)&1)!=0 or (
        word&0xfff)!=12:
        return None
    cond=(word>>28)&15
    if cond==15:
        return None
    return {
        "operation":"LDR" if (word>>20)&1 else "STR",
        "base_register":f"r{(word>>16)&15}",
        "value_register":f"r{(word>>12)&15}",
        "conditional":cond!=14,
        "opcode":f"0x{word:08x}",
        "offset_bytes":12,
        "record_identity_confirmed":False,
    }


def scan_segment_function(
    image:bytes,loads:list,entry:dict,relocations:dict[int,str]
)->dict:
    start,size=entry["address"],entry["size"]
    offset=elf.file_range_for_vaddr(loads,start,size)
    if offset<0 or offset+size>len(image):
        raise ValueError("Bad private segment native code extent")
    words=struct.unpack_from("<"+"I"*(size//4),image,offset)
    candidates=[]
    for index,word in enumerate(words):
        decoded=arm_word_offset12(word)
        if decoded is not None:
            candidates.append({
                **decoded,
                "site":f"0x{start+4*index:08x}",
            })
        if len(candidates)>MAX_CANDIDATES:
            raise ValueError("Unbounded segment +12 load/store candidates")
    edges=[]
    for site,target in arm.scan_direct_calls(image,start,size,loads):
        try:
            got=jpeg.plt_got(image,loads,target)
            name=relocations.get(got)
        except ValueError:
            name=None
        if name==GET_DATA:
            edges.append(f"0x{site:08x}")
        if len(edges)>MAX_CANDIDATES:
            raise ValueError("Unbounded segment record accessor callers")
    if entry["symbol"]==GET_DATA:
        first=[{"pc":f"0x{start+4*i:08x}",
                "word":f"0x{w:08x}"} for i,w in
               enumerate(words[:32])]
        last=[{"pc":f"0x{start+4*i:08x}",
               "word":f"0x{words[i]:08x}"} for i in
              range(max(0,len(words)-12),len(words))]
    else:
        first=[]
        last=[]
    return {
        "symbol":entry["symbol"],
        "address":f"0x{start:08x}",
        "size_bytes":size,
        "body_sha256":hashlib.sha256(image[offset:offset+size]).hexdigest(),
        "offset_plus12_arm_load_store_candidates":candidates,
        "direct_calls_via_plt_to_segment_get_data":edges,
        "accessor_entry_arm_words":first,
        "accessor_exit_arm_words":last,
        "accessor_pointer_static_proof":(
            accessor_static_pointer_witness(words,start)
            if entry["symbol"]==GET_DATA else None),
        "record_plus12_candidate_writer_context":(
            target_writer_context(words,start)
            if entry["symbol"]==STORE_FUNCTION else None),
        "real_record_writer_proven":False,
        "actual_mapped_bytes_observed":False,
    }


def inspect(root:Path)->dict:
    path=provider.find_provider(root,provider.LIBRARY)
    image=path.read_bytes()
    loads=elf.program_headers(path)
    table=abi.tool(["readelf","-Ws",str(path)])
    symbols=segment_functions(table)
    relocations=jpeg.relocations(abi.tool(["readelf","-Wr",str(path)]))
    examined=[scan_segment_function(image,loads,e,relocations)
              for e in symbols]
    accessor=[f for f in examined if f["symbol"]==GET_DATA]
    if len(accessor)!=1:
        # An imported function is not resolved by pretending local code.
        raise ValueError("Missing or ambiguous defined native get_data body")
    stores=[{"function":f["symbol"],**site}
            for f in examined for site in
            f["offset_plus12_arm_load_store_candidates"]
            if site["operation"]=="STR"]
    if len(stores)>MAX_CANDIDATES:
        raise ValueError("Unbounded segment size record store sites")
    return {
        "scope":"PRIVATE_UNOFFICIAL_ARM_SEGMENT_RECORD_12_CANDIDATES",
        "provider_sha256":hashlib.sha256(image).hexdigest(),
        "accessor":accessor[0],
        "segment_functions_examined":examined,
        "store_offset12_candidates":stores,
        "record_identity_proven":False,
        "record_plus12_initialization_proven":False,
        "record_plus12_live_value_known":False,
        "descriptor_plus4_equivalence_proven":False,
        "physical_camera_memory_extent_verified":False,
        "camera_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a,b=inspect(fw114),inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "same_provider_bytes":a["provider_sha256"]==b["provider_sha256"],
        "same_accessor_body":a["accessor"]["body_sha256"]==
            b["accessor"]["body_sha256"],
        "same_candidate_writers":a["store_offset12_candidates"]==
            b["store_offset12_candidates"],
        "proves_actual_camera_mmap_length":False,
        "camera_flash_permitted":False,
    }
