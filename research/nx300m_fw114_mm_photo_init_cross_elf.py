#!/usr/bin/env python3
"""Offline mm_photo_init() ARM BL/PLT callers from two NX300M firmware builds.

Only version-specific, privately extracted, unofficial ARM32 ELF files are
read. No vendor code is loaded/executed, no image pixels or firmware patches
are emitted. A static BL/PLT edge is NOT evidence of a live camera call,
successful initialization, callback frequency, or safe DMA buffer ownership.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct

import nx300m_fw114_listener_cross_elf_imports as scope
import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_sif_callgraph as graph
import nx300m_native_jpeg_abi_boundary_audit as jpeg

TARGET = "mm_photo_init()"
NATIVE_SYMBOL = "_Z13mm_photo_initv"
MAX_FUNCTIONS = 12000
MAX_FUNCTION_BYTES = 32768
MAX_DIRECT_EDGES = 100
MAX_RELOCS = 32


def exact_symbol(raw: str) -> bool:
    """Reject substring names and similarly spelled camera functions."""
    return raw.split("@", 1)[0] == NATIVE_SYMBOL


def symbol_rows(table: str) -> list[dict]:
    matches = []
    for line in table.splitlines():
        m = scope.LINE.match(line)
        if not m or not exact_symbol(m[4]):
            continue
        matches.append({
            "raw": m[4].split("@", 1)[0],
            "kind": m[1],
            "binding": m[2],
            "section": m[3],
            "undefined": m[3] == "UND",
        })
        if len(matches) > 32:
            raise ValueError("Unexpected mm_photo_init symbol count")
    return matches


def direct_edges(entries: dict) -> list[dict]:
    """Only named ARM direct BL → exact local method or PLT import."""
    if entries.get("identified_calls_truncated"):
        raise ValueError("Truncated native ARM call inventory")
    candidates = entries.get("identified_callsite_evidence")
    if not isinstance(candidates, list):
        raise ValueError("Invalid native caller evidence")
    matches = []
    for candidate in candidates:
        local = (candidate.get("target_kind") == "local" and
                 candidate.get("target_symbol") == TARGET)
        imported = (candidate.get("target_kind") == "import" and
                    candidate.get("target_symbol") == NATIVE_SYMBOL)
        if local or imported:
            matches.append({
                "callsite": candidate["callsite"],
                "target_symbol": candidate["target_symbol"],
                "edge_class": ("ARM_BL_LOCAL" if local else
                               "ARM_BL_PLT_IMPORT"),
                "runtime_binding_verified": False,
            })
    return matches


def method_inventory(table: str) -> list[tuple[int, int]]:
    """Unique bounded file-backed ARM FUNC symbols; avoid alias duplication."""
    methods = set()
    for line in table.splitlines():
        m = sif.SYMBOL.match(line)
        if not m or m[3] != "FUNC" or m[4] == "UND":
            continue
        start, size = int(m[1], 16), int(m[2])
        if (start & 3) or (size & 3) or not 4 <= size <= MAX_FUNCTION_BYTES:
            continue
        methods.add((start, size))
        if len(methods) > MAX_FUNCTIONS:
            raise ValueError("Native mm_photo_init candidate module too large")
    return sorted(methods)


def inspect_one(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > scope.MAX_ELF:
        raise ValueError("Invalid selected firmware ARM ELF")
    table = sif.arm.offline_tool(["readelf", "-Ws", str(path)])
    rows = symbol_rows(table)
    rt = sif.arm.offline_tool(["readelf", "-Wr", str(path)])
    symbol_relocations = sif.relocation_symbol_targets(rt)
    refs = [
        {"slot": f"0x{address:08x}", "type": item["relocation_type"],
         "raw": item["mangled_symbol"]}
        for address, item in sorted(symbol_relocations.items())
        if exact_symbol(item["mangled_symbol"])
    ]
    if len(refs) > MAX_RELOCS:
        raise ValueError("Unexpected number of mm_photo_init relocations")
    plt = [x for x in refs if x["type"] == "R_ARM_JUMP_SLOT"]
    do_scan = bool(rows or refs)
    callsites = []
    examined = 0
    if do_scan:
        data = path.read_bytes()
        segments = elf.program_headers(path)
        defined = graph.defined_symbols(path)
        native_imports = jpeg.relocations(rt) if plt else {}
        # An imported PLT relocation alone cannot establish the executable
        # callsite. Resolve the actual ARM direct BL for each method.
        for address, size in method_inventory(table):
            try:
                offset = elf.file_range_for_vaddr(segments, address, size)
            except ValueError:
                continue
            if offset + size > len(data):
                raise ValueError("Truncated file-backed native ARM function")
            links = graph.collect_edges(
                data, segments, address, size, defined, native_imports
            )
            examined += 1
            for edge in direct_edges(links):
                callsites.append({
                    "caller": defined.get(address, "UNKNOWN_DEFINED_FUNC"),
                    "caller_address": f"0x{address:08x}",
                    "caller_bytes": size,
                    **edge,
                    "runtime_mm_photo_init_invoked": False,
                })
                if len(callsites) > MAX_DIRECT_EDGES:
                    raise ValueError("Unbounded mm_photo_init ARM callers")
    return {
        "module": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "exact_native_symbol_rows": rows,
        "exact_relocations": refs,
        "jump_slot_count": len(plt),
        "examined_arm_methods": examined,
        "arm_direct_call_candidates": callsites,
        "camera_boot_or_capture_execution_proven": False,
        "on_camera_dynamic_linker_binding_proven": False,
        "callback_or_pixel_dma_lifetime_verified": False,
    }


def inspect(root: Path) -> dict:
    modules = scope.select_paths(root)
    evidence = {name: inspect_one(path) for name, path in
                sorted(modules.items())}
    refs = [name for name, item in evidence.items() if (
        item["exact_native_symbol_rows"] or
        item["exact_relocations"] or
        item["arm_direct_call_candidates"]
    )]
    return {
        "scope": "UNOFFICIAL_FW_ARM_STATIC_MM_PHOTO_INIT_LINKS",
        "selected_modules": sorted(evidence),
        "mm_photo_init_related_modules": refs,
        "modules": evidence,
        "off_camera_static_analysis_only": True,
        "possible_dlsym_indirect_thumb_or_other_ELF_paths_complete": False,
        "on_camera_init_frequency_proven": False,
        "on_camera_dma_ownership_proven": False,
        "firmware_install_or_flash_permitted": False,
    }


def compare_versions(fw114_root: Path, fw115_root: Path) -> dict:
    a, b = inspect(fw114_root), inspect(fw115_root)
    return {
        "fw114": a,
        "fw115": b,
        "native_target": TARGET,
        "native_mangled_symbol": NATIVE_SYMBOL,
        "both_have_photo_library":
            "libmm-photo.so" in a["modules"] and
            "libmm-photo.so" in b["modules"],
        "camera_runtime_init_sequence_proven": False,
        "flash_permitted": False,
    }
