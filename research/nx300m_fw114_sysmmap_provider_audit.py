#!/usr/bin/env python3
"""Offline ABI audit of actual FW1.14/1.15 libsys-mmap-manager.so.

libmm-photo.so NEEDED includes libsys-mmap-manager.so, unlike the guessed
libsysmmap.so name. Resolve the library strictly within a private UBI root.
Static symbol and ARM BL/PLT evidence does NOT establish kernel mmap size,
ownership, cache fences, DMA safety, runtime executions or flash safety.
Never execute firmware, access a camera, patch binaries or upload vendor ELF.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat

import nx300m_fw114_function_proofs as arm_elf
import nx300m_fw114_arm_loader_abi as abi
import nx300m_fw114_sif_callgraph as graph
import nx300m_pw_ui_bl_call_audit as arm
import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_fw114_runtime_linkage_audit as runtime

LIBRARY = "libsys-mmap-manager.so"
CONSUMER = "libmm-photo.so"
TARGETS = (
    "sysmmap_alloc",
    "sysmmap_cached_alloc",
    "sysmmap_free",
    "sysmmap_client_callback_register",
    "sysmmap_mgr_alloc",
    "sysmmap_mgr_free",
    "sysmmap_mgr_register_callback",
    "sysmmap_client_alloc",
    "sysmmap_client_free",
    "sysmmap_segment_alloc",
    "sysmmap_segment_free",
    "sysmmap_segment_init",
    "sysmmap_segment_destroy",
    "sysmmap_osif_alloc",
    "sysmmap_osif_free",
)
MAX_PATHS = 60000
MAX_BYTES = 32 * 1024 * 1024
MAX_SYMBOL_ROWS = 40000
MAX_REFS = 48
MAX_FUNCS = 20
MAX_FUNCTION_BYTES = 32768
EXPORT = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+"
    r"(FUNC|NOTYPE)\s+(GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)


def matching_target(name: str) -> bool:
    return name.split("@", 1)[0] in TARGETS


def parse_symbol_rows(table: str) -> list[dict]:
    result = {}
    for line_no, line in enumerate(table.splitlines()):
        if line_no > MAX_SYMBOL_ROWS:
            raise ValueError("Native symbol inventory too large")
        m = EXPORT.match(line)
        if not m or not matching_target(m[6]):
            continue
        key = (m[6].split("@", 1)[0], m[5], int(m[1],16), int(m[2]))
        result[key] = {
            "symbol": key[0],
            "section": m[5],
            "address": f"0x{key[2]:08x}",
            "size": key[3],
            "binding": m[4],
            "kind": m[3],
            "is_defined": m[5] != "UND",
        }
        if len(result) > MAX_REFS:
            raise ValueError("Too many mmap ABI symbol definitions")
    return sorted(result.values(), key=lambda e:(e["symbol"],e["is_defined"],e["address"]))


def find_provider(root: Path, required_name: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid private extracted firmware root")
    base = root.resolve(strict=True)
    found={}
    examined=0
    for path in root.rglob("*"):
        examined+=1
        if examined > MAX_PATHS:
            raise ValueError("Unbounded firmware path inventory")
        if path.name != required_name:
            continue
        try:
            real=path.resolve(strict=True)
            real.relative_to(base)
        except (RuntimeError, ValueError, OSError) as exc:
            raise ValueError("ELF dependency escapes private firmware root") from exc
        if (not real.is_file() or not stat.S_ISREG(real.stat().st_mode)
            or not 52 <= real.stat().st_size <= MAX_BYTES):
            raise ValueError("Invalid selected memory manager ELF")
        abi.source_header(real)
        found[str(real)] = real
        if len(found) > 4:
            raise ValueError("Too many duplicate mmap native providers")
    if len(found) != 1:
        raise ValueError("Missing or ambiguous native "+required_name)
    return next(iter(found.values()))


def bounded_call_sites(
    path: Path, rows: list[dict]
) -> list[dict]:
    """Only statically visible ARM direct BL edges in symbol-defined funcs."""
    funcs=[x for x in rows if x["is_defined"] and x["kind"]=="FUNC"
           and 4 <= x["size"] <= MAX_FUNCTION_BYTES
           and int(x["address"],16) % 4 == 0]
    if len(funcs)>MAX_FUNCS:
        raise ValueError("Ambiguous native mmap function definitions")
    data=path.read_bytes()
    segments=arm_elf.program_headers(path)
    defined=graph.defined_symbols(path)
    relocations=jpeg.relocations(abi.tool(["readelf","-Wr",str(path)]))
    report=[]
    for entry in funcs:
        start,size=int(entry["address"],16),entry["size"]
        if size%4:
            continue
        calls=arm.scan_direct_calls(data,start,size,segments)
        if len(calls)>256:
            raise ValueError("Too many mmap function ARM BLs")
        linked=[]
        for site,target in calls:
            name=defined.get(target)
            kind="local" if name is not None else "unresolved"
            if name is None:
                try:
                    slot=jpeg.plt_got(data,segments,target)
                    name=relocations.get(slot)
                    kind="import" if name else "unresolved"
                except ValueError:
                    pass
            linked.append({
                "callsite":f"0x{site:08x}",
                "target_kind":kind,
                "target_symbol":name,
            })
        report.append({
            "function":entry["symbol"],
            "native_address":entry["address"],
            "function_size":size,
            "arm_direct_bl_edges":linked,
            "real_camera_function_invoked":False,
            "actual_kernel_mapping_length_proven":False,
        })
    return report


def inspect(root: Path) -> dict:
    photo=find_provider(root,CONSUMER)
    source=abi.inspect_elf(photo)
    needed=source["needed_sonames"]
    if LIBRARY not in needed:
        raise ValueError("Actual native photo library no longer depends on sysmmap")
    manager=find_provider(root,LIBRARY)
    meta=abi.inspect_elf(manager)
    table=abi.tool(["readelf","-Ws",str(manager)])
    rows=parse_symbol_rows(table)
    exported=sorted({r["symbol"] for r in rows if r["is_defined"]})
    imported=sorted({r["symbol"] for r in rows if not r["is_defined"]})
    edges=bounded_call_sites(manager,rows)
    return {
        "scope":"UNOFFICIAL_PRIVATE_FW_ARM_SYSMMAP_PROVIDER_METADATA",
        "provider":LIBRARY,
        "photo_needed_provider":True,
        "photo_required_library_count":len(needed),
        "provider_sha256":hashlib.sha256(manager.read_bytes()).hexdigest(),
        "provider_elf_eabi5":meta["arm32_eabi5_little_endian"],
        "provider_needed_sonames":meta["needed_sonames"],
        "mmap_exported_functions":exported,
        "mmap_undefined_symbols":imported,
        "symbol_rows":rows,
        "native_defined_function_arm_callgraph":edges,
        "all_kernel_ioctl_and_dynamic_callbacks_resolved":False,
        "camera_runtime_allocator_calls_observed":False,
        "actual_allocated_bytes_measured":False,
        "mmap_cached_uncached_coherency_proven":False,
        "camera_firmware_flash_permitted":False,
    }


def compare_versions(fw114: Path, fw115: Path) -> dict:
    a,b=inspect(fw114),inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "same_provider_sha256":a["provider_sha256"]==b["provider_sha256"],
        "same_exported_function_names":
            a["mmap_exported_functions"]==b["mmap_exported_functions"],
        "physical_camera_kernel_mapping_proven":False,
        "firmware_flash_permitted":False,
    }
