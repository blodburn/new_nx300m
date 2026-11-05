#!/usr/bin/env python3
"""Trace callers of FW1.14/1.15 native RegisterMemoryMapListner().

Only read ELF32 ARM instructions from privately extracted, *unofficial*
firmware mirrors. A direct BL is a static code edge, not evidence of runtime
execution or of image/DMA buffer lifetime. No patch, loading or camera access.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_callgraph as graph
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_native_jpeg_abi_boundary_audit as jpeg

TARGET = "RegisterMemoryMapListner()"
MAX_ELF = 2 * 1024 * 1024
MAX_METHODS = 4000
MAX_FUNCTION = 32768
MAX_DIRECT_CALLS = 128


def direct_target_sites(edges: dict, target: str = TARGET) -> list[dict]:
    """Extract explicit same-library BL references, never infer BLX/vtable."""
    entries = edges.get("identified_callsite_evidence")
    if not isinstance(entries, list):
        raise ValueError("No bounded native ARM callsite evidence")
    if edges.get("identified_calls_truncated"):
        raise ValueError("Truncated ARM direct-call inventory")
    return [
        {"callsite": e["callsite"],
         "target_kind": e["target_kind"],
         "target_symbol": e["target_symbol"]}
        for e in entries
        if e.get("target_kind") == "local" and e.get("target_symbol") == target
    ]


def call_window(words: tuple[int, ...], start: int, site: int) -> dict:
    """Bounded ARM opcode window; caller argument provenance is not proven."""
    if (start & 3 or site & 3 or site < start or
        site >= start + 4 * len(words) or
        not words or len(words) * 4 > MAX_FUNCTION):
        raise ValueError("Invalid native register-caller ARM range")
    i = (site - start) // 4
    return {
        "site": f"0x{site:08x}",
        "preceding_arm_words": [
            {"pc": f"0x{start + 4 * j:08x}",
             "word": f"0x{words[j]:08x}"}
            for j in range(max(0, i - 12), i)
        ],
        "following_arm_words": [
            {"pc": f"0x{start + 4 * j:08x}",
             "word": f"0x{words[j]:08x}"}
            for j in range(i, min(len(words), i + 6))
        ],
        "camera_capture_event_or_thread_proven": False,
        "runtime_callback_registration_invoked": False,
    }


def inspect(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file() or
        not 1024 <= path.stat().st_size <= MAX_ELF):
        raise ValueError("Bounded private ARM photo ELF required")
    data = path.read_bytes()
    loads = elf.program_headers(path)
    symbols = sif.symbol_index(sif.arm.offline_tool(
        ["readelf", "-Ws", str(path)]))
    native = sif.select(symbols, TARGET, "FUNC")
    target_address = native["address"]
    if target_address != 0x000350d8 or native["size"] != 220:
        raise ValueError("Different native FW listener registration function")
    defined = graph.defined_symbols(path)
    if defined.get(target_address) != TARGET:
        raise ValueError("Native registration target symbol does not match")
    relocs = jpeg.relocations(sif.arm.offline_tool(
        ["readelf", "-Wr", str(path)]))
    methods = [
        (name, item) for name, item in sorted(symbols.items())
        if item["kind"] == "FUNC" and
        4 <= item["size"] <= MAX_FUNCTION and
        not item["address"] & 3 and not item["size"] & 3
    ]
    if not 1 <= len(methods) <= MAX_METHODS:
        raise ValueError("Unexpected bounded native method inventory")
    callers = []
    examined = 0
    for name, fn in methods:
        start, size = fn["address"], fn["size"]
        try:
            offset = elf.file_range_for_vaddr(loads, start, size)
        except ValueError:
            continue
        edges = graph.collect_edges(data, loads, start, size, defined, relocs)
        sites = direct_target_sites(edges)
        examined += 1
        if not sites:
            continue
        words = struct.unpack_from("<" + "I" * (size // 4), data, offset)
        for hit in sites:
            site = int(hit["callsite"], 16)
            callers.append({
                "caller": name,
                "caller_address": f"0x{start:08x}",
                "caller_bytes": size,
                **call_window(words, start, site),
                "callee": TARGET,
                "callee_address": f"0x{target_address:08x}",
                "real_camera_invocation_proven": False,
                "callback_registration_success_proven": False,
            })
            if len(callers) > MAX_DIRECT_CALLS:
                raise ValueError("Unbounded native registration callers")
    return {
        "scope": "UNOFFICIAL_FW114_ARM_DIRECT_BL_ONLY",
        "libmm_photo_sha256": hashlib.sha256(data).hexdigest(),
        "registration_target": TARGET,
        "registration_function_address": f"0x{target_address:08x}",
        "registration_function_bytes": native["size"],
        "examined_arm_function_count": examined,
        "direct_bl_callers": callers,
        "direct_bl_caller_count": len(callers),
        "memory_map_named_symbols": sorted(
            name for name in symbols if "MemoryMap" in name
        )[:60],
        "indirect_thumb_external_callers_fully_scanned": False,
        "per_shutter_callback_registration_proven": False,
        "live_callback_frequency_or_order_verified": False,
        "image_dma_ownership_or_cache_safety_verified": False,
        "firmware_flash_permitted": False,
    }


def compare_versions(fw114: Path, fw115: Path) -> dict:
    a, b = inspect(fw114), inspect(fw115)
    return {
        "fw114": a,
        "fw115": b,
        "photo_ELF_sha256_equal":
            a["libmm_photo_sha256"] == b["libmm_photo_sha256"],
        "registered_callback_owner_on_camera_proven": False,
        "firmware_flash_permitted": False,
    }
