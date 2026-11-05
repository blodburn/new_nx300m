#!/usr/bin/env python3
"""Find possible callback registration of native AllocListener/FreeListener.

Only static ELF symbol/relocation/pointer evidence from unofficial FW1.14
and FW1.15 mirror libmm-photo.so. No code is executed or patched.

R_ARM_RELATIVE raw addends and matching pointer words are candidates, not
proof of runtime listener registration or invocation frequency.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif

MAX_FILE=2*1024*1024
MAX_RELOCS=100000
TARGETS=("AllocListener","FreeListener")

def relative_relocations(text:str)->set[int]:
    """readelf ELF32 REL entries with no external symbol."""
    result=set()
    pattern=re.compile(
        r"^\s*([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+R_ARM_RELATIVE(?:\s|$)"
    )
    for line in text.splitlines():
        m=pattern.match(line)
        if m:
            result.add(int(m[1],16))
            if len(result)>MAX_RELOCS:
                raise ValueError("Too many candidate relative relocations")
    return result


def word_sites(data:bytes,segments:list[tuple[int,int,int]],
               target_address:int,relative:set[int])->list[dict]:
    """Read in-file REL relocated pointer words at *exact* offsets.

    We intentionally do not search unrelocated address coincidences in
    executable bytes, which would overstate support for callback identity.
    """
    out=[]
    for addr in sorted(relative):
        try:
            off=elf.file_range_for_vaddr(segments,addr,4)
        except ValueError:
            continue
        raw=struct.unpack_from("<I",data,off)[0]
        if raw!=target_address:
            continue
        out.append({
            "relocation_address":f"0x{addr:08x}",
            "raw_addend":"0x%08x"%raw,
            "R_ARM_RELATIVE_confirmed":True,
            "listener_registering_function_proven":False,
            "callback_invocation_on_camera_proven":False,
        })
        if len(out)>200:
            raise ValueError("Too many callback pointer relocation candidates")
    return out


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (
        1024<=path.stat().st_size<=MAX_FILE
    ):
        raise ValueError("Need bounded private libmm-photo.so")
    blob=path.read_bytes()
    loads=elf.program_headers(path)
    symbol_text=sif.arm.offline_tool(["readelf","-Ws",str(path)])
    syms=sif.symbol_index(symbol_text)
    reloc_text=sif.arm.offline_tool(["readelf","-Wr",str(path)])
    explicit=sif.relocation_symbol_targets(reloc_text)
    relative=relative_relocations(reloc_text)
    report={}
    for label in TARGETS:
        symbol=sif.select(syms,label,"FUNC")
        addr=symbol["address"]
        direct=[]
        for place,item in sorted(explicit.items()):
            if item["symbol_value"]==f"0x{addr:08x}" and (
                item["mangled_symbol"]==label
            ):
                direct.append({
                    "relocation_address":f"0x{place:08x}",
                    "relocation_type":item["relocation_type"],
                    "symbol":item["mangled_symbol"],
                    "on_camera_registration_proven":False,
                })
        report[label]={
            "native_function_address":f"0x{addr:08x}",
            "native_function_bytes":symbol["size"],
            "explicit_dynamic_symbol_relocations":direct,
            "R_ARM_RELATIVE_word_address_candidates":
                word_sites(blob,loads,addr,relative),
            "listener_runtime_registering_site_proven":False,
        }
    return {
        "scope":"UNOFFICIAL_FW114_LIBMM_PHOTO_STATIC_CALLBACK_POINTERS",
        "libmm_photo_sha256":hashlib.sha256(blob).hexdigest(),
        "relative_relocation_count":len(relative),
        "listener_pointer_evidence":report,
        "all_possible_registration_operators_scanned":False,
        "actual_listener_runtime_frequency_proven":False,
        "shared_pool_DMA_lifetime_verified":False,
        "camera_firmware_patch_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a=inspect(fw114);b=inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "libmm_photo_elf_byte_equal":a["libmm_photo_sha256"]==
                                     b["libmm_photo_sha256"],
        "on_camera_callback_execution_proven":False,
        "firmware_install_permitted":False,
    }
