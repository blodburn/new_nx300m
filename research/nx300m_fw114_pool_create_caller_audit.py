#!/usr/bin/env python3
"""Find actual FW1.14/1.15 CMemoryPool CreateInstance/Destroy callers.

Read-only ARM32 direct BL→ELF PLT/GOT/relocation symbol resolution. Caller
register windows are static candidates, not proof of live buffer addresses,
allocations, frees, synchronization, DMA or hardware capture timing.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_callgraph as calls
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_native_jpeg_abi_boundary_audit as jpeg

MAX_ELF=2*1024*1024
MAX_METHODS=4000
MAX_FUNC=32768
MAX_MATCHES=64
FOCUS=("CMemoryPool::CreateInstance(","CMemoryPool::Destory(",
       "CMemoryPool::GetInstance(","CMemoryPool::GetAddr(",
       "CMemoryPool::CMemoryPool(")


def is_pool_lifecycle_call(target:str)->bool:
    """Only creation and destruction; exclude hot-path GetAddr/GetInstance."""
    return (
        "CMemoryPool::CreateInstance(" in target or
        "_ZN11CMemoryPool14CreateInstance" in target or
        "CMemoryPool::Destory(" in target or
        "_ZN11CMemoryPool7Destory" in target
    )


def caller_context(words:tuple[int,...],start:int,site:int)->dict:
    if start&3 or site<start or (site-start)&3 or (site-start)//4>=len(words):
        raise ValueError("Bad ARM caller context range")
    i=(site-start)//4
    return {
        "site":f"0x{site:08x}",
        "before":[
            {"pc":f"0x{start+j*4:08x}","opcode":f"0x{words[j]:08x}"}
            for j in range(max(0,i-14),i)
        ],
        "r0_writer_candidates":sif.register_writer_candidates(
            list(words),i,0
        )[:8],
        "input_base_virtual_address_proven":False,
        "memory_pool_alloc_size_proven":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (
        1024<=path.stat().st_size<=MAX_ELF
    ):
        raise ValueError("Require private FW libmm-photo.so ELF32")
    data=path.read_bytes()
    segs=elf.program_headers(path)
    syms=sif.symbol_index(sif.arm.offline_tool(
        ["readelf","-Ws",str(path)]))
    defined=calls.defined_symbols(path)
    relocs=jpeg.relocations(sif.arm.offline_tool(
        ["readelf","-Wr",str(path)]))
    functions=[
        (name,info) for name,info in sorted(syms.items())
        if info["kind"]=="FUNC" and info["size"]>=4 and
        info["size"]<=MAX_FUNC and not info["address"]&3
    ]
    if not functions or len(functions)>MAX_METHODS:
        raise ValueError("Unexpected bounded FW native method inventory")
    matches=[]
    lifecycle={}
    examined=0
    for name,fn in functions:
        start,size=fn["address"],fn["size"]
        try:
            off=elf.file_range_for_vaddr(segs,start,size)
        except ValueError:
            continue
        edges=calls.collect_edges(data,segs,start,size,defined,relocs)
        examined+=1
        if name in ("AllocListener","FreeListener"):
            if edges["identified_calls_truncated"]:
                raise ValueError("Lifecycle ARM callgraph incomplete")
            lifecycle[name]={
                "start":f"0x{start:08x}",
                "size":size,
                "direct_bl_candidate_count":edges["arm_direct_bl_candidate_count"],
                "named_arms_bl":edges["identified_callsite_evidence"],
                "live_capture_frequency_proven":False,
                "arena_allocation_size_proven":False,
                "arena_runtime_base_address_proven":False,
            }
        for e in edges["identified_callsite_evidence"]:
            target=e["target_symbol"]
            if not is_pool_lifecycle_call(target):
                continue
            site=int(e["callsite"],16)
            words=struct.unpack_from("<"+"I"*(size//4),data,off)
            matches.append({
                "caller_native_symbol":name,
                "caller_address":f"0x{start:08x}",
                "callee_symbol":target,
                "callee_kind":e["target_kind"],
                **caller_context(words,start,site),
            })
            if len(matches)>MAX_MATCHES:
                raise ValueError("Too many camera memory pool callsites")
    return {
        "scope":"UNOFFICIAL_ACTUAL_FW114_LIBMM_PHOTO_STATIC_CALLERS",
        "sha256":hashlib.sha256(data).hexdigest(),
        "examined_method_count":examined,
        "pool_callsite_candidates":matches,
        "allocation_release_listener_arms":lifecycle,
        "caller_search_is_complete_for_indirect_calls":False,
        "pool_base_address_at_runtime_proven":False,
        "pool_write_or_reuse_after_creation_proven":False,
        "on_camera_capture_timing_proven":False,
        "camera_firmware_install_or_flash_permitted":False,
    }


def compare_versions(p114:Path,p115:Path)->dict:
    a=inspect(p114)
    b=inspect(p115)
    return {
        "fw114":a,"fw115":b,
        "photo_ELF_byte_equal":a["sha256"]==b["sha256"],
        "real_camera_pool_ownership_proven":False,
        "firmware_flash_permitted":False,
    }
