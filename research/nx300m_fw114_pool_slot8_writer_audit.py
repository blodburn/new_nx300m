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


def rotate_right32(value:int,bits:int)->int:
    bits=bits%32
    return ((value>>bits)|(value<<(32-bits)))&0xffffffff if bits else value


def decode_arm_add_immediate(word:int)->dict|None:
    """ARM conditional ADD immediate with no carry; literals not pointers."""
    if (word>>28)!=14 or ((word>>25)&7)!=1 or (
        (word>>21)&15
    )!=4 or ((word>>20)&1):
        return None
    return {
        "dst":(word>>12)&15,
        "source":(word>>16)&15,
        "immediate":rotate_right32(word&255,2*((word>>8)&15))
    }


def prove_ctor_immutable_slot_base(words:tuple[int,...],start:int)->dict:
    """Exact 13-instruction native proof of three computed pool pointers."""
    if start!=0x000351b4 or len(words)!=23:
        raise ValueError("Wrong CMemoryPool constructor version/length")
    opcodes=(
        (0x351c8,0xe51b3008), # this from fp-8
        (0x351cc,0xe51b200c), # incoming base from fp-12
        (0x351d0,0xe5832000), # this+0 = base
        (0x351d4,0xe51b3008),
        (0x351d8,0xe5933000), # base
        (0x351e0,0xe51b3008),
        (0x351e4,0xe5832004), # this+4 = base+...
        (0x351e8,0xe51b3008),
        (0x351ec,0xe5933004), # this+4
        (0x351f4,0xe51b3008),
        (0x351f8,0xe5832008), # this+8 = previous+...
    )
    for pc,w in opcodes:
        if words[(pc-start)//4]!=w:
            raise ValueError(f"Native pool constructor ARM changed at {pc:#x}")
    add1=decode_arm_add_immediate(words[(0x351dc-start)//4])
    add2=decode_arm_add_immediate(words[(0x351f0-start)//4])
    if (not add1 or not add2 or
        (add1["source"],add1["dst"])!=(3,2) or
        (add2["source"],add2["dst"])!=(3,2) or
        add1["immediate"]!=30*1024*1024 or
        add2["immediate"]!=10*1024*1024):
        raise ValueError("Native pool 30MiB+10MiB offsets changed")
    return {
        "constructor":"CMemoryPool::CMemoryPool(unsigned int)",
        "native_address":f"0x{start:08x}",
        "source_base_argument":"r1 saved at [fp-12]",
        "field_offset_to_base":{
            "0":0,
            "4":add1["immediate"],
            "8":add1["immediate"]+add2["immediate"],
        },
        "arm_add30_site":"0x000351dc",
        "arm_add10_site":"0x000351f0",
        "field8_write_site":"0x000351f8",
        "base_is_real_camera_buffer_virtual_address_proven":False,
        "physical_pool_size_or_allocation_bounds_proven":False,
        "concurrent_or_later_writers_excluded":False,
        "camera_flash_permitted":False,
    }


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
    layout=None
    for name,info in pool:
        addr,size=info["address"],info["size"]
        if addr&3 or size&3 or not 8<=size<=MAX_METHOD:
            raise ValueError("Unexpected private pool method ARM size")
        pos=elf.file_range_for_vaddr(segs,addr,size)
        raw=blob[pos:pos+size]
        if len(raw)!=size:
            raise ValueError("Truncated CMemoryPool method")
        words=struct.unpack("<"+"I"*(size//4),raw)
        if name.startswith("CMemoryPool::CMemoryPool("):
            if layout is not None:
                raise ValueError("Unexpected multiple pool constructors")
            layout=prove_ctor_immutable_slot_base(words,addr)
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
    if layout is None:
        raise ValueError("Original pool constructor missing")
    return {
        "scope":"UNOFFICIAL_MIRROR_ACTUAL_ELF32_POOL_METHODS_ONLY",
        "constructor_three_pointer_offset_layout":layout,
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
