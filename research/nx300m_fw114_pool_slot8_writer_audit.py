#!/usr/bin/env python3
"""Version-matched ARM32 CMemoryPool slot +8 writer and allocation-site audit.

Read real, private, unauthenticated third-party-mirror FW1.14 and FW1.15
libmm-photo.so. Strictly static: no firmware execution, patch, upload or
camera access. Scanning STR [any base,#8] is a *candidate*, NOT proof of
object identity or concurrent reuse.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_sif_callgraph as calls
import nx300m_fw114_jfif_r6_arg_provenance as arm
import nx300m_native_jpeg_abi_boundary_audit as jpeg

MAX_FILE=2*1024*1024
MAX_METHOD=16384
MAX_POOL_METHODS=80
MAX_STORES=128
POOL_PREFIX="CMemoryPool::"


def offset8_stores(words:tuple[int,...],start:int)->list[dict]:
    if not words or len(words)*4>MAX_METHOD or start&3:
        raise ValueError("Bounded native pool ARM words required")
    out=[]
    for i,w in enumerate(words):
        m=arm.decode_mem_word(w)
        if not m or m["kind"]!="STR" or m["offset"]!=8:
            continue
        if len(out)>=MAX_STORES:
            raise ValueError("Unbounded pool field +8 writes")
        out.append({
            "site":f"0x{start+i*4:08x}",
            "opcode":f"0x{w:08x}",
            "base_register":f"r{m['base_register']}",
            "value_register":f"r{m['data_register']}",
            "condition":m["condition"],
            "preceding_arm_words":[
                {"site":f"0x{start+j*4:08x}",
                 "opcode":f"0x{words[j]:08x}"}
                for j in range(max(0,i-12),i)
            ],
            "is_confirmed_pool_this_plus8_write":False,
            "is_confirmed_live_pool_reuse":False,
        })
    return out


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (
        1024<=path.stat().st_size<=MAX_FILE
    ):
        raise ValueError("Require private bounded libmm-photo ARM ELF")
    blob=path.read_bytes()
    segs=elf.program_headers(path)
    syms=sif.symbol_index(sif.arm.offline_tool(["readelf","-Ws",str(path)]))
    defined=calls.defined_symbols(path)
    reloc=jpeg.relocations(sif.arm.offline_tool(["readelf","-Wr",str(path)]))
    pool=[
        (name,info) for name,info in sorted(syms.items())
        if name.startswith(POOL_PREFIX) and info["kind"]=="FUNC"
        and info["size"]>0
    ]
    if not pool or len(pool)>MAX_POOL_METHODS:
        raise ValueError("Invalid pool method count from real libmm-photo")
    out=[]
    for name,info in pool:
        addr,size=info["address"],info["size"]
        if addr&3 or size&3 or not 8<=size<=MAX_METHOD:
            raise ValueError("Unexpected private pool method ARM size")
        pos=elf.file_range_for_vaddr(segs,addr,size)
        raw=blob[pos:pos+size]
        if len(raw)!=size:
            raise ValueError("Truncated CMemoryPool method")
        words=struct.unpack("<"+"I"*(size//4),raw)
        graph=calls.collect_edges(blob,segs,addr,size,defined,reloc)
        if graph["identified_calls_truncated"]:
            raise ValueError("Truncated pool native direct caller graph")
        imported=sorted({
            e["target_symbol"] for e in graph["identified_callsite_evidence"]
            if e["target_kind"]=="import"})
        demangled=sif.arm.offline_tool(
            ["c++filt"],"\n".join(imported)+"\n"
        ).splitlines() if imported else []
        if len(demangled)!=len(imported):
            raise ValueError("C++ pool call demangle count mismatch")
        names=dict(zip(imported,demangled))
        bls=[{
            "callsite":e["callsite"],
            "target_demangled":names.get(e["target_symbol"],
                                           e["target_symbol"]),
            "target_kind":e["target_kind"],
        } for e in graph["identified_callsite_evidence"]]
        out.append({
            "method":name,
            "address":f"0x{addr:08x}",
            "size":size,
            "body_sha256":hashlib.sha256(raw).hexdigest(),
            "field_plus8_store_candidates":offset8_stores(words,addr),
            "named_native_arm_direct_calls":bls,
            "actual_pool_object_identity_proven":False,
            "runtime_pool_write_or_reuse_observed":False,
        })
    return {
        "scope":"UNOFFICIAL_MIRROR_ACTUAL_ELF32_POOL_METHODS_ONLY",
        "libmm_photo_sha256":hashlib.sha256(blob).hexdigest(),
        "native_pool_method_count":len(out),
        "CMemoryPool_native_methods":out,
        "all_pool_offset8_writers_located":False,
        "actual_pool_slot8_writer_and_allocator_proven":False,
        "physical_camera_dma_reuse_interval_proven":False,
        "safe_film_processing_hook_proven":False,
        "firmware_install_or_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a=inspect(fw114);b=inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "photo_ELF_sha256_same":a["libmm_photo_sha256"]==b["libmm_photo_sha256"],
        "method_count_equal":a["native_pool_method_count"]==b[
            "native_pool_method_count"],
        "live_camera_buffer_ownership_verified":False,
        "camera_firmware_flash_permitted":False,
    }
