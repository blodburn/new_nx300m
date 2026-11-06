#!/usr/bin/env python3
"""Find callers of FW1.14/1.15 SYSMMAP field-copy and Q+8 candidates.

Offline ARM32 ELF and PLT/GOT audit of privately extracted, untrusted
mirror firmware. Direct BL callsites and [base,#8] stores are static
candidates: do not infer dynamic arguments, positive sizes, real mmap
extent, DMA-safe ownership, or permit installation on a camera.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_function_proofs as elf
import nx300m_fw114_segment_get_data_writers as records
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_fw114_sysmmap_osif_arg_windows as windows
import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_pw_ui_bl_call_audit as arm

TARGET="sysmmap_segment_update_empty_seg"
TARGET_START=0x0000b0e0
TARGET_SIZE=244
MAX_FUNCTIONS=6500
MAX_CALLERS=48
MAX_FIELD_CANDIDATES=120
MAX_FUNCTION_BYTES=32768
MAX_FILE_BYTES=32*1024*1024


def defined_functions(symbol_table:str)->list[dict]:
    """Include all native functions, not only the segment API prefix."""
    found={}
    for line_number,line in enumerate(symbol_table.splitlines()):
        if line_number>75000:
            raise ValueError("Native ARM symbol table unbounded")
        m=records.FUNC.match(line)
        if not m or m.group(3)=="UND":
            continue
        addr,size=int(m.group(1),16),int(m.group(2))
        if not (addr and addr%4==0 and size>=4 and
                size%4==0 and size<=MAX_FUNCTION_BYTES):
            continue
        name=m.group(4).split("@",1)[0]
        found[(addr,size,name)]={
            "symbol":name,"address":addr,"size":size,
        }
        if len(found)>MAX_FUNCTIONS:
            raise ValueError("Native ARM function inventory too large")
    return sorted(found.values(),key=lambda x:(x["address"],x["symbol"]))


def decode_record_word_store_plus8(word:int)->dict|None:
    """Recognize ARM32 STR Rt,[Rn,#8], no SP/FP base and no writeback."""
    if type(word) is not int or not 0<=word<=0xffffffff:
        raise ValueError("Invalid ARM32 word")
    if ((word>>26)&3)!=1 or (word>>25)&1 or not (word>>24)&1 or (
        not (word>>23)&1 or (word>>22)&1 or (word>>21)&1 or
        (word>>20)&1 or (word&0xfff)!=8):
        return None
    cond=(word>>28)&15
    base=(word>>16)&15
    rt=(word>>12)&15
    if cond==15 or base in (11,13,15):
        return None
    return {
        "opcode":f"0x{word:08x}",
        "base":f"r{base}",
        "source":f"r{rt}",
        "conditional":cond!=14,
        "offset":8,
        "base_is_get_data_record_proven":False,
        "value_is_positive_size_proven":False,
    }


def inspect(root:Path)->dict:
    native=provider.find_provider(root,provider.LIBRARY)
    blob=native.read_bytes()
    if not 52<=len(blob)<=MAX_FILE_BYTES:
        raise ValueError("Firmware memory manager size out of bounds")
    loads=elf.program_headers(native)
    table=abi.tool(["readelf","-Ws",str(native)])
    funcs=defined_functions(table)
    target=[f for f in funcs if f["symbol"]==TARGET and
            f["address"]==TARGET_START and f["size"]==TARGET_SIZE]
    if len(target)!=1:
        raise ValueError("Missing or ambiguous native source-field copier")
    relocs=jpeg.relocations(abi.tool(["readelf","-Wr",str(native)]))
    callers=[]
    candidate_stores=[]
    for f in funcs:
        start,size=f["address"],f["size"]
        try:
            offset=elf.file_range_for_vaddr(loads,start,size)
        except (KeyError,ValueError):
            continue
        if offset<0 or offset+size>len(blob):
            raise ValueError("Malformed native function boundary")
        # Only other sysmmap_ functions need +8 candidate store inventory;
        # but ALL functions are scanned for real direct target callers.
        if f["symbol"].startswith("sysmmap_"):
            words=struct.unpack_from("<"+"I"*(size//4),blob,offset)
            for i,opcode in enumerate(words):
                store=decode_record_word_store_plus8(opcode)
                if store is None:
                    continue
                candidate_stores.append({
                    "function":f["symbol"],
                    "site":f"0x{start+4*i:08x}",**store,
                })
                if len(candidate_stores)>MAX_FIELD_CANDIDATES:
                    raise ValueError("Unbounded SYSMMAP +8 store inventory")
        else:
            words=None
        for site,target_address in arm.scan_direct_calls(
            blob,start,size,loads):
            if target_address==TARGET_START:
                kind="native_direct"
            else:
                try:
                    got=jpeg.plt_got(blob,loads,target_address)
                    symbol=relocs.get(got)
                except (KeyError,ValueError):
                    symbol=None
                if symbol!=TARGET:
                    continue
                kind="arm_plt_import"
            if words is None:
                words=struct.unpack_from("<"+"I"*(size//4),blob,offset)
            evidence=windows.argument_context(
                words,start,site,lookback=32)
            callers.append({
                "function":f["symbol"],
                "address":f"0x{start:08x}",
                "body_size":size,
                "body_sha256":hashlib.sha256(
                    blob[offset:offset+size]).hexdigest(),
                "site":f"0x{site:08x}",
                "call_kind":kind,
                "r0_candidate_writers":
                    evidence["candidate_argument_writers"]["r0"],
                "r1_candidate_writers":
                    evidence["candidate_argument_writers"]["r1"],
                "arm_words_before_call":evidence["preceding_arm_words"],
                "first_20_arm_words":[{
                    "pc":f"0x{start+4*i:08x}",
                    "opcode":f"0x{word:08x}"}
                    for i,word in enumerate(words[:20])],
                "source_Q_from_caller_proven":False,
                "source_Q_plus8_positive_value_proven":False,
                "actual_camera_memory_bytes_verified":False,
            })
            if len(callers)>MAX_CALLERS:
                raise ValueError("Unbounded source-field copier callers")
    offset=elf.file_range_for_vaddr(loads,TARGET_START,TARGET_SIZE)
    words=struct.unpack_from("<"+"I"*(TARGET_SIZE//4),blob,offset)
    return {
        "scope":"OFFLINE_UNAUTHENTICATED_ARM32_SOURCE_FIELD_CALLERS",
        "native_provider":provider.LIBRARY,
        "provider_sha256":hashlib.sha256(blob).hexdigest(),
        "copy_target":TARGET,
        "copy_target_address":"0x0000b0e0",
        "copy_target_prologue":[{
            "pc":f"0x{TARGET_START+i*4:08x}",
            "opcode":f"0x{word:08x}"}
            for i,word in enumerate(words[:24])],
        "callers":sorted(callers,key=lambda x:(x["site"],x["function"])),
        "source_plus8_store_candidates":sorted(
            candidate_stores,key=lambda x:(x["site"],x["function"])),
        "complete_cross_function_Q_dataflow_proven":False,
        "positive_live_size_value_observed":False,
        "kernel_mmap_extent_verified":False,
        "physical_camera_flash_permitted":False,
    }


def compare_versions(root114:Path,root115:Path)->dict:
    a,b=inspect(root114),inspect(root115)
    return {
        "fw114":a,"fw115":b,
        "same_native_provider":
            a["provider_sha256"]==b["provider_sha256"],
        "same_direct_source_callers":
            a["callers"]==b["callers"],
        "same_plus8_store_candidates":
            a["source_plus8_store_candidates"]==
            b["source_plus8_store_candidates"],
        "camera_buffer_size_verified":False,
        "firmware_flash_permitted":False,
    }
