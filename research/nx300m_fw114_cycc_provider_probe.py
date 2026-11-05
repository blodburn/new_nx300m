#!/usr/bin/env python3
"""Find CYcc and memory-pool implementation providers in private FW UBI.

Only reads local extracted ELF symbol tables and function byte digests.
No native execution, camera access, root privileges or firmware modification.
The UBI files come from unauthenticated third-party mirror firmware.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import stat

import nx300m_fw114_sif_virtual_dispatch as symbols
import nx300m_fw114_function_proofs as elf

MAX_FILES=60000
MAX_ELF=16*1024*1024
NAMES=("libmm-type.so","libmm-photo.so","libcapture-fw-slpcam.so",
       "libcapture-fw-slpcam-nx300.so")
NEEDLES=(
    "CYcc::~CYcc()",
    "CYcc::GetType()",
    "CYcc::GetY0()",
    "CMemoryPool::GetAddr(",
    "CMemoryPool::GetInstance()",
    "CYcc::CYcc(sImgSize, unsigned long)",
    "CYcc::CYcc(sImgSize, sYccAddr",
)


def safe_sources(root:Path)->dict[str,Path]:
    """Realpaths must remain under the already extracted private root."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Expected real private firmware tree")
    resolved_root=root.resolve(strict=True)
    found:dict[str,dict[str,Path]]={}
    count=0
    for item in root.rglob("*"):
        count+=1
        if count>MAX_FILES:
            raise ValueError("Unbounded firmware tree")
        if item.name not in NAMES:
            continue
        try:
            resolved=item.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError,ValueError,RuntimeError) as exc:
            raise ValueError("Library alias escapes private firmware root") from exc
        if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
            raise ValueError("Not a real library file")
        if not 52<=resolved.stat().st_size<=MAX_ELF:
            raise ValueError("Unsupported provider ELF bytes")
        found.setdefault(item.name,{})[str(resolved)]=resolved
    output={}
    for name,locations in found.items():
        if len(locations)!=1:
            raise ValueError("Ambiguous library realpath: "+name)
        output[name]=next(iter(locations.values()))
    return output


def inspect(root:Path)->dict:
    providers=safe_sources(root)
    report={}
    for name in NAMES:
        path=providers.get(name)
        if path is None:
            report[name]={"present":False,"target_symbols":[]}
            continue
        loads=elf.program_headers(path)
        idx=symbols.symbol_index(symbols.arm.offline_tool(
            ["readelf","-Ws",str(path)]))
        matches=[]
        for title,entry in sorted(idx.items()):
            if entry["kind"]!="FUNC" or not any(
                title.startswith(want) for want in NEEDLES
            ):
                continue
            size=entry["size"];address=entry["address"]
            if size<4 or size>65536:
                continue
            off=elf.file_range_for_vaddr(loads,address,size)
            with path.open("rb") as stream:
                stream.seek(off)
                body=stream.read(size)
            if len(body)!=size:
                raise ValueError("Provider ARM method truncated")
            matches.append({
                "name":title,
                "address":"0x%08x"%address,
                "function_bytes":size,
                "sha256":hashlib.sha256(body).hexdigest(),
                "actual_function_run_on_camera":False,
            })
        if len(matches)>96:
            raise ValueError("Too many native CYcc provider matches")
        report[name]={
            "present":True,
            "ELF_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "target_symbols":matches,
            "runtime_CYcc_buffer_destructor_behavior_verified":False,
            "memorypool_GetAddr_retained_by_caller_proven":False,
        }
    return {
        "scope":"UNOFFICIAL_PRIVATE_UBI_NATIVE_SYMBOLS_ONLY",
        "provider_elfs":report,
        "live_symbol_resolution_proven":False,
        "destructor_frees_CYcc_pixel_storage_proven":False,
        "destructor_does_not_free_CYcc_pixel_storage_proven":False,
        "real_camera_firmware_patch_permitted":False,
    }
