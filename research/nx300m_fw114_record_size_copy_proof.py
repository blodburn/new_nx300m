#!/usr/bin/env python3
"""FW1.14/1.15: verify segment +12 receives copied source +8 word.

Read-only A32 ELF analysis. This audit validates the static *conditional*
store performed by sysmmap_segment_update_empty_seg, not a positive
nonzero value, not an initialized live frame, and not flash readiness.
The firmware is held only in the private CI runner temporary directory.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_fw114_segment_get_data_writers as record

FUNCTION = "sysmmap_segment_update_empty_seg"
START = 0x0000b0e0
SIZE = 244
# Verified FW1.14 ARM32 instructions from private CI output.
COPIED_WORDS = {
    0x0000b118:0xe51b301c,  # LDR r3,[fp,#-28] source pointer
    0x0000b124:0xe51b0018,  # LDR r0,[fp,#-24] destination lookup input
    0x0000b12c:0xe50b0014,  # STR helper's r0,[fp,#-20]
    0x0000b164:0xe51b301c,  # LDR r3,[fp,#-28] source pointer
    0x0000b168:0xe5932000,  # LDR r2,[r3,#0]
    0x0000b16c:0xe51b3014,  # LDR r3,[fp,#-20] destination pointer
    0x0000b170:0xe5832000,  # STR r2,[r3,#0]
    0x0000b174:0xe51b301c,  # LDR r3,[fp,#-28]
    0x0000b178:0xe5932004,  # LDR r2,[r3,#4]
    0x0000b17c:0xe51b3014,  # LDR r3,[fp,#-20]
    0x0000b180:0xe5832004,  # STR r2,[r3,#4]
    0x0000b184:0xe51b301c,  # LDR r3,[fp,#-28]
    0x0000b188:0xe5932008,  # LDR r2,[r3,#8]
    0x0000b18c:0xe51b3014,  # LDR r3,[fp,#-20]
    0x0000b190:0xe5832008,  # STR r2,[r3,#8]
    0x0000b194:0xe51b3014,  # LDR r3,[fp,#-20]
    0x0000b198:0xe3a02000,  # MOV r2,#0
    0x0000b19c:0xe583200c,  # STR r2,[r3,#12]
    0x0000b1a0:0xe51b3014,  # LDR r3,[fp,#-20]
    0x0000b1a4:0xe3a02065,  # MOV r2,#0x65
    0x0000b1a8:0xe5c32010,  # STRB r2,[r3,#16]
}
CALL_GET_MEMPOOL = 0x0000b128


def proof_from_words(words:tuple[int,...],start:int=START) -> dict:
    if (start!=START or len(words)!=SIZE//4 or
        any(type(word) is not int or word<0 or word>0xffffffff
            for word in words)):
        raise ValueError("Wrong native segment copy function body")
    for pc,expected in COPIED_WORDS.items():
        if words[(pc-start)//4]!=expected:
            raise ValueError(f"Changed native segment field-copy opcode {pc:#x}")
    if (words[(CALL_GET_MEMPOOL-start)//4]>>24)&15!=11:
        raise ValueError("Missing native get_mempool_data BL")
    return {
        "native_function":FUNCTION,
        "native_address":f"0x{START:08x}",
        "source_field_offset_bytes":8,
        "source_load_site":"0x0000b188",
        "source_pointer_stack_slot_fp_minus28":True,
        "destination_helper":"sysmmap_segment_get_mempool_data",
        "destination_helper_bl":"0x0000b128",
        "destination_helper_returns_get_data_plus_bytes":4,
        "destination_local_stack_slot_fp_minus20":True,
        "destination_field_offset_from_helper":8,
        "destination_store_site":"0x0000b190",
        "effective_destination_field_from_get_data_return":12,
        "static_copy_formula":"*(get_data(r0)+12) = *(source_ptr+8)",
        "adjacent_zero_reset_effective_offset":16,
        "read_value_may_be_zero":True,
        "nonzero_value_or_real_allocation_size_proven":False,
        "source_pointer_is_user_listener_descriptor_proven":False,
        "record_pointer_identity_in_other_calls_proven":False,
        "all_control_flow_paths_reach_copy_proven":False,
        "camera_runtime_mapping_or_dma_safety_proven":False,
        "camera_flash_permitted":False,
    }


def inspect(root:Path)->dict:
    # Reuse already independently checked real imported BL links and +4
    # helper pointer chain from the previous review.
    upstream=record.inspect(root)
    mempool=upstream["static_reset_vs_alloc_record_offset_proof"]
    if (mempool["get_data_return_plus_bytes"]!=4 or
        mempool["empty_reset_effective_offset_from_get_data_return"]!=16 or
        mempool["alloc_size_load_offset_from_get_data_return"]!=12 or
        mempool["positive_size_initializer_identified"]):
        raise ValueError("Unexpected native get_data pointer provenance")
    entry=next((f for f in upstream["segment_functions_examined"]
                if f["symbol"]==FUNCTION),None)
    if (entry is None or entry["address"]!=f"0x{START:08x}" or
        entry["size_bytes"]!=SIZE or not any(
        c["site"]==f"0x{CALL_GET_MEMPOOL:08x}" and
        c["imported_symbol"]=="sysmmap_segment_get_mempool_data"
        for c in entry["writer_function_imported_arm_calls"])):
        raise ValueError("Different native segment copy or helper call")
    provider_path=provider.find_provider(root,provider.LIBRARY)
    headers=elf.program_headers(provider_path)
    offset=elf.file_range_for_vaddr(headers,START,SIZE)
    with provider_path.open("rb") as file:
        file.seek(offset)
        image=file.read(SIZE)
    if len(image)!=SIZE:
        raise ValueError("Truncated ARM function")
    words=struct.unpack("<"+"I"*(SIZE//4),image)
    proof=proof_from_words(words)
    # Do not ship OEM code bytes. Only opcode witnesses and SHA metadata.
    return {
        "scope":"UNOFFICIAL_PRIVATE_FW_STATIC_ARM_RECORD_FIELD_COPY",
        "native_segment_body_sha256":hashlib.sha256(image).hexdigest(),
        "candidate_positive_field_copy_static_proof":proof,
        "actual_source_value_bytes":None,
        "actual_allocated_region_length_bytes":None,
        "live_camera_firmware_modification_permitted":False,
    }


def compare_versions(root114:Path,root115:Path)->dict:
    a,b=inspect(root114),inspect(root115)
    return {
        "fw114":a,
        "fw115":b,
        "native_body_equal":a["native_segment_body_sha256"]==
                            b["native_segment_body_sha256"],
        "actual_mmap_length_observed":False,
        "camera_flash_permitted":False,
    }
