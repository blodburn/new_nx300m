#!/usr/bin/env python3
"""NX300M FW114 off-camera runtime linkage inventory (private UBIFS input).

Read-only ELF/filesystem metadata. It does not execute vendor code, chroot,
mount, create firmware packages, write calibration, or approve camera flashing.
Resolve only source-root-local library links. A file present does NOT imply a
matching runtime symbol version, calling convention, or safe dlopen.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import stat
import subprocess

import nx300m_fw114_arm_loader_abi as arm

MAX_FILES = 60000
MAX_LIB_CANDIDATES = 160
MAX_ELF_BYTES = 64 * 1024 * 1024
RUNTIME = ("libc.so.6", "libm.so.6", "libpthread.so.0",
           "libstdc++.so.6", "ld-linux.so.3", "ld-linux-armhf.so.3")
TARGETS = ("libc.so.6", "ld-linux.so.3", "libm.so.6")
VERSION_RE = re.compile(r"\bGLIBC_(\d+)\.(\d+)(?:\.(\d+))?\b")
SAFE_VERSION = re.compile(r"GLIBC_\d+\.\d+(?:\.\d+)?\Z")
REQUIRED_ROOT = ("libmm-photo.so", "libsif.so",
                 "libcapture-fw-slpcam-nx300.so")
OPTIONAL_EXECUTABLE = "di-camera-app"


def check_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Firmware filesystem root missing or symlinked")
    return root.resolve(strict=True)


def safe_file(root: Path, path: Path) -> Path:
    root = check_root(root)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError("Library path escapes extracted firmware root") from exc
    if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError("Resolved runtime library is not a regular file")
    if not 52 <= resolved.stat().st_size <= MAX_ELF_BYTES:
        raise ValueError("Unexpected runtime ELF size")
    return resolved


def index_libs(root: Path) -> tuple[dict[str, list[Path]], int]:
    root = check_root(root)
    index: dict[str,list[Path]] = {}
    count = 0
    for p in root.rglob("*"):
        count += 1
        if count > MAX_FILES:
            raise ValueError("Firmware extraction file-count cap exceeded")
        name = p.name
        if name in RUNTIME or name in REQUIRED_ROOT or name == OPTIONAL_EXECUTABLE:
            index.setdefault(name, []).append(p)
            if sum(len(v) for v in index.values()) > MAX_LIB_CANDIDATES:
                raise ValueError("Too many firmware runtime candidate libraries")
    return index, count


def choose(index: dict[str,list[Path]], root: Path, name: str) -> Path | None:
    candidates = index.get(name, [])
    if not candidates:
        return None
    target = {}
    for candidate in candidates:
        try:
            resolved = safe_file(root, candidate)
        except ValueError:
            # Symlink-to-missing stays a missing dependency. External links
            # or broken references must never be silently treated as success.
            raise
        target[str(resolved)] = resolved
    if len(target) != 1:
        raise ValueError("Multiple distinct runtime library candidates: " + name)
    return next(iter(target.values()))


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for piece in iter(lambda: f.read(1024*1024), b""):
            sha.update(piece)
    return sha.hexdigest()


def version_tags(s: str) -> list[str]:
    versions=set()
    for match in VERSION_RE.finditer(s):
        value=match.group()
        if SAFE_VERSION.fullmatch(value):
            versions.add(value)
    return sorted(versions,key=lambda k:tuple(map(int,k[6:].split("."))))


def inspect_versions(path: Path) -> dict:
    output = arm.tool(["readelf","-W","-V",str(path)])
    # readelf -V includes the dynamic version-definition and version-need
    # sections. Distinguish the tables to avoid treating version requirements
    # as versions provided by glibc.
    definitions,requirements,active="","",""
    for line in output.splitlines(keepends=True):
        if "Version definition section" in line:
            active="def"
        elif "Version needs section" in line:
            active="need"
        elif "Version symbols section" in line:
            active=""
        if active=="def":
            definitions+=line
        elif active=="need":
            requirements+=line
    definitions_tags=version_tags(definitions)
    return {
        "defined_glibc_versions":definitions_tags,
        "required_glibc_versions":version_tags(requirements),
        "max_defined_glibc_tag":
            definitions_tags[-1] if definitions_tags else None,
        "max_required_glibc_tag":
            version_tags(requirements)[-1]
            if version_tags(requirements) else None,
        "presence_proves_target_sysroot_is_available":False,
        "symbol_version_binding_verified":False,
    }


def audit(root: Path) -> dict:
    root=check_root(root)
    index,examined=index_libs(root)
    sources={}
    for name in RUNTIME:
        p=choose(index,root,name)
        if p is None:
            sources[name]={"present":False}
        else:
            h=arm.inspect_elf(p)
            sources[name]={
                "present":True,
                "sha256":digest(p),
                "bytes":p.stat().st_size,
                "arm32_eabi5_little_endian":h["arm32_eabi5_little_endian"],
                "tag_cpu_arch":h["tag_cpu_arch"],
                "float_abi_eflags":h["float_abi_eflags"],
                "soname":h["elf_soname"],
                "version_evidence":inspect_versions(p),
            }
    required=[]
    for name in REQUIRED_ROOT:
        p=choose(index,root,name)
        if p is None:
            raise ValueError("Camera library missing from extracted firmware: "+name)
        abi=arm.inspect_elf(p)
        required.append({
            "camera_library":name,
            "required_elf_count":len(abi["needed_sonames"]),
            "required_sonames":abi["needed_sonames"],
            # Not a full recursive linker resolution. The firmware runtime
            # can have unresolved dependencies absent from this inventory.
            "present_in_selected_system_runtime_inventory":[
                n for n in abi["needed_sonames"]
                if n in sources and sources[n]["present"]
            ],
        })
    app=choose(index,root,OPTIONAL_EXECUTABLE)
    app_header=arm.inspect_elf(app) if app is not None else None
    libc=sources["libc.so.6"]
    return {
        "scope":"OFFLINE_UNTRUSTED_EXTRACTED_FW_FILESYSTEM",
        "examined_paths":examined,
        "runtime_libraries":sources,
        "camera_dependency_roots":required,
        "camera_app_metadata":{
            "present":app is not None,
            "pt_interp_from_static_elf":
                app_header["program_interpreter"] if app_header else None,
            "arm_cpu_tag":app_header["tag_cpu_arch"] if app_header else None,
            "needed_sonames":app_header["needed_sonames"] if app_header else [],
            "actual_live_process_loader_verified":False,
        },
        "firmware_libc_discovered":libc["present"],
        "libc_max_glibc_version_static":
            libc["version_evidence"]["max_defined_glibc_tag"]
            if libc["present"] else None,
        "exact_camera_dynamic_loader_path_verified":False,
        "external_arm_gnu_executable_loader_compatible":False,
        "target_tizen_sdk_sysroot_verified":False,
        "full_dependency_closure_verified":False,
        "kernel_camera_abi_and_buffer_ownership_verified":False,
        "physical_recovery_verified":False,
        "camera_flash_permitted":False,
    }



def compare_report_114_115(a:dict,b:dict)->dict:
    left=a["runtime_libraries"]
    right=b["runtime_libraries"]
    names=sorted(set(left)&set(right))
    deltas=[]
    for name in names:
        x,y=left[name],right[name]
        deltas.append({
            "name":name,
            "both_present":x["present"] and y["present"],
            "sha256_equal":x.get("sha256")==y.get("sha256")
                if x["present"] and y["present"] else False,
            "fw114_max_glibc_tag":
                x.get("version_evidence",{}).get("max_defined_glibc_tag"),
            "fw115_max_glibc_tag":
                y.get("version_evidence",{}).get("max_defined_glibc_tag"),
        })
    return {
        "static_libc_and_loader_file_deltas":deltas,
        "fw114_static_max_defined_glibc":a["libc_max_glibc_version_static"],
        "fw115_static_max_defined_glibc":b["libc_max_glibc_version_static"],
        "fw114_di_camera_app_interp":
            a["camera_app_metadata"]["pt_interp_from_static_elf"],
        "fw115_di_camera_app_interp":
            b["camera_app_metadata"]["pt_interp_from_static_elf"],
        "gnu_linux_cross_compiler_binary_loadable_on_camera":False,
        "physical_camera_runtime_test_performed":False,
        "firmware_flash_permitted":False,
    }
