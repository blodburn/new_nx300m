#!/usr/bin/env python3
"""Read-only FW1.14/1.15 cross-ELF RegisterMemoryMapListner references.

Only inspect selected ARM32 ELF metadata from a private offline UBI extract.
An undefined dynamic symbol or relocation is NOT proof of execution,
registration, memory ownership, DMA safety or physical-camera compatibility.
Never execute, patch, upload, or flash firmware.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat

import nx300m_fw114_sif_virtual_dispatch as sif

TARGET = "RegisterMemoryMapListner()"
NEEDLE = "RegisterMemoryMapListner"
SELECTED = frozenset((
    "di-camera-app",
    "libmm-photo.so",
    "libmm-type.so",
    "libsif.so",
    "libdsc.so",
    "libipcs.so",
    "libsysmmap.so",
    "libcapture-fw-slpcam.so",
    "libcapture-fw-slpcam-nx300.so",
))
MAX_FILES = 60000
MAX_TARGET_FILES = 15
MAX_ELF = 64 * 1024 * 1024
MAX_MATCHES = 40
LINE = re.compile(
    r"^\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+"
    r"(FUNC|NOTYPE|OBJECT)\s+(GLOBAL|WEAK|LOCAL)\s+"
    r"\S+\s+(\S+)\s+(\S+)"
)


def target_symbol_spelling(symbol: str) -> bool:
    """Mangled symbol must contain the complete native method spelling."""
    return NEEDLE in symbol.split("@", 1)[0]


def symbol_candidates(readelf_text: str) -> list[dict]:
    """Read bounded, exact dynamic symbol candidates (not whole readelf)."""
    found = []
    for line in readelf_text.splitlines():
        hit = LINE.match(line)
        if not hit or not target_symbol_spelling(hit[4]):
            continue
        found.append({
            "native_symbol": hit[4].split("@", 1)[0],
            "kind": hit[1],
            "binding": hit[2],
            "section": hit[3],
            "undefined_import": hit[3] == "UND",
        })
        if len(found) > MAX_MATCHES:
            raise ValueError("Too many native listener symbol candidates")
    return found


def select_paths(root: Path) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Private extracted firmware root is missing")
    base = root.resolve(strict=True)
    found: dict[str, dict[str, Path]] = {}
    scanned = 0
    for item in root.rglob("*"):
        scanned += 1
        if scanned > MAX_FILES:
            raise ValueError("Unbounded extracted firmware filesystem")
        if item.name not in SELECTED:
            continue
        try:
            resolved = item.resolve(strict=True)
            resolved.relative_to(base)
        except (ValueError, OSError, RuntimeError) as exc:
            raise ValueError("Target ELF escapes firmware root") from exc
        if (not resolved.is_file() or
            not stat.S_ISREG(resolved.stat().st_mode) or
            not 52 <= resolved.stat().st_size <= MAX_ELF):
            raise ValueError("Invalid bounded native ELF file")
        with resolved.open("rb") as stream:
            header = stream.read(52)
        if (header[:4] != b"\x7fELF" or header[4] != 1 or
            header[5] != 1 or int.from_bytes(header[18:20], "little") != 40):
            raise ValueError("Expected ELF32 little-endian ARM binary")
        found.setdefault(item.name, {})[str(resolved)] = resolved
        if sum(map(len, found.values())) > MAX_TARGET_FILES:
            raise ValueError("Too many selected native module paths")
    output = {}
    for name, paths in found.items():
        if len(paths) != 1:
            raise ValueError("Ambiguous distinct ELF providers: " + name)
        output[name] = next(iter(paths.values()))
    if "libmm-photo.so" not in output:
        raise ValueError("Expected native photo library missing")
    return output


def analyze_single(path: Path) -> dict:
    symbols = symbol_candidates(sif.arm.offline_tool(
        ["readelf", "-Ws", str(path)]))
    relocations = sif.relocation_symbol_targets(
        sif.arm.offline_tool(["readelf", "-Wr", str(path)]))
    dynamic_reloc = [
        {"site": f"0x{site:08x}",
         "type": item["relocation_type"],
         "native_symbol": item["mangled_symbol"]}
        for site, item in sorted(relocations.items())
        if target_symbol_spelling(item["mangled_symbol"])
    ]
    if len(dynamic_reloc) > MAX_MATCHES:
        raise ValueError("Too many native registration relocations")
    names = sorted({
        x["native_symbol"] for x in symbols
    } | {
        x["native_symbol"] for x in dynamic_reloc
    })
    decoded = sif.arm.offline_tool(
        ["c++filt"], "\n".join(names) + "\n"
    ).splitlines() if names else []
    if len(decoded) != len(names):
        raise ValueError("Symbol demangling failed")
    naming = dict(zip(names, decoded))
    # Reject a similarly spelled but non-identical method to prevent
    # a misleading cross-ELF runtime linkage assertion.
    matching = {raw for raw, readable in naming.items() if readable == TARGET}
    return {
        "elf": path.name,
        "elf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "defined_or_undefined_symbols": [
            {**item, "demangled": naming[item["native_symbol"]]}
            for item in symbols if item["native_symbol"] in matching
        ],
        "native_exact_symbol_relocations": [
            {**item, "demangled": naming[item["native_symbol"]]}
            for item in dynamic_reloc if item["native_symbol"] in matching
        ],
        "module_loaded_on_live_camera_verified": False,
        "runtime_registration_invocation_proven": False,
    }


def inspect(root: Path) -> dict:
    modules = select_paths(root)
    scanned = {
        name: analyze_single(path)
        for name, path in sorted(modules.items())
    }
    refs = [
        name for name, item in scanned.items()
        if item["defined_or_undefined_symbols"] or
        item["native_exact_symbol_relocations"]
    ]
    return {
        "scope": "UNOFFICIAL_PRIVATE_UBI_SELECTED_ARM_ELF_SYMBOLS_ONLY",
        "selected_module_count": len(scanned),
        "selected_names": sorted(scanned),
        "modules": scanned,
        "modules_with_exact_registration_symbol": refs,
        "all_possible_plugin_and_dlsym_callers_scanned": False,
        "runtime_dlopen_or_callback_execution_proven": False,
        "actual_camera_dma_or_buffer_lifetime_verified": False,
        "physical_firmware_flash_permitted": False,
    }


def compare_versions(fw114_root: Path, fw115_root: Path) -> dict:
    a, b = inspect(fw114_root), inspect(fw115_root)
    return {
        "fw114": a,
        "fw115": b,
        "both_photo_libraries_scanned": (
            "libmm-photo.so" in a["modules"] and
            "libmm-photo.so" in b["modules"]
        ),
        "on_camera_memory_pool_listener_timing_verified": False,
        "firmware_flash_permitted": False,
    }
