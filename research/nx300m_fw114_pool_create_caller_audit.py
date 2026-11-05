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


def verify_listener_memory_arena_arm(
    image:bytes,segments:list[tuple[int,int,int]],
    index:dict[str,dict],lifecycles:dict
)->dict:
    """Exact native static malloc/munmap-style pointer forwarding.

    Verifies imported native calls and caller ARM stack dataflow. This does
    not prove the actual mapped allocation capacity or lock/pin lifetime.
    """
    expected_imports={
        "AllocListener":{
            0x34e44:"sysmmap_cached_alloc",
            0x34e6c:"sysmmap_alloc",
            0x34e7c:"_ZN11CMemoryPool14CreateInstanceEj",
        },
        "FreeListener":{
            0x35028:"_ZN11CMemoryPool11GetInstanceEv",
            0x35038:"_ZN11CMemoryPool7GetAddrE8eMemMode",
            0x35058:"sysmmap_free",
            0x35068:"_ZN11CMemoryPool7DestoryEv",
        },
    }
    expected_opcodes={
        "AllocListener":{
            0x34e48:0xe1a03000, # mov r3,r0, mmap return
            0x34e4c:0xe50b3010, # cached result -> fp-16
            0x34e50:0xea000008, # skip to common pool instance path
            0x34e54:0xe51b301c,
            0x34e58:0xe5932004, # region size descriptor
            0x34e5c:0xe51b301c,
            0x34e60:0xe593300c, # mapped mode descriptor
            0x34e64:0xe1a00002, # r0=size
            0x34e68:0xe1a01003, # r1=mode
            0x34e70:0xe1a03000, # mmap return into r3
            0x34e74:0xe50b3010, # fp-16 stores returned ptr
            0x34e78:0xe51b0010, # CreateInstance r0=stored ptr
        },
        "FreeListener":{
            0x35030:0xe1a00003, # pool this
            0x35034:0xe3a01000, # GetAddr(mode 0) -> pool base
            0x3503c:0xe1a03000, # returned pool base
            0x35040:0xe50b3010, # stored fp-16
            0x35044:0xe51b3018, # listener params
            0x35048:0xe5932004, # mapped size
            0x3504c:0xe51b3010, # map base
            0x35050:0xe1a00002, # free r0=size
            0x35054:0xe1a01003, # free r1=base pointer
            0x35060:0xe1a03000,
            0x35064:0xe1a00003, # pool object for destroy
        },
    }
    report={}
    for name in ("AllocListener","FreeListener"):
        fn=sif.select(index,name,"FUNC")
        addr,size=fn["address"],fn["size"]
        present=lifecycles.get(name)
        if present is None or int(present["start"],16)!=addr:
            raise ValueError("Missing same-version native pool listener")
        off=elf.file_range_for_vaddr(segments,addr,size)
        words=struct.unpack_from("<"+"I"*(size//4),image,off)
        for pc,expected in expected_opcodes[name].items():
            if not addr<=pc<addr+size or words[(pc-addr)//4]!=expected:
                raise ValueError(
                    f"Wrong native listener {name} ptr forwarding at {pc:#x}")
        calls_by_site={
            int(x["callsite"],16):x["target_symbol"]
            for x in present["named_arms_bl"]
        }
        for pc,import_name in expected_imports[name].items():
            if calls_by_site.get(pc)!=import_name:
                raise ValueError(
                    f"Wrong native listener {name} import at {pc:#x}")
        report[name]={
            "native_symbol":name,
            "function_address":f"0x{addr:08x}",
            "verified_plt_imports":{
                f"0x{pc:08x}":symbol for pc,symbol in
                expected_imports[name].items()
            },
            "verified_ARM_argument_words":{
                f"0x{pc:08x}":f"0x{word:08x}"
                for pc,word in expected_opcodes[name].items()
            },
            "uses_same_process_pool_base_pointer_static_layout":True,
            "mmap_region_size_actual_value_verified":False,
            "physical_camera_listener_event_frequency_verified":False,
        }
    return {
        "source":"UNOFFICIAL_FW114_ELF_NATIVE_STATIC_ONLY",
        "listeners":report,
        "sysmmap_cached_alloc_and_alloc_results_stored_for_CreateInstance":True,
        "FreeListener_gets_pool_mode0_base_then_calls_sysmmap_free":True,
        "per_shutter_reallocation_proven":False,
        "concurrent_mapping_access_and_DMA_coherency_proven":False,
        "camera_firmware_flash_permitted":False,
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
    if set(lifecycle)!=set(("AllocListener","FreeListener")):
        raise ValueError("Incomplete native pool listener inventory")
    pointer_flow=verify_listener_memory_arena_arm(
        data,segs,syms,lifecycle
    )
    return {
        "scope":"UNOFFICIAL_ACTUAL_FW114_LIBMM_PHOTO_STATIC_CALLERS",
        "native_pool_mmap_pointer_flow":pointer_flow,
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
