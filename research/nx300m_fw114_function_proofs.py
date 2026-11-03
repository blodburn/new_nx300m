#!/usr/bin/env python3
"""Host-only static function-body evidence from private ARM32 camera ELF.

Never executes an ELF or firmware. File-range SHA-256 for version-specific
functions and exact ARM JPEG sampling switch; NOT a camera ABI approval.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct
import subprocess

TARGETS = (
    "DscJfifHal::Parse(",
    "DscJfif::JpegEncode(",
    "DscJfifHal::Encode(",
    "DscImage::SaveExifImage(",
    "DscImage::GetExifImageInfo(",
    "DscImage::CopyExifInfo(",
    "CMmDeviceDriver::EncodeYcc(",
)
MAX_FUNCTION = 256 * 1024
MAX_ELF = 96 * 1024 * 1024
MAX_READ_ELF_SYMBOL_TEXT = 18_000_000
SYM = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+"
    r"(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)
# Earlier MFW1.1 (Samsung 1.15) read-only static witness only. 
# 0x21 maps JPEG 4:2:2 and 0x22 JPEG 4:2:0 in DscJfifHal::Parse.
OLD_SOFS = {
    0x294a8: 0xe55b301b, 0x294ac: 0xe3530021,
    0x294b0: 0x1a000003, 0x294b4: 0xe51b3044,
    0x294b8: 0xe3a02000, 0x294bc: 0xe5832000,
    0x294c4: 0xe55b301b, 0x294c8: 0xe3530022,
    0x294cc: 0x1a000003, 0x294d0: 0xe51b3044,
    0x294d4: 0xe3a02001, 0x294d8: 0xe5832000,
}


def program_headers(path: Path) -> list[tuple[int,int,int]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ELF:
        raise ValueError("Invalid bounded private ELF")
    with path.open("rb") as stream:
        header = stream.read(52)
        if (len(header) < 52 or header[:4] != b"\x7fELF" or header[4] != 1
            or header[5] != 1 or struct.unpack_from("<H",header,18)[0] != 40):
            raise ValueError("Expected ARM32 little-endian ELF")
        offset = struct.unpack_from("<I", header, 28)[0]
        size, count = struct.unpack_from("<HH", header, 42)
        if not 32 <= size <= 64 or count > 80 or offset+size*count>path.stat().st_size:
            raise ValueError("Invalid ARM ELF PHDR table")
        stream.seek(offset)
        content = stream.read(size*count)
    entries=[]
    for i in range(count):
        p_type,p_offset,vaddr,paddr,filesz,memsz,flags,align=struct.unpack_from(
            "<IIIIIIII",content,i*size)
        if p_type==1 and filesz:
            if p_offset+filesz>path.stat().st_size:
                raise ValueError("PT_LOAD extends beyond physical ELF")
            entries.append((vaddr,filesz,p_offset))
    if not entries:
        raise ValueError("No file-backed ELF PT_LOAD")
    return entries


def file_range_for_vaddr(loads: list[tuple[int,int,int]],
                         vaddr: int, size: int) -> int:
    if size < 1 or size > MAX_FUNCTION:
        raise ValueError("Invalid or oversized function range")
    # ARM32 binary symbols may carry Thumb bit, but this is not a runtime pointer.
    start=vaddr&~1
    for base,backed,offset in loads:
        if base<=start and start+size<=base+backed:
            return offset+start-base
    raise ValueError("Function outside file-backed ARM load segment")


def inspect(path: Path, *, include_sampling: bool = False) -> dict:
    loads=program_headers(path)
    result=subprocess.run(["readelf","-Ws",str(path)],
                          capture_output=True,text=True,timeout=30,check=False)
    if result.returncode or len(result.stdout)>MAX_READ_ELF_SYMBOL_TEXT:
        raise ValueError("readelf function inventory failed")
    potential={}
    for line in result.stdout.splitlines():
        m=SYM.match(line)
        if m and any(s in m.group(4) for s in (
                "DscJfif","DscImage","CMmDeviceDriver")):
            key=m.group(4)
            val=(int(m.group(1),16),int(m.group(2)),m.group(3))
            if key in potential and potential[key]!=val:
                # A duplicate symbol with differing definition is ambiguous.
                raise ValueError("Ambiguous ELF symbol definitions")
            potential[key]=val
    if not potential:
        raise ValueError("No focused camera symbols in ELF")
    names=sorted(potential)
    decoded=subprocess.run(["c++filt"],input="\n".join(names)+"\n",
                           capture_output=True,text=True,timeout=30,check=False)
    demangled=decoded.stdout.splitlines()
    if decoded.returncode or len(demangled)!=len(names):
        raise ValueError("ELF symbol demangling failed")
    found={}
    with path.open("rb") as stream:
        for mangled,name in zip(names,demangled):
            if not any(name.startswith(prefix) for prefix in TARGETS):
                continue
            address,size,index=potential[mangled]
            if index=="UND" or size<1:
                continue
            offset=file_range_for_vaddr(loads,address,size)
            stream.seek(offset)
            body=stream.read(size)
            if len(body)!=size:
                raise ValueError("Truncated ELF function body")
            found[name]={"symbol_address":"0x%08x"%address,
                         "function_bytes":size,
                         "code_sha256":hashlib.sha256(body).hexdigest(),
                         "a_runtime_camera_abi_proof":False}
        if include_sampling:
            mismatch=[]
            for address,expected in OLD_SOFS.items():
                try:
                    offset=file_range_for_vaddr(loads,address,4)
                except ValueError:
                    mismatch.append(hex(address));continue
                stream.seek(offset)
                data=stream.read(4)
                if len(data)!=4 or struct.unpack("<I",data)[0]!=expected:
                    mismatch.append(hex(address))
    if include_sampling:
        return {
            "functions":found,
            "old_115_jpeg_sof_signature_points":len(OLD_SOFS),
            "old_115_jpeg_sof_signature_points_matching":
                len(OLD_SOFS)-len(mismatch),
            "old_115_jpeg_sof_static_signature_all_match":not mismatch,
            "sampling_420_branch_address_0x294c8_only_if_unchanged":True,
            "camera_buffer_layout_verified":False,
            "native_device_safe":False,
        }
    return {"functions":found, "native_device_safe":False}


def compare(a: dict,b: dict) -> dict:
    fa,fb=a["functions"],b["functions"]
    names=sorted(set(fa)&set(fb))
    return {
        "common_function_count":len(names),
        "functions":[{
            "function":name,
            "fw114_addr":fa[name]["symbol_address"],
            "fw115_addr":fb[name]["symbol_address"],
            "symbol_address_equal":
                fa[name]["symbol_address"]==fb[name]["symbol_address"],
            "function_code_sha256_equal":
                fa[name]["code_sha256"]==fb[name]["code_sha256"],
            "fw114_length":fa[name]["function_bytes"],
            "fw115_length":fb[name]["function_bytes"],
        } for name in names],
        "native_camera_abi_and_memory_contract_proven":False,
        "camera_flash_permitted":False,
    }
