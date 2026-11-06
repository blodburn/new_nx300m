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
MAX_REL_LINES=40000
MAX_POINTER_REFS=64
MAX_INDIRECT=150
EXPECTED_DYNAMIC_RELOCATIONS={
    ("0x0001bb14","R_ARM_GLOB_DAT"),
    ("0x0001babc","R_ARM_JUMP_SLOT"),
}
EXPECTED_RAW_ADDRESS_LITERAL_VADDR="0x00001214"


def qualified_indirect_reference_evidence(
    relocation_lines:list[str],pointer_candidates:list[dict],
    calls:list[dict],blx:list[dict]
)->dict:
    """Validate recorded ELF pointer witnesses; no runtime target claim."""
    seen=set()
    for line in relocation_lines:
        terms=line.split()
        if len(terms)<5 or terms[-1]!=TARGET:
            raise ValueError("Invalid native Q-copier ELF relocation")
        seen.add((f"0x{int(terms[0],16):08x}",terms[2]))
    if seen!=EXPECTED_DYNAMIC_RELOCATIONS:
        raise ValueError("Changed Q-copier ELF dynamic linkage")
    exact=[p for p in pointer_candidates
           if p["elf_vaddr"]==EXPECTED_RAW_ADDRESS_LITERAL_VADDR
           and p["value"]=="0x0000b0e0"]
    if len(exact)!=1:
        raise ValueError("Missing verified FW function pointer literal")
    return {
        "glob_dat_site":"0x0001bb14",
        "jump_slot_site":"0x0001babc",
        "literal_vaddr":"0x00001214",
        "literal_value":"0x0000b0e0",
        "direct_arm_bl_or_plt_callsite_count":len(calls),
        "indirect_arm_blx_site_count":len(blx),
        "target_address_present_in_runtime_linkage":True,
        "indirect_blx_linked_to_target_function_proven":False,
        "runtime_copy_function_executed_proven":False,
        "q_source_object_identity_proven":False,
    }


Q_ENTRY_OPCODES={
    0x0000b0f4:0xe50b0018, # STR incoming r0,[fp,#-24]
    0x0000b0f8:0xe50b101c, # STR incoming r1,[fp,#-28] source Q
    0x0000b118:0xe51b301c, # LDR r3,[fp,#-28] Q
    0x0000b184:0xe51b301c, # LDR r3,[fp,#-28] Q
    0x0000b188:0xe5932008, # LDR r2,[r3,#8] Q+8
}


def verify_source_q_incoming(words:tuple[int,...])->dict:
    if len(words)!=TARGET_SIZE//4:
        raise ValueError("Wrong FW field copier function length")
    for pc,expected in Q_ENTRY_OPCODES.items():
        if words[(pc-TARGET_START)//4]!=expected:
            raise ValueError(f"Changed source Q AAPCS input at {pc:#x}")
    return {
        "source_q_is_input_register":"r1",
        "q_register_save_pc":"0x0000b0f8",
        "q_saved_at":"[fp,-28]",
        "q_field_plus8_load_pc":"0x0000b188",
        "q_source_value_positive_proven":False,
        "incoming_r1_callers_or_execution_proven":False,
    }


def arm_blx_register(word:int)->dict|None:
    """Accept only A32 BLX Rm register indirect calls, not BX/BL."""
    if type(word) is not int or not 0<=word<=0xffffffff:
        raise ValueError("Invalid native A32 instruction")
    if (word&0x0ffffff0)!=0x012fff30 or (word>>28)==15:
        return None
    return {
        "via_register":f"r{word&15}",
        "opcode":f"0x{word:08x}",
        "target_is_update_empty_seg_proven":False,
        "indirect_branch_executed_proven":False,
    }


def aligned_literal_refs(blob:bytes,loads:list,needle:int)->list[dict]:
    """Read bounded file-backed aligned raw pointer candidates; no xrefs."""
    results=[]
    for base,length,offset in loads:
        for fileoff in range(offset+(4-offset%4)%4,offset+length-3,4):
            word=struct.unpack_from("<I",blob,fileoff)[0]
            if word not in (needle,needle|1):
                continue
            results.append({
                "file_offset":f"0x{fileoff:08x}",
                "elf_vaddr":f"0x{base+fileoff-offset:08x}",
                "value":f"0x{word:08x}",
                "literal_referenced_by_code_proven":False,
            })
            if len(results)>MAX_POINTER_REFS:
                raise ValueError("Too many firmware function-pointer literals")
    return results


def named_native_relocations(text:str)->list[str]:
    """Capture symbol-linked REL text only; no proprietary image payload."""
    found=[]
    for i,line in enumerate(text.splitlines()):
        if i>MAX_REL_LINES:
            raise ValueError("Unbounded native relocation text")
        if TARGET not in line:
            continue
        found.append(line.strip()[:280])
        if len(found)>MAX_POINTER_REFS:
            raise ValueError("Too many target symbol relocations")
    return found



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
    relocation_text=abi.tool(["readelf","-Wr",str(native)])
    relocs=jpeg.relocations(relocation_text)
    symbol_relocations=named_native_relocations(relocation_text)
    pointer_literals=aligned_literal_refs(blob,loads,TARGET_START)
    callers=[]
    indirect_calls=[]
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
            for i,opcode in enumerate(words):
                call=arm_blx_register(opcode)
                if call is None:
                    continue
                indirect_calls.append({
                    "function":f["symbol"],
                    "site":f"0x{start+4*i:08x}",
                    **call,
                    "preceding_a32_words":[{
                        "pc":f"0x{start+4*j:08x}",
                        "opcode":f"0x{words[j]:08x}"}
                        for j in range(max(0,i-10),i)],
                })
                if len(indirect_calls)>MAX_INDIRECT:
                    raise ValueError("Too many candidate ARM BLX register calls")
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
    dynamic_reference_proof=qualified_indirect_reference_evidence(
        symbol_relocations,pointer_literals,callers,indirect_calls)
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
        "source_q_abi_proof":verify_source_q_incoming(words),
        "dynamic_reference_proof":dynamic_reference_proof,
        "raw_function_pointer_literals":pointer_literals,
        "named_symbol_relocations":symbol_relocations,
        "sysmmap_indirect_blx_candidates":indirect_calls,
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
