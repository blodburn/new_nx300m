#!/usr/bin/env python3
"""Read-only FW1.14/1.15 native CYcc type/scan getter ARM field offsets.

Analyze only the bounded ARM32 instructions already extracted from the
private, third-party mirrored libmm-type.so. No native code execution,
device access, hooking, firmware writes, or flash permission.
"""
from __future__ import annotations

import hashlib
import struct

import nx300m_fw114_jfif_r6_arg_provenance as arm

GETTERS=("CYcc::GetType()","CYcc::GetScanMode()")
PROVIDER="libmm-type.so"
TYPE_SITE=0x31d8
TYPE_SIZE=40
TYPE_OFFSET=0x20
SCAN_SITE=0x31b0
SCAN_SIZE=40
SCAN_OFFSET=0x1c
# Exact source-backed GetType A32 function from FW1.14/1.15.
TYPE_WORDS=(
    0xe52db004,0xe28db000,0xe24dd00c,0xe50b0008,0xe51b3008,
    0xe5933020,0xe1a00003,0xe28bd000,0xe8bd0800,0xe12fff1e,
)
SCAN_WORDS=(
    0xe52db004,0xe28db000,0xe24dd00c,0xe50b0008,0xe51b3008,
    0xe593301c,0xe1a00003,0xe28bd000,0xe8bd0800,0xe12fff1e,
)
FRAME=(0xe52db004,0xe28db000,0xe24dd00c,0xe50b0008,0xe51b3008)
EPILOGUE=(0xe1a00003,0xe28bd000,0xe8bd0800,0xe12fff1e)


def getter_method(report:dict, name:str)->dict:
    """Select a single source ELF method, never guess a missing symbol."""
    if not isinstance(report,dict):
        raise ValueError("Malformed private native provider report")
    providers=report.get("provider_elfs",{})
    p=providers.get(PROVIDER)
    if not p or p.get("present") is not True:
        raise ValueError("Missing libmm-type.so native CYcc provider")
    found=[x for x in p.get("target_symbols",[])
           if x.get("name")==name]
    if len(found)!=1 or "offline_native_ARM_body" not in found[0]:
        raise ValueError("Missing or ambiguous native CYcc getter ARM body")
    return found[0]


def inspect_method(method:dict, name:str)->dict:
    """Decode bounded A32 function; classify single direct this+field load."""
    if name not in GETTERS:
        raise ValueError("Unknown CYcc getter")
    body=method.get("offline_native_ARM_body",{})
    rows=body.get("arm_instruction_words",[])
    address_text=method.get("address")
    size=method.get("function_bytes")
    try:
        address=int(address_text,16)
    except (ValueError,TypeError) as exc:
        raise ValueError("Malformed native getter address") from exc
    if (type(size)is not int or size<16 or size>256 or size&3 or
        address&3 or len(rows)!=size//4 or
        body.get("arm_word_count")!=len(rows)):
        raise ValueError("Unexpected bounded native CYcc getter size")
    words=[]
    for i,item in enumerate(rows):
        try:
            pc=int(item["pc"],16)
            op=int(item["opcode"],16)
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("Invalid CYcc getter instruction record") from exc
        if pc!=address+4*i or op<0 or op>0xffffffff:
            raise ValueError("Non-contiguous native CYcc getter instruction")
        words.append(op)
    if body.get("direct_ARM_BL_edges") or body.get("register_indirect_branches"):
        raise ValueError("CYcc getter has unmodeled call or register branch")
    pinned=(TYPE_SITE,TYPE_SIZE,TYPE_WORDS) if name==GETTERS[0] else (
        SCAN_SITE,SCAN_SIZE,SCAN_WORDS)
    if (address,size,tuple(words))!=pinned:
        raise ValueError(f"Actual FW1.14/1.15 {name} field source changed")

    # Generic, fail-closed O0 GCC-like trivial getter. A scan-mode getter
    # can be reported as unsupported without pretending to know its field.
    prefix=tuple(words[:5])
    suffix=tuple(words[-4:])
    simple=(len(words)==10 and prefix==FRAME and suffix==EPILOGUE)
    load=arm.decode_mem_word(words[5]) if simple else None
    direct=(simple and load is not None and
        load["kind"]=="LDR" and load["condition"]==14 and
        load["base_register"]==3 and load["data_register"]==3 and
        0<=load["offset"]<=256)
    expected_offset=TYPE_OFFSET if name==GETTERS[0] else SCAN_OFFSET
    if not direct or load["offset"]!=expected_offset:
        raise ValueError(f"{name} changed CYcc field offset")
    return {
        "native_getter":name,
        "provider_elf":PROVIDER,
        "function_site":f"0x{address:08x}",
        "function_byte_count":size,
        "arm_code_sha256":hashlib.sha256(
            struct.pack("<"+"I"*len(words),*words)).hexdigest(),
        "arm_instruction_words":[
            {"site":f"0x{address+4*i:08x}","opcode":f"0x{w:08x}"}
            for i,w in enumerate(words)
        ],
        "incoming_this_register":"r0",
        "this_saved_at_fp_offset":-8 if simple else None,
        "this_reload_before_field_load":bool(simple),
        "trivial_direct_field_return_pattern_verified":bool(direct),
        "field_read_opcode":f"0x{words[5]:08x}" if direct else None,
        "field_read_site":f"0x{address+20:08x}" if direct else None,
        "field_offset_from_this_bytes":load["offset"] if direct else None,
        "return_field_via_r3_to_r0":bool(direct),
        "runtime_cycc_object_identity_proven":False,
        "actual_enum_definitions_or_chroma_order_proven":False,
        "camera_buffer_ownership_or_dma_verified":False,
        "firmware_flash_permitted":False,
    }


def compare_versions(fw114:dict,fw115:dict)->dict:
    result={}
    for ver,provider in (("fw114",fw114),("fw115",fw115)):
        result[ver]={
            name:inspect_method(getter_method(provider,name),name)
            for name in GETTERS
        }
    return {
        **result,
        "same_GetType_code":
            result["fw114"][GETTERS[0]]["arm_code_sha256"]==
            result["fw115"][GETTERS[0]]["arm_code_sha256"],
        "same_GetScanMode_code":
            result["fw114"][GETTERS[1]]["arm_code_sha256"]==
            result["fw115"][GETTERS[1]]["arm_code_sha256"],
        "GetType_object_field_plus32_verified":all(
            result[v][GETTERS[0]]["field_offset_from_this_bytes"]==32
            for v in ("fw114","fw115")),
        "GetScanMode_object_field_plus28_verified":all(
            result[v][GETTERS[1]]["field_offset_from_this_bytes"]==28
            for v in ("fw114","fw115")),
        "live_getter_results_or_enum_semantics_verified":False,
        "physical_camera_buffer_format_or_stride_verified":False,
        "native_DMA_cache_coherency_verified":False,
        "firmware_flash_permitted":False,
    }
