#!/usr/bin/env python3
"""Read-only actual FW1.14/1.15 SIF HAL callback producer investigation.

Trace native DscJPEG::DscJPEG(... tDscHal*) and Instance(.. tDscHal*)
to DscJfif::HalRegister, recording exact ARM32 BL/PLT and table
pointer passing. Scan direct writes to the +8 field only within
relevant named native functions, and distinguish presence of a
GLOB_DAT relocation from proof of callback assignment.

All inputs are ephemeral, previously header-checked third-party
unofficial firmware ELFs. Never execute code or patch firmware.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_jfif_r6_arg_provenance as arg
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_sif_callgraph as graph
import nx300m_native_jpeg_abi_boundary_audit as jpeg

MAX_SOURCE=2*1024*1024
MAX_METHOD=4096
METHODS=(
    "DscJfif::HalRegister(",
    "DscJPEG::DscJPEG(unsigned long",
    "DscJPEG::Instance(",
    "DscJfif::DscJfif()",
)
HAL_SYMBOL="DscJfifHal::Encode("
HAL_REGISTER_SYMBOL="DscJfif::HalRegister("
MAX_RELEVANT_FUNCS=128


def candidate_mem_store_sites(
    words:tuple[int,...],address:int,offset:int=8
)->list[dict]:
    """Direct STR [reg,#8] statements; never infer object base."""
    found=[]
    for i,w in enumerate(words):
        item=arg.decode_mem_word(w)
        if not item or item["kind"]!="STR" or item["offset"]!=offset:
            continue
        if len(found)>=40:
            raise ValueError("Unbounded HAL field store candidate count")
        found.append({
            "site":"0x%08x"%(address+4*i),
            "opcode":"0x%08x"%w,
            "base_register":"r%d"%item["base_register"],
            "value_register":"r%d"%item["data_register"],
            "preceding_words":[
                {"site":"0x%08x"%(address+4*j),
                 "opcode":"0x%08x"%words[j]}
                for j in range(max(0,i-7),i)
            ],
            "proven_tDscHal_plus8_write":False,
            "proven_hal_encoder_callback_value":False,
        })
    return found


def native_method(path:Path, segments:list[tuple[int,int,int]],
                  symbols:dict[str,dict],prefix:str,
                  defined:dict[int,str],relocs:dict[int,str]) -> dict:
    fn=sif.select(symbols,prefix,"FUNC")
    addr=fn["address"];size=fn["size"]
    if addr&3 or size&3 or not 8<=size<=MAX_METHOD:
        raise ValueError("Unexpected FW114 SIF method body: "+prefix)
    off=elf.file_range_for_vaddr(segments,addr,size)
    with path.open("rb") as stream:
        stream.seek(off);raw=stream.read(size)
    if len(raw)!=size:
        raise ValueError("SIF ARM body truncated")
    words=struct.unpack("<"+"I"*(size//4),raw)
    edges=graph.collect_edges(raw,[(addr,size,0)],addr,size,
                              defined,relocs)
    # graph.collect_edges expects the exact code address and its local PT_LOAD
    return {
        "native_symbol":fn["name"],
        "function_address":"0x%08x"%addr,
        "size":size,
        "sha256":hashlib.sha256(raw).hexdigest(),
        "direct_bl_candidates":edges["arm_direct_bl_candidate_count"],
        "identified_direct_calls":edges["identified_callsite_evidence"],
        "all_identified_calls_included":not edges["identified_calls_truncated"],
        "direct_plus8_store_candidates":candidate_mem_store_sites(words,addr),
        "complete_native_control_flow_verified":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or (
        not 1024<=path.stat().st_size<=MAX_SOURCE
    ):
        raise ValueError("Require private bounded native FW libsif.so")
    data=path.read_bytes()
    segments=elf.program_headers(path)
    symbols=sif.symbol_index(sif.arm.offline_tool(
        ["readelf","-Ws",str(path)]))
    defined=graph.defined_symbols(path)
    reltext=sif.arm.offline_tool(["readelf","-Wr",str(path)])
    relocs=jpeg.relocations(reltext)
    reloc_targets=sif.relocation_symbol_targets(reltext)
    hal_symbol=sif.select(symbols,HAL_SYMBOL,"FUNC")
    hal_got=[
        {"got_address":"0x%08x"%location,**item}
        for location,item in reloc_targets.items()
        if item["symbol_value"]=="0x%08x"%hal_symbol["address"] and
           item["relocation_type"] in ("R_ARM_GLOB_DAT","R_ARM_JUMP_SLOT")
    ]
    if not hal_got or len(hal_got)>4:
        raise ValueError("Missing or ambiguous HAL Encode relocated symbol witness")
    focus={}
    for prefix in METHODS:
        focus[prefix]=native_method(path,segments,symbols,prefix,defined,relocs)
    ctor=focus["DscJPEG::DscJPEG(unsigned long"]
    instance=focus["DscJPEG::Instance("]
    def evidence(data:dict)->list[dict]:
        return [x for x in data["identified_direct_calls"] if
                "HalRegister" in x["target_symbol"] or
                "DscJfif" in x["target_symbol"] or
                "DscJPEG" in x["target_symbol"]]
    return {
        "source":"UNOFFICIAL_MIRROR_STATIC_ARM32_SIF",
        "libsif_sha256":hashlib.sha256(data).hexdigest(),
        "method_evidence":focus,
        "jpeg_constructor_relevant_direct_calls":evidence(ctor),
        "jpeg_instance_relevant_direct_calls":evidence(instance),
        "hal_encoder_symbol":"DscJfifHal::Encode",
        "hal_encoder_native_address":"0x%08x"%hal_symbol["address"],
        "hal_encoder_static_got_relocations":hal_got,
        "jpeghal_table_plus8_actual_initialization_proven":False,
        "same_tDscHal_table_instance_proven":False,
        "callback_runtime_target_proven":False,
        "real_dma_ycc_buffer_ownership_proven":False,
        "firmware_install_or_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a=inspect(fw114)
    b=inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "third_party_firmware_authenticated_by_samsung":False,
        "hal_callback_exact_runtime_address_proven":False,
        "camera_flash_permitted":False,
    }
