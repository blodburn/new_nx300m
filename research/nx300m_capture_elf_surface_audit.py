#!/usr/bin/env python3
"""Read-only ARM shared-library linkage/symbol audit for NX300M research.

Only static metadata are read with GNU readelf and optionally c++filt.
No vendor binaries are distributed, executed, copied, patched or flashed.
A symbol hit is NOT ABI proof, a firmware version match, or camera input access.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

MAX_FILES = 256
MAX_BYTES = 128 * 1024 * 1024
SYMBOL_LIMIT = 30_000
SELECT_LIMIT = 12
GROUPS = {
    "dial_mode_word": re.compile(r"DialMode|DIALMODE", re.I),
    "picture_wizard_word": re.compile(r"PictureWizard|Picture_Wizard|PictureWizardMode", re.I),
    "physical_key_input_word": re.compile(r"Evas.*Key|rotary|key_down|DialKey|KeyPress", re.I),
    "ycc_buffer_word": re.compile(r"CYcc::(GetY[01]|GetC[01]|VerifyBuffer|GetType)", re.I),
    "jpeg_exif_word": re.compile(r"(DscJPEG|EncodeYcc|SaveExifImage|MakerNote|JpegDone)", re.I),
    "capture_still_word": re.compile(r"(CaptureStillImage|CCallbackStillCapture|CCapStillShot)", re.I),
    "efl_userspace_word": re.compile(r"(evas_|ecore_|elm_|elementary_)", re.I),
}
NEEDED = re.compile(r"\(NEEDED\).*?\[(.*?)\]")
# -Ws --dyn-syms, where Ndx=UND means undefined imported symbol.
SYMBOL = re.compile(r"^\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+"
                    r"(?:FUNC|OBJECT|NOTYPE|TLS)\s+"
                    r"(?:GLOBAL|WEAK)\s+\S+\s+"
                    r"(\S+)\s+(\S+)")
VERSION_SUFFIX = re.compile(r"@@?.*$")

def tool(command: list[str], *, input_text: str | None = None) -> str:
    try:
        r = subprocess.run(command, input=input_text, text=True,
                           capture_output=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("required offline metadata tool unavailable or timed out") from exc
    if r.returncode:
        raise ValueError("ELF metadata read failed (non-ELF or malformed ELF)")
    if len(r.stdout) > 16_000_000:
        raise ValueError("ELF metadata too large")
    return r.stdout

def elf_candidate(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return False
    with path.open("rb") as fp:
        return fp.read(4) == b"\x7fELF"

def inspect(path: Path) -> dict:
    dynamic = tool(["readelf", "-W", "-d", str(path)])
    symbols = tool(["readelf", "-W", "--dyn-syms", str(path)])
    needed = sorted(set(NEEDED.findall(dynamic)))
    defined, imported = set(), set()
    for line in symbols.splitlines():
        m = SYMBOL.match(line)
        if not m:
            continue
        name = VERSION_SUFFIX.sub("", m.group(2))
        if name and name != "0":
            (imported if m.group(1) == "UND" else defined).add(name)
        if len(defined) + len(imported) > SYMBOL_LIMIT:
            raise ValueError("Symbol count exceeds bounded inspection limit")
    matched_mangled = sorted(name for name in defined | imported
                             if any(term.lower() in name.lower()
                                    for term in ("cycc", "dial", "jpeg", "exif",
                                                 "capture", "maker", "evas", "elm_",
                                                 "ecore", "picture", "rotary", "key")))
    # A single vectorized c++filt pass, not vendor execution.
    demangled = (tool(["c++filt"], input_text="\n".join(matched_mangled) + "\n").splitlines()
                 if matched_mangled else [])
    hits = {name: {"defined": [], "imported": []} for name in GROUPS}
    for symbol, view in zip(matched_mangled, demangled):
        bucket = "defined" if symbol in defined else "imported"
        for group, pattern in GROUPS.items():
            if pattern.search(view):
                rows = hits[group][bucket]
                if len(rows) < SELECT_LIMIT:
                    rows.append(view[:180])
    return {
        "needed": needed,
        "dynamic_defined_count": len(defined),
        "dynamic_imported_count": len(imported),
        "evidence": hits,
    }

def audit(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Root must be a local directory, not a symlink")
    paths = []
    for item in root.rglob("*"):
        if len(paths) >= MAX_FILES:
            raise ValueError("Too many candidate shared libraries")
        if item.is_file() and not item.is_symlink() and item.suffix == ".so":
            if elf_candidate(item):
                paths.append(item)
    paths.sort()
    by_name = {p.name for p in paths}
    results = []
    for path in paths:
        info = inspect(path)
        info["file"] = path.relative_to(root).as_posix()
        info["needed_present_in_extraction"] = sorted(n for n in info["needed"] if n in by_name)
        info["needed_missing_from_extraction"] = sorted(n for n in info["needed"] if n not in by_name)
        results.append(info)
    present = sum(len(x["needed_present_in_extraction"]) for x in results)
    missing = sum(len(x["needed_missing_from_extraction"]) for x in results)
    return {
        "input_kind": "offline existing extracted binaries only",
        "firmware_114_binary_identity_verified": False,
        "on_camera_symbol_execution_verified": False,
        "picture_wizard_efl_connection_verified": False,
        "shared_elf_count": len(results),
        "dependency_edges_present": present,
        "dependency_edges_missing": missing,
        "libraries": results,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = audit(args.root)
        if args.summary:
            data["libraries"] = [
                {"file": x["file"],
                 "needed_present_count": len(x["needed_present_in_extraction"]),
                 "needed_missing_count": len(x["needed_missing_from_extraction"]),
                 "symbol_categories": {
                     k: {direction: len(v) for direction, v in details.items()}
                     for k, details in x["evidence"].items()}}
                for x in data["libraries"]
            ]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0 if data["shared_elf_count"] else 2
    except (ValueError, OSError) as exc:
        print("AUDIT_REJECTED: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
