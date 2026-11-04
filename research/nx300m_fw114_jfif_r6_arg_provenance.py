#!/usr/bin/env python3
"""Static sJpegOp ARM32 register-to-stack provenance from real libsif ELF.

Offline-only analysis of exact FW1.14/1.15 symbols and code bytes.
No camera I/O, firmware loading, memory writing, native patch or flashing.
The file is a third-party mirror, NOT manufacturer-authenticated.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif

FUNCTION = "DscJfif::JpegEncode("
FIELD_BYTE_OFFSET = 12
MAX_WORDS = 1024


def decode_mem_word(word: int) -> dict | None:
    """ARM pre-indexed 32-bit immediate LDR/STR, without writeback.

    This does NOT model condition flags, execution order, memory aliases
    or Thumb instructions. Preserve condition and reject unusual modes.
    """
    cond = (word >> 28) & 15
    if (cond == 15 or (word >> 26) & 3 != 1 or
        (word >> 25) & 1 or (word >> 24) & 1 == 0 or
        (word >> 22) & 1 or (word >> 21) & 1):
        return None
    return {
        "kind": "LDR" if (word >> 20) & 1 else "STR",
        "base_register": (word >> 16) & 15,
        "data_register": (word >> 12) & 15,
        "offset": (1 if (word >> 23) & 1 else -1) * (word & 0xfff),
        "condition": cond,
    }


def select_provenance(words: list[int], start: int) -> dict:
    if not words or len(words) > MAX_WORDS or start & 3:
        raise ValueError("Invalid bounded ARM function code")
    calls=[i for i,w in enumerate(words)
           if sif.decode_indirect(w)==("BLX_register",6)]
    if len(calls)!=1:
        raise ValueError("Missing or ambiguous BLX r6 in JpegEncode")
    call=calls[0]
    load_sites=[]
    for i,w in enumerate(words[:call]):
        info=decode_mem_word(w)
        if (info and info["kind"]=="LDR" and
            info["data_register"]==6 and info["base_register"]==3 and
            info["offset"]==FIELD_BYTE_OFFSET):
            load_sites.append(i)
    if len(load_sites)!=1:
        raise ValueError("Missing or ambiguous r6 <- [r3 + 12] writer")
    load=load_sites[0]
    # A pointer base used at the writer must come from a stack slot.
    base_candidates=[]
    for i in range(max(0,load-5),load):
        info=decode_mem_word(words[i])
        if (info and info["kind"]=="LDR" and
            info["data_register"]==3 and info["base_register"]==11):
            base_candidates.append((i,info))
    if len(base_candidates)!=1:
        raise ValueError("Missing or ambiguous r3 <- [fp + imm] near r6 writer")
    pointer_load,base=base_candidates[0]
    slot_writers=[]
    for i,w in enumerate(words[:pointer_load]):
        info=decode_mem_word(w)
        if (info and info["kind"]=="STR" and
            info["base_register"]==11 and
            info["offset"]==base["offset"]):
            slot_writers.append({
                "address":f"0x{start+4*i:08x}",
                "source_register":f"r{info['data_register']}",
                "condition_arm":info["condition"],
                "word_index":i,
            })
    # AAPCS r1 normally receives the explicit sJpegOp& argument, but
    # symbol signatures and static prologue are not runtime proof.
    incoming_arg1_saved_candidacy=(
        len(slot_writers)==1 and
        slot_writers[0]["source_register"]=="r1" and
        slot_writers[0]["condition_arm"]==14
    )
    incoming_object_r0_saved_candidacy=(
        len(slot_writers)==1 and
        slot_writers[0]["source_register"]=="r0" and
        slot_writers[0]["condition_arm"]==14
    )
    return {
        "native_function":FUNCTION,
        "function_address":f"0x{start:08x}",
        "function_words":len(words),
        "arm_instruction_hash_sha256":
            hashlib.sha256(struct.pack("<"+"I"*len(words),*words)).hexdigest(),
        "base_pointer_load_site":f"0x{start+4*pointer_load:08x}",
        "base_pointer_register":"r3",
        "base_pointer_source_register":"fp",
        "base_pointer_stack_offset":base["offset"],
        "r6_field_load_site":f"0x{start+4*load:08x}",
        "field_load_expression":"LDR r6, [r3, #12]",
        "field_byte_offset":FIELD_BYTE_OFFSET,
        "blx_register_site":f"0x{start+4*call:08x}",
        "blx_register":"r6",
        "stack_slot_store_candidates":slot_writers,
        "incoming_sJpegOp_r1_saved_to_slot_candidate":
            incoming_arg1_saved_candidacy,
        "incoming_object_this_r0_saved_to_slot_candidate":
            incoming_object_r0_saved_candidacy,
        "cpp_aapcs_this_pointer_runtime_identity_proven":False,
        "incoming_arg_r1_is_live_sJpegOp_proven":False,
        "stack_alias_and_control_flow_checked":False,
        "indirect_call_runtime_target_proven":False,
        "hal_encode_target_proven":False,
        "live_capture_buffer_ownership_proven":False,
        "camera_install_or_flash_permitted":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing private regular libsif ELF")
    # Decode symbol from actual same-version ELF, no old offset guesses.
    sym=sif.symbol_index(sif.arm.offline_tool(
        ["readelf","-Ws",str(path)]))
    func=sif.select(sym,FUNCTION,"FUNC")
    address=func["address"];size=func["size"]
    if address&3 or size&3 or not 16<=size<=MAX_WORDS*4:
        raise ValueError("Unsupported ARM function code range")
    segments=elf.program_headers(path)
    offset=elf.file_range_for_vaddr(segments,address,size)
    with path.open("rb") as f:
        f.seek(offset)
        content=f.read(size)
    if len(content)!=size:
        raise ValueError("Truncated native function body")
    values=list(struct.unpack("<"+"I"*(size//4),content))
    out=select_provenance(values,address)
    out["mirror_source_is_vendor_authenticated"]=False
    return out


def compare_versions(p114:Path,p115:Path)->dict:
    return {
        "fw114":inspect(p114),
        "fw115":inspect(p115),
        "scope":"UNOFFICIAL_MIRROR_ARM32_STATIC_ONLY",
        "hardware_codec_pointer_proven":False,
        "camera_recovery_and_install_permitted":False,
    }
