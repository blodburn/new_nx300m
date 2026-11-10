#!/usr/bin/env python3
"""Offline ARM32 proof of the four JPEG CYcc getter *receiver arguments*.

Exact PC/opcode and bounded-frame-slot checks in unauthenticated mirrored
NX300M FW 1.14 / 1.15 libmm-photo.so. No device shell, DMA, firmware
modification, native execution, actual memory mapping, or flashing.

A matching stack-slot offset shows reuse of the SAME CALLER FRAME SLOT;
it does not by itself authenticate runtime identity of the pointed-to
CYcc object, prove all aliases, or establish pixel buffer ownership.
"""
from __future__ import annotations

import nx300m_fw114_encoder_format_pack_origins as fmt
import nx300m_fw114_jfif_r6_arg_provenance as mem

START=fmt.START
BODY_BYTES=fmt.BODY_BYTES
SAVE_SITE=0x34b28
SAVE_OPCODE=0xe50b1064  # STR r1,[fp,#-100] (AAPCS CYcc& parameter)
SLOT=-100


def trace_receiver_inputs(words:tuple[int,...],getter_paths:dict)->dict:
    """Decode four final local R0 setup words before named native getter BLs.

    A recorded frame slot is a *syntactic* address. Other control-flow and
    indirect writes may alter it. The caller is not actually executed.
    """
    if (not isinstance(words,tuple) or len(words)!=BODY_BYTES//4 or
        any(type(x)is not int or not 0<=x<=0xffffffff for x in words) or
        not isinstance(getter_paths,dict) or
        not getter_paths.get(
            "four_native_imported_getter_calls_and_r0_r3_paths_verified"
        ) or getter_paths.get("four_local_getter_equality_tests")!=4):
        raise ValueError("Expected validated FW1.14 getter ABI and bounded ARM body")
    if words[(SAVE_SITE-START)//4]!=SAVE_OPCODE:
        raise ValueError("Changed native CYcc& r1 argument prologue save")
    # Every direct ARM STR [fp, -100] is inventoried before any getter call.
    direct_stores=[]
    for i,opcode in enumerate(words):
        d=mem.decode_mem_word(opcode)
        if d and d["kind"]=="STR" and d["base_register"]==11 and (
            d["offset"]==SLOT
        ):
            direct_stores.append({
                "pc":f"0x{START+4*i:08x}",
                "opcode":f"0x{opcode:08x}",
                "source_register":f"r{d['data_register']}",
                "condition":d["condition"],
            })
            if len(direct_stores)>32:
                raise ValueError("Unbounded native frame slot direct writes")
    sources=[]
    for field,pairs in fmt.GETTER_CALLS.items():
        approved=getter_paths["getters"].get(field)
        if (not isinstance(approved,list) or len(approved)!=len(pairs)):
            raise ValueError("Missing validated native getter path")
        for checked,(callsite,getter,_,expected_value) in zip(approved,pairs):
            if (checked["imported_callsite"]!=f"0x{callsite:08x}" or
                checked["imported_native_getter"]!=getter or
                checked["compared_getter_return_value"]!=expected_value):
                raise ValueError("Getter call and verified receiver mapping differ")
            pc=callsite-4
            ix=(pc-START)//4
            opcode=words[ix]
            d=mem.decode_mem_word(opcode)
            is_frame_r0=(d is not None and
                d["kind"]=="LDR" and d["base_register"]==11 and
                d["data_register"]==0 and d["condition"]==14)
            slot=d["offset"] if is_frame_r0 else None
            sources.append({
                "field":field,
                "native_getter":getter,
                "callsite":f"0x{callsite:08x}",
                "r0_final_writer_site":f"0x{pc:08x}",
                "r0_final_writer_opcode":f"0x{opcode:08x}",
                "r0_final_writer_kind":(
                    "LDR_r0_from_fp_immediate" if is_frame_r0 else
                    "UNRESOLVED_OTHER_ARM_INSTRUCTION"
                ),
                "r0_frame_slot_offset":slot,
                "same_slot_as_saved_incoming_r1":slot==SLOT,
                "preceding_arm_context":[
                    {"pc":f"0x{START+4*k:08x}",
                     "opcode":f"0x{words[k]:08x}"}
                    for k in range(max(0,ix-3),ix+1)
                ],
                "runtime_receiver_pointer_identity_verified":False,
                "native_getter_receiver_lifetime_verified":False,
            })
    same_slot=all(x["same_slot_as_saved_incoming_r1"] for x in sources)
    initial_store_only=(
        len(direct_stores)==1 and
        direct_stores[0]=={
            "pc":f"0x{SAVE_SITE:08x}",
            "opcode":f"0x{SAVE_OPCODE:08x}",
            "source_register":"r1","condition":14,
        }
    )
    return {
        "scope":"READ_ONLY_PRIVATE_FW_ARM32_LOCAL_R0_RECEIVER_FRAME_SLOTS",
        "native_function":"CMmDeviceDriver::EncodeYcc(CYcc&, unsigned int)",
        "cycc_reference_incoming_aapcs_register":"r1",
        "incoming_r1_save_site":f"0x{SAVE_SITE:08x}",
        "incoming_r1_saved_to_fp_offset":SLOT,
        "direct_frame_slot_store_witnesses":direct_stores,
        "only_one_direct_fp_slot_store_before_getters":initial_store_only,
        "getter_receiver_evidence":sources,
        "recognized_getter_calls":len(sources),
        "four_getter_r0_setup_uses_incoming_r1_frame_slot":same_slot,
        "incoming_r1_runtime_object_same_across_all_calls_proven":False,
        "indirect_stack_alias_writes_excluded":False,
        "getter_object_lifetime_and_pixel_ownership_verified":False,
        "live_camera_YCC_type_or_scan_mode_verified":False,
        "native_camera_dma_cache_coherency_verified":False,
        "firmware_flash_permitted":False,
    }
