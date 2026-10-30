#!/usr/bin/env python3
"""Read-only NX300M Tizen ARM ELF ABI and firmware-identity guard.

This is an OFF-CAMERA tool. It does not enable code execution on a camera,
modify firmware, extract keys, or copy Samsung proprietary binaries.
ELF EABI compatibility does NOT prove offsets, safety or a firmware match.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ARM_MACHINE = 40
EABI5 = 5
MAX_CANDIDATES = 12000
MAX_FILE_BYTES = 536870912  # no need to load larger images into memory

def elf_info(path: Path) -> dict | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 52:
        return None
    with path.open("rb") as f:
        header = f.read(52)
    if header[:4] != b"\x7fELF":
        return None
    kind, endianness = header[4], header[5]
    if kind != 1 or endianness not in (1, 2):
        return {"status": "unsupported_elf_class_or_endianness"}
    e = "<" if endianness == 1 else ">"
    machine = struct.unpack_from(e + "H", header, 18)[0]
    flags = struct.unpack_from(e + "I", header, 36)[0]
    return {
        "status": "elf32",
        "endianness": "little" if endianness == 1 else "big",
        "machine": machine,
        "arm_eabi_version": (flags >> 24) if machine == ARM_MACHINE else None,
        "arm_eabi5_candidate": bool(
            machine == ARM_MACHINE and endianness == 1 and flags >> 24 == EABI5
        ),
    }

def inventory(root: Path) -> dict:
    if not root.is_dir():
        raise ValueError("Input must be a readable extracted directory")
    items = []
    seen = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        seen += 1
        if seen > MAX_CANDIDATES:
            raise ValueError("Too many files: narrow the offline extraction root")
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            abi = elf_info(path)
        except (OSError, PermissionError):
            continue
        if abi:
            # Relative path, no absolute local path/private file content.
            items.append({"path": path.relative_to(root).as_posix(), **abi})
    items.sort(key=lambda item: item["path"])
    signals = [
        p for p in ("etc/tizen-release", "etc/os-release", "usr/share/tizen")
        if (root / p).exists()
    ]
    arm = [x for x in items if x.get("arm_eabi5_candidate")]
    return {
        "tizen_markers_found": signals,
        "tizen_confirmed_from_elf_alone": False,
        "file_candidates_examined": seen,
        "elf_count": len(items),
        "arm32_eabi5_little_count": len(arm),
        "non_matching_elf_count": len(items)-len(arm),
        "elf_files": items,
    }

def fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def compare(root: Path, target: Path, original: dict) -> dict:
    if not target.is_dir():
        raise ValueError("Target extraction directory missing")
    base = {x["path"]: x for x in original["elf_files"]}
    match, changed = [], []
    for rel in sorted(base):
        src = root / rel
        dst = target / rel
        if dst.is_symlink() or not dst.is_file():
            continue
        if dst.stat().st_size > MAX_FILE_BYTES:
            continue
        tgt = elf_info(dst)
        if not tgt:
            continue
        if fingerprint(src) == fingerprint(dst):
            match.append(rel)
        else:
            changed.append(rel)
    return {
        "common_elf_paths": len(match)+len(changed),
        "bit_identical": match,
        "different": changed,
        "reuse_firmware_offsets_permitted": False,
        "note": ("Binary matches for named individual files only; no global "
                 "firmware or runtime ABI identity has been established. "
                 "Do not reuse function offsets across versions."),
    }

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,required=True,
                    help="Directory containing read-only, offline extracted firmware files")
    ap.add_argument("--compare-to",type=Path,
                    help="Optional separately extracted version; comparison never writes")
    ap.add_argument("--summary",action="store_true",
                    help="Omit individual file names from output")
    a = ap.parse_args(argv)
    try:
        data = inventory(a.root)
        if a.compare_to:
            data["comparison"] = compare(a.root,a.compare_to,data)
        if a.summary:
            data.pop("elf_files",None)
            if "comparison" in data:
                c = data["comparison"]
                c["bit_identical_count"] = len(c.pop("bit_identical"))
                c["different_count"] = len(c.pop("different"))
        print(json.dumps(data,ensure_ascii=False,indent=2))
        if not data["elf_count"]:
            return 2
        if a.compare_to and (
            data["comparison"]["common_elf_paths"] == 0
            or data["comparison"].get("different_count",len(data["comparison"].get("different",[])))>0
        ):
            return 3
        return 0
    except (OSError, ValueError) as e:
        print(f"INPUT_REJECTED: {e}",file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
