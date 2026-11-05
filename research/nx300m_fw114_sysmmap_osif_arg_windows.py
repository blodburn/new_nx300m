#!/usr/bin/env python3
"""Read-only FW1.14/1.15 ARM mmap/ioctl/munmap call-argument windows.

The ARM AAPCS passes mmap(addr, length, prot, flags, fd, offset):
r0=addr, r1=length, r2=prot, r3=flags, with later args on stack.
Native instruction windows and register-write candidates are NOT proof
of a live requested size, a successful syscall, allocated extent or DMA
ownership. The input is the private, unofficial firmware ELF32.
No device, firmware patch, target code execution, or upload is allowed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sysmmap_provider_audit as provider
import nx300m_pw_ui_bl_call_audit as arms
import nx300m_native_jpeg_abi_boundary_audit as jpeg

EXPECTED = {
    "sysmmap_osif_alloc": {
        "address": 0x0000c7a0, "size": 284,
        "calls": {"ioctl": 0x0000c7f0, "mmap": 0x0000c81c},
    },
    "sysmmap_osif_free": {
        "address": 0x0000c8bc, "size": 52,
        "calls": {"munmap": 0x0000c8d8},
    },
}
REGISTER_NAMES = {0:"r0",1:"r1",2:"r2",3:"r3"}
MAX_WINDOW = 32


def classify_arm_argument_writer(word:int, address:int, reg:int)->dict|None:
    """Bounded writer candidates; effects of branches/calls are not modeled."""
    if not (0<=word<=0xffffffff and address>=0 and address%4==0
            and reg in REGISTER_NAMES):
        raise ValueError("Invalid ARM instruction or AAPCS register")
    cond=word>>28
    if cond!=14:
        return None
    # Immediate-mode load: LDR rN,[rM,#imm] or LDR rN,[pc,#imm]
    if (((word>>26)&3)==1 and not ((word>>25)&1) and
        ((word>>20)&1) and ((word>>12)&15)==reg):
        return {
            "kind":"LDR_IMMEDIATE",
            "register":REGISTER_NAMES[reg],
            "source_register":f"r{(word>>16)&15}",
            "byte_offset":(word&0xfff)*(1 if (word>>23)&1 else -1),
            "opcode":f"0x{word:08x}",
            "site":f"0x{address:08x}",
            "proves_arg_value":False,
        }
    # ARM data-processing immediate / simple register MOV or ADD.
    if ((word>>26)&3)==0 and not ((word>>20)&1) and (
        (word>>12)&15)==reg):
        opcode=(word>>21)&15
        if opcode not in (4,13):
            return None
        imm=bool((word>>25)&1)
        src=(word>>16)&15
        if imm:
            if ((word>>8)&15)!=0:
                return None   # rotated immediate: no simple constant claim
            arg=word&255
        else:
            if (word&0xff0)!=0:
                return None   # shifted register: do not guess
            arg=word&15
        return {
            "kind":("MOV_IMMEDIATE" if imm else "MOV_REGISTER")
                   if opcode==13 else
                   ("ADD_IMMEDIATE" if imm else "ADD_REGISTER"),
            "register":REGISTER_NAMES[reg],
            "source_register":None if opcode==13 else f"r{src}",
            "value":arg if imm else f"r{arg}",
            "opcode":f"0x{word:08x}",
            "site":f"0x{address:08x}",
            "proves_arg_value":False,
        }
    return None


def argument_context(words:tuple[int,...],start:int,site:int,
                     lookback:int=22)->dict:
    """Raw bounded ARM window before one syscall BL, never fabricate values."""
    if (start&3 or site&3 or site<start or site>=start+4*len(words) or
        not 1<=lookback<=MAX_WINDOW):
        raise ValueError("Invalid ARM OSIF callsite window")
    index=(site-start)//4
    if (index>=len(words) or words[index]>>24&15 != 0xb):
        # Last check only tests BL immediate top opcode nibble, not target.
        raise ValueError("Expected ARM-state branch-with-link at callsite")
    lo=max(0,index-lookback)
    preceding=[{
        "pc":f"0x{start+4*j:08x}",
        "opcode":f"0x{words[j]:08x}",
    } for j in range(lo,index)]
    candidates={}
    for reg,label in REGISTER_NAMES.items():
        values=[]
        for j in range(lo,index):
            data=classify_arm_argument_writer(words[j],start+4*j,reg)
            if data:
                values.append(data)
        candidates[label]=values[-6:]
    return {
        "callsite":f"0x{site:08x}",
        "call_opcode":f"0x{words[index]:08x}",
        "preceding_arm_words":preceding,
        "candidate_argument_writers":candidates,
        "arm_aapcs_6_arg_mmap_length_register":"r1",
        "native_mmap_argument_provenance_complete":False,
        "actual_requested_mmap_bytes_observed":False,
        "kernel_allocated_bytes_verified":False,
    }


def inspect(root:Path)->dict:
    path=provider.find_provider(root,provider.LIBRARY)
    image=path.read_bytes()
    loads=elf.program_headers(path)
    rows=provider.parse_symbol_rows(
        abi.tool(["readelf","-Ws",str(path)]))
    entries={row["symbol"]:row for row in rows if row["is_defined"] and
             row["kind"]=="FUNC"}
    imported=jpeg.relocations(abi.tool(["readelf","-Wr",str(path)]))
    out={}
    for name,expected in EXPECTED.items():
        fn=entries.get(name)
        if (not fn or int(fn["address"],16)!=expected["address"] or
            fn["size"]!=expected["size"] or fn["size"]%4):
            raise ValueError("Different native OSIF function body or address")
        start,size=expected["address"],expected["size"]
        offset=elf.file_range_for_vaddr(loads,start,size)
        words=struct.unpack_from("<"+"I"*(size//4),image,offset)
        links=arms.scan_direct_calls(image,start,size,loads)
        actual={}
        for site,target in links:
            try:
                plt_slot=jpeg.plt_got(image,loads,target)
                symbol=imported.get(plt_slot)
            except ValueError:
                symbol=None
            if symbol in expected["calls"]:
                if symbol in actual:
                    raise ValueError("Ambiguous native OSIF BL target")
                actual[symbol]=site
        if actual!=expected["calls"]:
            raise ValueError("Missing actual OS mmap/ioctl/munmap callsite")
        out[name]={
            "address":f"0x{start:08x}",
            "size_bytes":size,
            "body_sha256":hashlib.sha256(
                image[offset:offset+size]).hexdigest(),
            "os_calls":{
                name:argument_context(words,start,site)
                for name,site in sorted(actual.items())
            },
            "real_camera_os_call_execution_verified":False,
            "real_memory_region_validity_verified":False,
        }
    return {
        "scope":"UNOFFICIAL_FW_OFFLINE_ARM32_SYSMMAP_AAPCS_WINDOWS",
        "provider":provider.LIBRARY,
        "functions":out,
        "native_aapcs_arg_length_proven_by_linear_window":False,
        "runtime_mmap_length_bytes":None,
        "runtime_mmap_success":None,
        "camera_pixel_buffer_ownership_verified":False,
        "firmware_flash_permitted":False,
    }


def compare_versions(root114:Path,root115:Path)->dict:
    a,b=inspect(root114),inspect(root115)
    return {
        "fw114":a,"fw115":b,
        "osif_function_body_sha256_equal":all(
            a["functions"][k]["body_sha256"]==
            b["functions"][k]["body_sha256"]
            for k in EXPECTED),
        "actual_camera_mmap_extent_verified":False,
        "firmware_flash_permitted":False,
    }
