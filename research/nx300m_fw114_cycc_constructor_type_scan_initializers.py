#!/usr/bin/env python3
"""Static two-field constructor initialization witnesses in private CYcc ARM.

Only checks fixed A32 instructions in a single mirrored FW1.14/1.15
CYcc(sImgSize,unsigned long) overload. Never claims that all constructors
or live camera buffers have these field values. No firmware execution.
"""
from __future__ import annotations

import hashlib
import struct

PROVIDER="libmm-type.so"
NAME="CYcc::CYcc(sImgSize, unsigned long)"
START=0x20b8
SIZE=544
ENTRY_SAVE=(0x20cc,0xe50b0010)  # STR r0,[fp,-16]
INITIALIZERS=(
    ("scan_mode",28,1,((0x2290,0xe51b3010),
                        (0x2294,0xe3a02001),
                        (0x2298,0xe583201c))),
    ("type",32,0,((0x229c,0xe51b3010),
                 (0x22a0,0xe3a02000),
                 (0x22a4,0xe5832020))),
)


def constructor_proof(provider:dict)->dict:
    if not isinstance(provider,dict):
        raise ValueError("Malformed native CYcc provider record")
    lib=provider.get("provider_elfs",{}).get(PROVIDER)
    if not lib or lib.get("present") is not True:
        raise ValueError("Missing native CYcc constructor provider")
    methods=[m for m in lib.get("target_symbols",[]) if m.get("name")==NAME]
    if len(methods)!=1 or "offline_native_ARM_body" not in methods[0]:
        raise ValueError("Missing or ambiguous CYcc constructor overload")
    method=methods[0]
    if (method.get("address")!=f"0x{START:08x}" or
        method.get("function_bytes")!=SIZE):
        raise ValueError("Changed FW native CYcc constructor address or size")
    body=method["offline_native_ARM_body"]
    rows=body.get("arm_instruction_words",[])
    if len(rows)!=SIZE//4 or body.get("arm_word_count")!=SIZE//4:
        raise ValueError("Unbounded native CYcc constructor instructions")
    words={}
    for i,row in enumerate(rows):
        try:
            pc=int(row["pc"],16)
            op=int(row["opcode"],16)
        except (KeyError,ValueError,TypeError) as exc:
            raise ValueError("Malformed CYcc constructor ARM evidence") from exc
        if pc!=START+4*i or not 0<=op<=0xffffffff:
            raise ValueError("Changed CYcc constructor ARM instruction stream")
        words[pc]=op
    if words[ENTRY_SAVE[0]]!=ENTRY_SAVE[1]:
        raise ValueError("CYcc constructor no longer saves this r0 at fp-16")
    witnesses=[]
    for label,offset,value,triple in INITIALIZERS:
        for address,expected in triple:
            if words[address]!=expected:
                raise ValueError(
                    f"Changed CYcc constructor {label} field write at {address:#x}"
                )
        witnesses.append({
            "field":label,
            "native_object_offset":offset,
            "adjacent_mov_immediate":value,
            "incoming_this_saved_at_fp_offset":-16,
            "local_ldr_this_from_frame":f"0x{triple[0][0]:08x}",
            "mov_immediate_site":f"0x{triple[1][0]:08x}",
            "store_to_this_field_site":f"0x{triple[2][0]:08x}",
            "store_arm_opcode":f"0x{triple[2][1]:08x}",
            "runtime_init_for_all_constructor_overloads_proven":False,
            "later_field_writes_or_runtime_changes_excluded":False,
        })
    # Scope is the exact six known A32 words plus the entry-save
    # instruction. No full function or callgraph path dominance claim.
    return {
        "scope":"SINGLE_CYCC_CONSTRUCTOR_OVERLOAD_STATIC_ARM_INITIALIZERS",
        "native_function":NAME,
        "provider":PROVIDER,
        "function_address":f"0x{START:08x}",
        "function_size":SIZE,
        "function_sha256":hashlib.sha256(
            struct.pack("<"+"I"*len(words),*(
                words[START+4*i] for i in range(SIZE//4)
            ))
        ).hexdigest(),
        "incoming_this_r0_saved_to_fp_minus16":True,
        "local_initializers":witnesses,
        "direct_initialization_values_for_this_overload_pinned":True,
        "all_constructor_overloads_analyzed":False,
        "init_path_executes_on_live_camera_proven":False,
        "runtime_enum_or_chroma_byte_layout_proven":False,
        "native_dma_ownership_verified":False,
        "camera_flash_permitted":False,
    }


def compare_versions(fw114:dict,fw115:dict)->dict:
    a=constructor_proof(fw114)
    b=constructor_proof(fw115)
    return {
        "fw114":a,
        "fw115":b,
        "same_constructor_arm_body":
            a["function_sha256"]==b["function_sha256"],
        "same_single_overload_field_initializers":
            a["local_initializers"]==b["local_initializers"],
        "runtime_constructor_usage_proven":False,
        "other_overloads_and_pixel_pack_verified":False,
        "camera_flash_permitted":False,
    }
