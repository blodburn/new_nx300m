#!/usr/bin/env python3
"""Trace actual FW1.14/1.15 SYSMMAP size arguments across ARM PLT callsites.

Only static native ARM32 AAPCS instruction evidence in third-party
untrusted firmware. This tool does not observe a physical camera,
prove runtime allocation sizes, make firmware modifications or flash.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_fw114_sysmmap_osif_arg_windows as osif
import nx300m_pw_ui_bl_call_audit as arms
import nx300m_native_jpeg_abi_boundary_audit as jpeg

# Exact ARM32 function body and ARM PLT BL witnesses verified in prior CI.
# Two different segment-free calls are distinct paths, not necessarily
# both executed per actual frame.
CHAINS = {
    "sysmmap_alloc": (0x000032f0,148, {"sysmmap_mgr_alloc":(0x00003360,)}),
    "sysmmap_cached_alloc":(
        0x00003384,148, {"sysmmap_mgr_alloc":(0x000033f4,)}),
    "sysmmap_mgr_alloc":(
        0x0000452c,384, {"sysmmap_client_alloc":(0x00004620,)}),
    "sysmmap_client_alloc":(
        0x0000780c,208, {"sysmmap_segment_alloc":(0x0000786c,)}),
    "sysmmap_segment_alloc":(
        0x0000a114,796, {"sysmmap_osif_alloc":(0x0000a344,)}),
    "sysmmap_free":(
        0x00003418,128, {"sysmmap_mgr_free":(0x0000347c,)}),
    "sysmmap_mgr_free":(
        0x000046ac,356, {"sysmmap_client_free":(0x00004784,)}),
    "sysmmap_client_free":(
        0x000078dc,260, {"sysmmap_segment_free":(0x00007914,)}),
    "sysmmap_segment_free":(
        0x0000a828,984, {"sysmmap_osif_free":(
            0x0000a93c,0x0000a9e4)}),
}
MAX_METHODS = 16
MAX_FUNCTION = 4096


# Exact final recognizable r1 writers in the native ARM window. This
# only verifies the immediate local argument setup; no complete dataflow
# or actual runtime length can be inferred.
R1_WRITER_WITNESSES = {
    "sysmmap_alloc": {0x3360:(0x3358,0xe1a01003)},
    "sysmmap_cached_alloc": {0x33f4:(0x33ec,0xe1a01003)},
    "sysmmap_mgr_alloc": {0x4620:(0x4618,0xe51b1024)},
    "sysmmap_client_alloc": {0x786c:(0x7864,0xe51b1014)},
    "sysmmap_segment_alloc": {0xa344:(0xa33c,0xe1a01002)},
    "sysmmap_free": {0x347c:(0x3478,0xe51b100c)},
    "sysmmap_mgr_free": {0x4784:(0x4780,0xe51b1024)},
    "sysmmap_client_free": {0x7914:(0x7910,0xe51b1014)},
    "sysmmap_segment_free": {
        0xa93c:(0xa938,0xe1a01003),
        0xa9e4:(0xa9e0,0xe1a01003)},
}


def last_r1_writer_witness(
    words:tuple[int,...],start:int,site:int,function:str
)->dict:
    expected=R1_WRITER_WITNESSES.get(function,{}).get(site)
    if not expected:
        raise ValueError("Unknown native SYSMMAP r1 witness")
    writer_pc,opcode=expected
    index=(writer_pc-start)//4
    if (writer_pc<start or (writer_pc-start)%4 or
        index>=len(words) or site<=writer_pc or
        site-start>=len(words)*4 or words[index]!=opcode):
        raise ValueError("Changed native SYSMMAP r1 writer at callsite")
    decoded=osif.classify_arm_argument_writer(opcode,writer_pc,1)
    if decoded is None or decoded["register"]!="r1":
        raise ValueError("Native r1 witness is not an ARM r1 writer")
    # No supported unconditional instruction after the witness writes
    # r1 again. Other kinds of instructions and aliases remain unresolved.
    for i in range(index+1,(site-start)//4):
        if osif.classify_arm_argument_writer(words[i],start+4*i,1):
            raise ValueError("Different nearby r1 writer before native BL")
    return {
        "writer_site":f"0x{writer_pc:08x}",
        "writer_opcode":f"0x{opcode:08x}",
        "writer_type":decoded["kind"],
        "source_register":decoded.get("source_register"),
        "value":decoded.get("value"),
        "only_static_local_r1_writer_witness":True,
        "unmodeled_aliases_branches_or_other_writers_excluded":False,
        "same_length_as_listener_descriptor_proven":False,
        "live_allocated_bytes_measured":False,
    }


def callsite_window(
    words:tuple[int,...],start:int,callsite:int
) -> dict:
    """Read bounded ARM words and candidate r1 writers; never infer bytes."""
    window=osif.argument_context(words,start,callsite,lookback=32)
    count=(callsite-start)//4
    entry=[{
        "pc":f"0x{start+i*4:08x}",
        "opcode":f"0x{word:08x}",
    } for i,word in enumerate(words[:min(count,12)])]
    window["first_12_function_arm_words"]=entry
    window["r1_is_actual_allocated_byte_count_proven"]=False
    window["same_value_as_listener_descriptor_plus4_proven"]=False
    window["runtime_camera_mmap_size_verified"]=False
    return window


def inspect(root:Path)->dict:
    path=provider.find_provider(root,provider.LIBRARY)
    blob=path.read_bytes()
    headers=elf.program_headers(path)
    symbol_rows=provider.parse_symbol_rows(
        abi.tool(["readelf","-Ws",str(path)]))
    defined={row["symbol"]:row for row in symbol_rows
             if row["kind"]=="FUNC" and row["is_defined"]}
    relocs=jpeg.relocations(abi.tool(["readelf","-Wr",str(path)]))
    if len(CHAINS)>MAX_METHODS:
        raise ValueError("Unbounded SYSMMAP function set")
    evidence={}
    for name,(start,size,expected) in CHAINS.items():
        info=defined.get(name)
        if (info is None or int(info["address"],16)!=start or
            info["size"]!=size or size%4 or size>MAX_FUNCTION):
            raise ValueError("Wrong real SYSMMAP native ABI function "+name)
        offset=elf.file_range_for_vaddr(headers,start,size)
        if offset+size>len(blob):
            raise ValueError("Truncated native SYSMMAP function")
        words=struct.unpack_from("<"+"I"*(size//4),blob,offset)
        scanned=arms.scan_direct_calls(blob,start,size,headers)
        resolved={}
        for site,target in scanned:
            try:
                got=jpeg.plt_got(blob,headers,target)
                callee=relocs.get(got)
            except ValueError:
                callee=None
            if callee in expected:
                resolved.setdefault(callee,[]).append(site)
        if {k:tuple(v) for k,v in resolved.items()}!=expected:
            raise ValueError("Wrong FW native mmap callsite chain "+name)
        evidence[name]={
            "start":f"0x{start:08x}",
            "size_bytes":size,
            "body_sha256":hashlib.sha256(
                blob[offset:offset+size]).hexdigest(),
            "calls":[{
                "callee":callee,
                "site":f"0x{site:08x}",
                "immediate_r1_writer_witness":
                    last_r1_writer_witness(words,start,site,name),
                **callsite_window(words,start,site)
            } for callee,sites in expected.items() for site in sites],
            "live_camera_syscall_or_callback_invoked":False,
            "exact_live_argument_length_known":False,
        }
    return {
        "scope":"UNAUTHENTICATED_FW114_115_ARM32_STATIC_SYSMMAP_CHAIN",
        "native_firmware_elf_sha256":hashlib.sha256(blob).hexdigest(),
        "methods":evidence,
        "listener_descriptor_plus4_to_mmap_r1_complete_proof":False,
        "allocator_returned_byte_count_or_success_verified":False,
        "physical_camera_dma_or_memory_lifetime_proven":False,
        "camera_firmware_flash_permitted":False,
    }


def compare_versions(root114:Path,root115:Path)->dict:
    x,y=inspect(root114),inspect(root115)
    return {
        "fw114":x,"fw115":y,
        "native_provider_byte_equal":
            x["native_firmware_elf_sha256"]==
            y["native_firmware_elf_sha256"],
        "all_static_function_bodies_equal":
            all(x["methods"][k]["body_sha256"]==
                y["methods"][k]["body_sha256"] for k in CHAINS),
        "runtime_on_camera_malloc_size_proven":False,
        "firmware_flash_permitted":False,
    }
