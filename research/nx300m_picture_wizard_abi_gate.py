#!/usr/bin/env python3
"""Read-only NX300M Picture Wizard symbol/body fingerprint comparison.

Builds evidence from an existing extracted ELF32 ARM shared library, and
optionally compares it against another independently authenticated version.
NEVER executes ELF code, modifies firmware, publishes vendor bytes, grants
camera execution permission, or approves firmware patching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

MAX_ELF_SIZE = 128 * 1024 * 1024
MAX_SYMBOL_BODY = 4 * 1024 * 1024
TARGETS = (
    "CProcessParameter::GetPictureWizardMode()",
    "CProcessParameter::GetPictureWizardParameter(CProcessParameter::T_PWPARAM&)",
    "CProcessParameter::updatePictureWizardBracket()",
    "CCapCmdIf::setPictureWizardBracket(int, int, int)",
)
SYMBOL_LINE = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+"
    r"(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)

def run(command: list[str], *, stdin: str | None = None) -> str:
    try:
        p = subprocess.run(command, input=stdin, text=True,
                           capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError("Required read-only ELF tool unavailable") from e
    if p.returncode or len(p.stdout) > 30_000_000:
        raise ValueError("Failed ELF metadata read")
    return p.stdout

def headers(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ELF_SIZE:
        raise ValueError("Expected local regular ELF file under size limit")
    with path.open("rb") as f:
        hdr = f.read(64)
    if len(hdr) < 52 or hdr[:4] != b"\x7fELF" or hdr[4] not in (1, 2):
        raise ValueError("Not ELF32 or ELF64")
    if hdr[5] not in (1, 2):
        raise ValueError("Unsupported ELF byte order")
    end = "<" if hdr[5] == 1 else ">"
    cls = hdr[4]
    etype, machine = struct.unpack_from(end + "HH", hdr, 16)
    flags = struct.unpack_from(end + "I", hdr, 36 if cls == 1 else 48)[0]
    phoff = struct.unpack_from(end + ("I" if cls == 1 else "Q"),
                               hdr, 28 if cls == 1 else 32)[0]
    entsz, nph = struct.unpack_from(end + "HH", hdr, 42 if cls == 1 else 54)
    if etype not in (2, 3) or nph > 300 or entsz < (32 if cls == 1 else 56):
        raise ValueError("Unexpected ELF header or program headers")
    if phoff + entsz*nph > path.stat().st_size:
        raise ValueError("Truncated program header table")
    loads = []
    with path.open("rb") as f:
        f.seek(phoff)
        for _ in range(nph):
            raw = f.read(entsz)
            if cls == 1:
                kind,off,vaddr,_,filesz,memsz,_,_ = struct.unpack_from(end+"IIIIIIII",raw)
            else:
                kind,_,off,vaddr,_,filesz,memsz,_ = struct.unpack_from(end+"IIQQQQQQ",raw)
            if kind == 1:
                if off+filesz > path.stat().st_size or filesz > memsz:
                    raise ValueError("Invalid load segment")
                loads.append((vaddr,filesz,off))
    if not loads:
        raise ValueError("No readable ELF load segments")
    return {"elf_class": 32 if cls == 1 else 64,
            "endianness": "little" if hdr[5] == 1 else "big",
            "machine": machine, "eabi_version": flags >> 24 if machine==40 else None,
            "arm_eabi5_candidate": cls==1 and hdr[5]==1 and machine==40 and flags>>24==5,
            "segments": loads}

def fingerprints(path: Path, *, allow_non_arm: bool = False) -> dict:
    elf = headers(path)
    if not allow_non_arm and not elf["arm_eabi5_candidate"]:
        raise ValueError("NX300M target requires ELF32 little-endian ARM EABI5")
    raw = run(["readelf","-W","--dyn-syms",str(path)])
    funcs = {}
    for ln in raw.splitlines():
        match = SYMBOL_LINE.match(ln)
        if not match or match.group(3) == "UND":
            continue
        addr = int(match.group(1),16)
        nbytes = int(match.group(2))
        name = match.group(4).split("@")[0]
        if nbytes == 0 or nbytes > MAX_SYMBOL_BODY:
            continue
        funcs[name]=(addr,nbytes)
    all_names = list(funcs)
    demangled = run(["c++filt"], stdin="\n".join(all_names)+"\n").splitlines() if all_names else []
    picked = {}
    with path.open("rb") as f:
        for name, dem in zip(all_names, demangled):
            if dem not in TARGETS or dem in picked:
                continue
            addr,size=funcs[name]
            # ARM's Thumb entrypoint may have bit0 set; this is ELF metadata
            # normalization only. No function is called or patched.
            vaddr=addr&~1 if elf["machine"]==40 else addr
            for seg_base,seg_len,file_off in elf["segments"]:
                if seg_base<=vaddr and vaddr+size<=seg_base+seg_len:
                    f.seek(file_off+vaddr-seg_base)
                    content=f.read(size)
                    if len(content)!=size:
                        raise ValueError("Truncated mapped function bytes")
                    picked[dem]={"symbol":name, "virtual_address_hex":hex(addr),
                                 "size":size, "code_sha256":hashlib.sha256(content).hexdigest()}
                    break
            else:
                raise ValueError("Function symbol not contained within file-backed LOAD")
    with path.open("rb") as fp:
        digest=hashlib.sha256()
        for chunk in iter(lambda:fp.read(1048576),b""):
            digest.update(chunk)
    return {
        "file_basename":path.name,
        "elf_sha256":digest.hexdigest(),
        "elf_class":elf["elf_class"],
        "endianness":elf["endianness"],
        "machine":elf["machine"],
        "arm_eabi5_candidate":elf["arm_eabi5_candidate"],
        "functions":{name:picked.get(name) for name in TARGETS},
        "found_count":sum(1 for name in TARGETS if name in picked),
        "required_count":len(TARGETS),
    }

def compare(reference: dict,candidate: dict) -> dict:
    cases={}
    for name in TARGETS:
        a=reference["functions"][name]
        b=candidate["functions"][name]
        if a is None or b is None:
            outcome="NOT_FOUND_IN_BOTH" if a is None and b is None else "MISSING"
        elif a["code_sha256"]==b["code_sha256"] and a["size"]==b["size"]:
            outcome="BODY_BYTES_IDENTICAL"
        else:
            outcome="BODY_BYTES_DIFFER"
        cases[name]=outcome
    all_match=all(x=="BODY_BYTES_IDENTICAL" for x in cases.values())
    return {
        "results":cases,
        "same_elf_sha256":reference["elf_sha256"]==candidate["elf_sha256"],
        "all_four_function_bodies_identical":all_match,
        "camera_114_authenticity_established_by_tool":False,
        "camera_114_loader_abi_verified":False,
        "safe_to_reuse_reference_addresses":False,
        "safe_to_flash_or_hook":False,
        "notice":"A byte-identical function alone NEVER validates call sites, relocations, data layout, version authenticity or safe device installation.",
    }

def main(argv: list[str] | None = None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-lib",type=Path,required=True)
    ap.add_argument("--candidate-lib",type=Path)
    ap.add_argument("--allow-host-fixtures",action="store_true",
                    help=argparse.SUPPRESS)
    args=ap.parse_args(argv)
    try:
        a=fingerprints(args.reference_lib,allow_non_arm=args.allow_host_fixtures)
        result={"reference":a,"candidate":None,"comparison":None,
                "reference_firmware_version_verified":False,
                "candidate_firmware_114_version_verified":False,
                "device_patching_authorized":False}
        if args.candidate_lib:
            b=fingerprints(args.candidate_lib,allow_non_arm=args.allow_host_fixtures)
            result["candidate"]=b
            result["comparison"]=compare(a,b)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if a["found_count"]!=4: return 3
        if args.candidate_lib and result["candidate"]["found_count"]!=4: return 3
        if args.candidate_lib and not result["comparison"]["all_four_function_bodies_identical"]:
            return 3
        return 0
    except (OSError,ValueError) as exc:
        print("ABI_AUDIT_REJECTED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
