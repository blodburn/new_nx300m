#!/usr/bin/env python3
"""Read-only ARM32 still-JPEG CYcc lifetime branch and pool/resize trace.

Read actual, locally extracted FW1.14/FW1.15 libmm-photo.so. Distinguish
a pool pointer used by temporary CYcc from independently owned, safe copy.
Original files are third-party mirrors, NOT Samsung-authenticated.
No live camera, DMA access, hook, firmware mutation, or flashing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as si
import nx300m_fw114_photo_ycc_copy_boundary as photo
import nx300m_fw114_jfif_r6_arg_provenance as mem

FUNC="CMmDeviceDriver::EncodeYcc("
TRACK=(0x34b34,0x34b60,0x34b64,0x34b74,0x34b8c,
       0x34bac,0x34bdc,0x34ca8,0x34d78,0x34d94)
MAX_BYTES=2*1024*1024
# Bound instruction excerpts only; the output is machine-code text, no images.
WINDOWS=((0x34b18,0x34c14),(0x34d70,0x34da0))


def arm_direct_b(opcode:int,site:int)->dict|None:
    """ARM B immediate, not BL, BLX, BX, or Thumb."""
    cond=(opcode>>28)&15
    if cond==15 or (opcode>>25)&7!=5 or (opcode>>24)&1:
        return None
    d=(opcode&0xffffff)<<2
    if d&0x2000000:
        d-=0x4000000
    return {
        "pc":"0x%08x"%site,
        "opcode":"0x%08x"%opcode,
        "condition":cond,
        "target":"0x%08x"%((site+8+d)&0xffffffff),
        "unconditional":cond==14,
    }


def branch_boundaries(words:tuple[int,...],base:int)->list[dict]:
    if base&3 or len(words)>4096 or not words:
        raise ValueError("Unsupported ARM function block")
    lo,hi=base,base+len(words)*4
    branches=[]
    for i,op in enumerate(words):
        pc=base+4*i
        b=arm_direct_b(op,pc)
        if b:
            b["target_inside_function"]=lo<=int(b["target"],16)<hi
            branches.append(b)
        if len(branches)>256:
            raise ValueError("Too many ARM branches in camera function")
    return branches


def excerpt(words:tuple[int,...],base:int,lo:int,hi:int)->list[dict]:
    if base&3 or lo<base or hi>base+4*len(words) or lo&3 or hi&3:
        raise ValueError("Unbounded FW native code window")
    out=[]
    for pc in range(lo,hi,4):
        op=words[(pc-base)//4]
        b=arm_direct_b(op,pc)
        m=mem.decode_mem_word(op)
        out.append({
            "pc":"0x%08x"%pc,
            "arm_word":"0x%08x"%op,
            "B_target":b["target"] if b else None,
            "B_condition":b["condition"] if b else None,
            "LDR_STR_immediate":{
                "kind":m["kind"],
                "base":"r%d"%m["base_register"],
                "data":"r%d"%m["data_register"],
                "offset":m["offset"],
            } if m else None,
        })
    return out


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (
        1024<=path.stat().st_size<=MAX_BYTES
    ):
        raise ValueError("Private FW ARM ELF required")
    data=path.read_bytes()
    loads=elf.program_headers(path)
    index=si.symbol_index(si.arm.offline_tool(["readelf","-Ws",str(path)]))
    function=si.select(index,FUNC,"FUNC")
    addr,size=function["address"],function["size"]
    if addr!=0x34b18 or size!=644:
        raise ValueError("Unexpected FW JPEG owner function address/bytes")
    words=photo.native_words(data,loads,addr,size)
    branches=branch_boundaries(words,addr)
    chosen=[b for b in branches if b["target_inside_function"]]
    known_targets={
        "CMemoryPool::GetAddr":0x34b74,
        "CYcc temporary constructor":0x34b8c,
        "ResizeImage":0x34bac,
        "CYcc destructor before JPEG":0x34bdc,
        "DscImage::EncodeYCC":0x34d78,
        "CYcc destructor after JPEG":0x34d94,
    }
    for pc in known_targets.values():
        if not addr<=pc<addr+size:
            raise ValueError("Expected camera call outside native encoder")
    excerpts=[
        {"first":"0x%08x"%start,"end_exclusive":"0x%08x"%end,
         "arm_words":excerpt(words,addr,start,end)}
        for start,end in WINDOWS
    ]
    return {
        "scope":"UNOFFICIAL_MIRROR_FW114_PHOTO_OFFLINE",
        "photo_sha256":hashlib.sha256(data).hexdigest(),
        "function_address":"0x%08x"%addr,
        "function_bytes":size,
        "function_body_sha256":hashlib.sha256(
            struct.pack("<"+"I"*len(words),*words)).hexdigest(),
        "conditional_arm_branches_in_function":sum(
            x["condition"]!=14 for x in chosen),
        "all_arm_immediate_branches":branches,
        "internal_arm_branch_edges":chosen,
        "actual_native_call_sites":{
            name:"0x%08x"%pc for name,pc in known_targets.items()
        },
        "code_windows":excerpts,
        "temporary_cycc_may_use_memory_pool":True,
        "native_pool_buffer_ownership_or_refcount_verified":False,
        "native_resize_output_lifetime_verified":False,
        "destructor_timing_proves_DMA_safety":False,
        "raw_input_and_resize_output_identity_proven":False,
        "camera_capture_runtime_proven":False,
        "camera_firmware_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a=inspect(fw114);b=inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "same_photo_ELF_SHA256":a["photo_sha256"]==b["photo_sha256"],
        "same_function_SHA256":a["function_body_sha256"]==b["function_body_sha256"],
        "camera_DMA_buffer_lifetime_verified":False,
        "camera_firmware_patch_allowed":False,
    }
