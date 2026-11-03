#!/usr/bin/env python3
"""Read-only Samsung NX300M ARM ELF ABI / loader witness.

Inspects *actual private extracted FW1.14 ELF* and an optional ARM32
GNU/Linux test ELF. Never executes, patches, uploads or writes firmware.
An EABI match is a necessary but INSUFFICIENT condition for runtime loading.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys

MAX_ELF_BYTES = 128 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_NEEDED = 160
EABI5 = 5
ARM_MACHINE = 40
ABI_SOFT_FLAG = 0x200
ABI_HARD_FLAG = 0x400
NEEDED = re.compile(r"\(NEEDED\).*?\[([A-Za-z0-9_.+-]{1,150})\]")
SONAME = re.compile(r"\(SONAME\).*?\[([A-Za-z0-9_.+-]{1,150})\]")
INTERP = re.compile(r"Requesting program interpreter:\s*([^\]]+)\]")
ATTR = re.compile(r"^\s*(Tag_(?:CPU_arch|ABI_VFP_args|FP_arch)):\s*(.{1,140})\s*$")


def tool(command: list[str]) -> str:
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=25,
                           check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError("ELF metadata tool unavailable or timed out") from exc
    if p.returncode or len(p.stdout) > MAX_TEXT_BYTES:
        raise ValueError("ELF metadata tool failed or exceeded output cap")
    return p.stdout


def source_header(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular, non-symlink ELF file")
    st = path.stat()
    if st.st_size < 52 or st.st_size > MAX_ELF_BYTES or not stat.S_ISREG(st.st_mode):
        raise ValueError("ELF outside bounded file size")
    h = path.open("rb").read(52)
    if (h[:4] != b"\x7fELF" or h[4] != 1 or h[5] != 1 or
        struct.unpack_from("<H", h, 18)[0] != ARM_MACHINE):
        raise ValueError("Target ELF must be ARM32 little-endian")
    flags = struct.unpack_from("<I", h, 36)[0]
    version = flags >> 24
    if version != EABI5:
        raise ValueError("Target ELF not ARM EABI version 5")
    soft = bool(flags & ABI_SOFT_FLAG)
    hard = bool(flags & ABI_HARD_FLAG)
    if soft and hard:
        raise ValueError("Contradictory soft/hard ARM ABI ELF flags")
    return {
        "eabi": version,
        "e_flags_hex": f"0x{flags:08x}",
        "ei_osabi": h[7],
        "e_type": struct.unpack_from("<H", h, 16)[0],
        "float_abi_eflags": "soft" if soft else "hard" if hard else "unspecified",
    }


def inspect_elf(path: Path) -> dict:
    header = source_header(path)
    attributes = tool(["readelf", "-A", str(path)])
    dynamic = tool(["readelf", "-W", "-d", str(path)])
    program_headers = tool(["readelf", "-W", "-l", str(path)])
    tagged = {}
    for line in attributes.splitlines():
        m = ATTR.match(line)
        if m:
            if m.group(1) in tagged and tagged[m.group(1)] != m.group(2):
                raise ValueError("Conflicting ARM build attributes")
            tagged[m.group(1)] = m.group(2)
    names = NEEDED.findall(dynamic)
    if len(names) > MAX_NEEDED:
        raise ValueError("Too many dynamic library dependencies")
    sonames = SONAME.findall(dynamic)
    if len(sonames)>1:
        raise ValueError("Ambiguous ELF SONAME")
    interps=INTERP.findall(program_headers)
    if len(interps)>1 or (interps and (
        len(interps[0])>180 or not interps[0].startswith("/")
    )):
        raise ValueError("Unexpected ELF loader path")
    vfp = tagged.get("Tag_ABI_VFP_args", "not_declared")
    attr_float = "vfp_registers" if "VFP registers" in vfp else (
        "base_aapcs" if vfp != "not_declared" else "not_declared"
    )
    if (header["float_abi_eflags"] == "hard" and
        attr_float == "base_aapcs") or (
        header["float_abi_eflags"] == "soft" and
        attr_float == "vfp_registers"
    ):
        raise ValueError("Contradictory ELF float-ABI build attributes")
    # Binding to the camera loader or a copy of Samsung's C runtime is NOT
    # established, even when the CPU/ABI signatures match perfectly.
    return {
        "arm32_eabi5_little_endian": True,
        **header,
        "tag_cpu_arch": tagged.get("Tag_CPU_arch", "not_declared"),
        "tag_fp_arch": tagged.get("Tag_FP_arch", "not_declared"),
        "float_abi_attributes": attr_float,
        "needed_sonames": sorted(set(names)),
        "elf_soname": sonames[0] if sonames else None,
        "program_interpreter": interps[0] if interps else None,
        "target_sysroot_or_loader_compatibility_verified": False,
        "physical_nx300m_camera_loadability_verified": False,
        "camera_firmware_flash_permitted": False,
    }


def compare_abi(fw114: dict, fw115: dict) -> dict:
    mandatory = ("arm32_eabi5_little_endian", "e_flags_hex",
                 "ei_osabi", "float_abi_eflags", "float_abi_attributes",
                 "tag_cpu_arch", "tag_fp_arch", "program_interpreter",
                 "needed_sonames")
    if not all(fw114.get("arm32_eabi5_little_endian") is True for fw114 in (fw114,fw115)):
        raise ValueError("Invalid ARM EABI candidate in comparison")
    differing = [key for key in mandatory if fw114.get(key) != fw115.get(key)]
    return {
        "two_firmware_versions_static_arm_abi_identical": not differing,
        "different_static_abi_fields": differing,
        "requires_actual_tizen_sysroot": True,
        "runtime_loader_compatibility_verified": False,
        "on_camera_buffer_hook_safe": False,
        "firmware_flash_permitted": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", required=True, type=Path)
    p.add_argument("--compare-elf", type=Path)
    args = p.parse_args(argv)
    try:
        evidence = {"input": inspect_elf(args.elf)}
        if args.compare_elf:
            second = inspect_elf(args.compare_elf)
            evidence["reference"] = second
            evidence["static_comparison"] = compare_abi(evidence["input"],second)
        evidence["scope"] = "HOST_STATIC_ARM_EABI_NOT_REAL_CAMERA"
        print("NX300M_ARM_ABI_JSON " + json.dumps(
            evidence,sort_keys=True,ensure_ascii=False))
        return 0
    except (OSError,ValueError) as exc:
        print("NX300M_ARM_ABI_REJECTED: "+str(exc),file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
