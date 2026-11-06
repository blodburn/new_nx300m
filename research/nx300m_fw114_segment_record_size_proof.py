#!/usr/bin/env python3
"""Verify FW1.14/1.15 native segment-record size conversion to mmap ABI.

Read-only static ARM32 witness in the private, third-party mirror firmware.
This does not measure actual camera allocation length or prove native DMA
safety, buffer lifetime, filesystem recovery or firmware flash readiness.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_pw_ui_bl_call_audit as arm
import nx300m_native_jpeg_abi_boundary_audit as jpeg

LIBRARY = "libsys-mmap-manager.so"
FUNCTION = "sysmmap_segment_alloc"
START = 0x0000a114
SIZE = 796
DATA_CALL = 0x0000a2e4
ALLOC_CALL = 0x0000a344

# Program-counter-specific instructions from actual mirror FW1.14 native ARM.
# The manager data record is returned by sysmmap_segment_get_data().
WORDS = {
    0x0000a2e8:0xe50b0024, # STR r0,[fp,#-36] after get_data
    0x0000a2f4:0x1a000009, # BNE -> 0xa320
    0x0000a320:0xe51b3024, # LDR r3,[fp,#-36] record pointer
    0x0000a324:0xe5931008, # LDR r1,[r3,#8] record field
    0x0000a328:0xe51b3024, # LDR r3,[fp,#-36] record pointer
    0x0000a32c:0xe593300c, # LDR r3,[r3,#12] size-unit value
    0x0000a330:0xe1a02503, # MOV r2,r3,LSL #10
    0x0000a334:0xe51b3068, # LDR r3,[fp,#-104]
    0x0000a338:0xe1a00001, # MOV r0,r1
    0x0000a33c:0xe1a01002, # MOV r1,r2 (OSIF requested length)
    0x0000a340:0xe1a02003, # MOV r2,r3
}
MAX_U32 = 0xffffffff


def decode_lsl_bytes(opcode:int)->int:
    """Recognize ARM MOV r2, r3, LSL immediate, not a guessed shift."""
    if not isinstance(opcode,int) or not 0<=opcode<=MAX_U32:
        raise ValueError("Invalid native ARM opcode")
    fields = {
        "cond":(opcode>>28)&15,
        "class":(opcode>>26)&3,
        "immediate":(opcode>>25)&1,
        "alu":(opcode>>21)&15,
        "update_flags":(opcode>>20)&1,
        "dst":(opcode>>12)&15,
        "rm":opcode&15,
        "bit4":(opcode>>4)&1,
        "shift_type":(opcode>>5)&3,
        "shift":(opcode>>7)&31,
    }
    if (fields["cond"]!=14 or fields["class"]!=0 or
        fields["immediate"]!=0 or fields["alu"]!=13 or
        fields["update_flags"]!=0 or fields["dst"]!=2 or
        fields["rm"]!=3 or fields["bit4"]!=0 or
        fields["shift_type"]!=0):
        raise ValueError("Unsupported ARM32 register-length conversion")
    if fields["shift"]!=10:
        raise ValueError("Changed firmware native size shift")
    return fields["shift"]


def simulated_request_bytes(record_field_units:int)->int:
    """Host-side safe, NON-camera calculation; reject 32-bit wraparound."""
    if (isinstance(record_field_units,bool) or
        not isinstance(record_field_units,int) or
        not 0<=record_field_units<=MAX_U32):
        raise ValueError("Not a nonnegative 32-bit native record value")
    size=record_field_units<<10
    if size>MAX_U32:
        raise ValueError("Native 32-bit left shift would wrap; refuse")
    return size


def proof_from_words(words:tuple[int,...],start:int=START)->dict:
    """Pin actual words and branch; this is not a full dynamic dataflow."""
    if start!=START or len(words)!=SIZE//4 or any(
        not isinstance(v,int) or not 0<=v<=MAX_U32 for v in words
    ):
        raise ValueError("Unexpected native segment ELF function body")
    for pc,expected in WORDS.items():
        idx=(pc-start)//4
        if pc<start or idx>=len(words) or words[idx]!=expected:
            raise ValueError(f"Changed native segment ARM instruction at {pc:#x}")
    shift=decode_lsl_bytes(words[(0xa330-start)//4])
    branch=words[(0xa2f4-start)//4]
    # ARM BNE immediate: signed word displacement; require exact target.
    if branch>>28!=1 or (branch>>24)&15!=10:
        raise ValueError("Wrong native conditional segment branch")
    off=branch&0xffffff
    if off&0x800000:
        off-=0x1000000
    if 0xa2f4+8+off*4!=0xa320:
        raise ValueError("Conditional branch does not reach size expression")
    return {
        "segment_function":FUNCTION,
        "segment_static_size_source":"segment_get_data_return_record_word_at_plus12",
        "record_pointer_saved_from_r0_at":"0x0000a2e8",
        "record_pointer_reloaded_at":["0x0000a320","0x0000a328"],
        "record_size_word_load":"0x0000a32c",
        "shift_left_bits":shift,
        "length_to_osif_r1_at":"0x0000a33c",
        "static_mmap_length_formula":
            "uint32(record[+12] << 10) [wrap possible]",
        "conditional_path_may_be_skipped":True,
        "record_value_or_actual_allocated_bytes_observed":False,
        "descriptor_plus4_equals_record_plus12_times1024":False,
        "on_camera_dma_coherency_or_ownership_verified":False,
        "firmware_flash_permitted":False,
    }


def inspect(root:Path)->dict:
    library=provider.find_provider(root,LIBRARY)
    elf_body=library.read_bytes()
    loads=elf.program_headers(library)
    funcs=provider.parse_symbol_rows(abi.tool([
        "readelf","-Ws",str(library)]))
    defined=[f for f in funcs if f["is_defined"] and
             f["kind"]=="FUNC" and f["symbol"]==FUNCTION]
    if len(defined)!=1 or int(defined[0]["address"],16)!=START or (
        defined[0]["size"]!=SIZE):
        raise ValueError("Native segment allocator identity changed")
    offset=elf.file_range_for_vaddr(loads,START,SIZE)
    if offset+SIZE>len(elf_body):
        raise ValueError("Truncated native sysmmap segment allocator")
    words=struct.unpack_from("<"+"I"*(SIZE//4),elf_body,offset)
    proof=proof_from_words(words)
    relocations=jpeg.relocations(abi.tool([
        "readelf","-Wr",str(library)]))
    direct=arm.scan_direct_calls(elf_body,START,SIZE,loads)
    wanted={
        DATA_CALL:"sysmmap_segment_get_data",
        ALLOC_CALL:"sysmmap_osif_alloc",
    }
    witnesses={}
    for site,target in direct:
        if site not in wanted:
            continue
        try:
            got=jpeg.plt_got(elf_body,loads,target)
            symbol=relocations.get(got)
        except ValueError:
            symbol=None
        if symbol!=wanted[site] or site in witnesses:
            raise ValueError("Native mmap record/alloc call target changed")
        witnesses[site]=symbol
    if witnesses!=wanted:
        raise ValueError("Missing source record call or OSIF alloc ARM BL")
    return {
        "scope":"UNAUTHENTICATED_PRIVATE_FW_ARM_STATIC_ONLY",
        "library":LIBRARY,
        "native_segment_body_sha256":hashlib.sha256(
            elf_body[offset:offset+SIZE]).hexdigest(),
        "arm_call_witnesses":{
            f"0x{site:08x}":name for site,name in sorted(witnesses.items())
        },
        **proof,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a,b=inspect(fw114),inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "segment_function_body_byte_equal":
            a["native_segment_body_sha256"]==
            b["native_segment_body_sha256"],
        "actual_mmap_bytes_measured":False,
        "camera_flash_permitted":False,
    }
