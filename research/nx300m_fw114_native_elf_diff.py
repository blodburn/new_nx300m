#!/usr/bin/env python3
"""Host-only NX300M FW1.14/1.15 camera ELF comparison from private SLP ZIPs.

UNTRUSTED, unofficial mirror data; no code execution from firmware. Requires
explicit offline extraction dependency 'ubireader_extract_files' and readelf.
Processes only exact ZIP/BIN geometry, recreates platform UBI into a PRIVATE
temporary directory and deletes all recovered files. Never runs chroot,
mounts NAND, flashes, patches, or uploads firmware/ELFs.
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
import tempfile
import zipfile

import nx300m_slp_firmware_integrity as slp
import nx300m_fw114_function_proofs as focus
import nx300m_fw114_capture_jpeg_route as static_route
import nx300m_fw114_sif_callgraph as sif_graph
import nx300m_fw114_sif_virtual_dispatch as sif_virtual
import nx300m_fw114_jfif_r6_arg_provenance as jfif_arg
import nx300m_fw114_hal_table_plus8_audit as hal_plus8
import nx300m_fw114_photo_ycc_copy_boundary as photo_buffer
import nx300m_fw114_photo_buffer_lifetime as lifetime
import nx300m_fw114_cycc_provider_probe as cycc_provider
import nx300m_fw114_pool_slot8_writer_audit as pool_slot8
import nx300m_fw114_pool_create_caller_audit as pool_callers
import nx300m_fw114_arm_loader_abi as arm_loader
import nx300m_fw114_runtime_linkage_audit as runtime_linkage

PEB = 131072
VID = 2048
DATA = 4096
MAX_PLATFORM = 360 * 1024 * 1024
MAX_ELF = 96 * 1024 * 1024
MAX_CANDIDATES = 90
MAX_SYMBOLS = 55
WATCH = re.compile(
    r"(?:^di-camera-app$|^libmm-photo|^libsif|^libdsc|^lib.*(?:camera|capture|jpeg|exif))",
    re.I,
)
SYMBOL = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+\d+\s+(?:FUNC|NOTYPE|OBJECT)"
    r"\s+(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)",
)
SYMBOL_WATCH = re.compile(
    r"(?i)(?:CYcc|EncodeYcc|DscJfif|DscJPEG|MakerNote|"
    r"Exif|CaptureStill|CCallbackStill|CCapImage|CCapBuffer|"
    r"PictureWizard|CMmDeviceDriver|SaveExif|GetMainImage|GetAddrFromCapImage)"
)
COPY_CHUNK = 1024 * 1024


def private_dir(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Private directory missing or symlink")
    if root.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError("Private directory has group/world write permission")


def copy_exact(source, target, size: int) -> str:
    remain = size
    digest = hashlib.sha256()
    while remain > 0:
        piece = source.read(min(COPY_CHUNK, remain))
        if not piece:
            raise ValueError("Truncated firmware segment")
        target.write(piece)
        digest.update(piece)
        remain -= len(piece)
    return digest.hexdigest()


def split_platform(archive: Path, tmp: Path, version: str) -> tuple[Path, dict]:
    """Integrity-check SLP then stream partition #4 without unpacking other files."""
    evidence = slp.inspect(archive, expected_version=version)
    entry = evidence["segments"][4]
    if not 0 < entry["length"] <= MAX_PLATFORM:
        raise ValueError("Oversized platform UBI")
    out = tmp / ("platform_" + version.replace(".", "") + ".ubi")
    if archive.suffix.lower() != ".zip":
        raise ValueError("Expected pinned ZIP containing one BIN")
    with zipfile.ZipFile(archive, "r") as z:
        members = [x for x in z.infolist() if x.filename.lower().endswith(".bin")]
        if len(members) != 1:
            raise ValueError("ZIP has an unexpected firmware member count")
        with z.open(members[0], "r") as reader:
            ignore = entry["offset"]
            while ignore:
                piece = reader.read(min(COPY_CHUNK, ignore))
                if not piece:
                    raise ValueError("Firmware truncated before platform partition")
                ignore -= len(piece)
            with out.open("xb") as dest:
                os.chmod(out, 0o600)
                digest = copy_exact(reader, dest, entry["length"])
            if digest != entry["sha256"]:
                raise ValueError("Extracted platform SHA differs from SLP verifier")
    return out, {
        "source": archive.name, "internal_fw_version": version,
        "platform_bytes": entry["length"], "platform_sha256": digest,
        "source_is_manufacturer_authenticated": False,
    }


def inspect_ubi_headers(platform: Path) -> dict:
    size = platform.stat().st_size
    if size < 2 * PEB or size % PEB:
        raise ValueError("Platform image is not aligned to known NX300M NAND PEB")
    count = size // PEB
    indices = sorted(i for i in set((0, 1, 2, min(33, count-1),
                                   count // 2, count-1)) if i < count)
    headers = []
    with platform.open("rb") as f:
        for index in indices:
            f.seek(index * PEB)
            h = f.read(64)
            if len(h) != 64:
                raise ValueError("UBI EC header truncated")
            if h[:4] == b"\xff" * 4:
                headers.append({"peb": index, "status": "empty"})
                continue
            if h[:4] != b"UBI#" or h[4] != 1:
                raise ValueError("Missing UBI EC magic/version at sampled PEB")
            vid, data = struct.unpack_from(">II", h, 16)
            if vid != VID or data != DATA:
                raise ValueError("Unexpected UBI VID/data offset")
            headers.append({
                "peb": index, "status": "ubi_ec_v1",
                "vid_header_offset": vid, "data_offset": data,
            })
    if sum(x["status"] == "ubi_ec_v1" for x in headers) < 2:
        raise ValueError("Insufficient UBI sample evidence")
    return {
        "peb_bytes": PEB, "peb_count": count, "sampled_headers": headers,
        "all_peb_crc_verified": False,
    }


def run_reader(executable: str, platform: Path, output: Path) -> None:
    output.mkdir(mode=0o700)
    cmd = [executable, "-p", str(PEB), "-o", str(output), str(platform)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=540,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("UBI reader unavailable or extraction timed out") from exc
    if result.returncode:
        raise ValueError("UBI reader extraction failed (see CI step, no guessed files)")
    # Never print untrusted filesystem contents or names in raw tool logs.


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(COPY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspected_candidates(root: Path) -> dict:
    candidates = []
    traversed = 0
    for item in root.rglob("*"):
        traversed += 1
        if traversed > 60000:
            raise ValueError("Extracted filesystem too large for bounded inspection")
        if item.is_symlink() or not item.is_file() or (
            not WATCH.search(item.name)
        ):
            continue
        size = item.stat().st_size
        if not 52 <= size <= MAX_ELF:
            continue
        with item.open("rb") as f:
            header = f.read(52)
        if header[:4] != b"\x7fELF":
            continue
        candidates.append((item, header))
        if len(candidates) > MAX_CANDIDATES:
            raise ValueError("Too many candidate camera ELFs")
    if not candidates:
        raise ValueError("No camera-related ELF found after UBI extraction")
    results = {}
    for file, h in sorted(candidates, key=lambda x: str(x[0])):
        if h[4] != 1 or h[5] != 1 or struct.unpack_from("<H", h, 18)[0] != 40:
            raise ValueError("Non-ARM32 little-endian camera ELF candidate")
        eabi = struct.unpack_from("<I", h, 36)[0] >> 24
        if eabi not in (0, 5):
            raise ValueError("Unexpected ARM EABI version")
        name = file.name
        if name in results:
            raise ValueError("Ambiguous same-name native library versions")
        symbols = []
        try:
            output = subprocess.run(
                ["readelf", "-W", "--dyn-syms", str(file)],
                capture_output=True, text=True, timeout=28, check=False,
            )
            if output.returncode:
                raise ValueError("Cannot read camera ELF dynamic symbol table")
            if len(output.stdout) > 16_000_000:
                raise ValueError("ELF symbol table exceeds bounded output")
            parsed = []
            for line in output.stdout.splitlines():
                match = SYMBOL.match(line)
                if match and SYMBOL_WATCH.search(match.group(3)):
                    parsed.append((match.group(3), match.group(1), match.group(2)))
            if parsed:
                demangle = subprocess.run(
                    ["c++filt"], input="\n".join(x[0] for x in parsed)+"\n",
                    capture_output=True, text=True, timeout=28, check=False,
                )
                if demangle.returncode:
                    raise ValueError("Demangler failed")
                names = demangle.stdout.splitlines()
                if len(names) != len(parsed):
                    raise ValueError("Incomplete symbol demangling")
                for (raw, address, index), decoded in zip(parsed, names):
                    if SYMBOL_WATCH.search(decoded):
                        if len(symbols) < MAX_SYMBOLS:
                            symbols.append({
                                "symbol": decoded[:180],
                                "value": "0x" + address,
                                "imported": index == "UND",
                            })
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise ValueError("ELF static metadata command unavailable") from exc
        results[name] = {
            "bytes": file.stat().st_size,
            "sha256": sha(file),
            "e_machine": 40,
            "arm_eabi_version": eabi,
            "native_symbol_samples": symbols,
            "sample_count": len(symbols),
        }
        if name in ("libsif.so", "libmm-photo.so"):
            results[name]["focused_function_proof"] = focus.inspect(
                file, include_sampling=name=="libsif.so")
        if name in ("libsif.so", "libmm-photo.so",
                    "libcapture-fw-slpcam-nx300.so"):
            results[name]["arm_loader_abi"] = arm_loader.inspect_elf(file)
    return results


def select_route_elves(root: Path) -> dict[str,Path]:
    """Require a unique, regular, non-symlink ELF for each native route node."""
    found: dict[str,Path] = {}
    targets = {static_route.CAPTURE,static_route.PHOTO,static_route.SIF}
    for p in root.rglob("*"):
        if p.name not in targets:
            continue
        if p.is_symlink() or not p.is_file() or p.name in found:
            raise ValueError("Ambiguous or symlinked native route file: "+p.name)
        found[p.name]=p
    if set(found)!=targets:
        raise ValueError("Missing required native capture/photo/SIF route ELF")
    return found


def compare_inventory(a: dict, b: dict) -> dict:
    names = sorted(set(a) & set(b))
    by_file = []
    for name in names:
        v, w = a[name], b[name]
        left = {(s["symbol"], s["imported"]): s["value"]
                for s in v["native_symbol_samples"]}
        right = {(s["symbol"], s["imported"]): s["value"]
                 for s in w["native_symbol_samples"]}
        common = sorted(set(left) & set(right))
        entry = {
            "library": name, "fw114_sha256": v["sha256"],
            "fw115_sha256": w["sha256"],
            "file_identical": v["sha256"] == w["sha256"],
            "fw114_bytes": v["bytes"], "fw115_bytes": w["bytes"],
            "common_native_symbol_sample_count": len(common),
            "sampled_symbol_value_changes": [{
                "symbol": s[0], "imported": s[1],
                "fw114": left[s], "fw115": right[s],
            } for s in common if left[s] != right[s]][:30],
        }
        if "arm_loader_abi" in v and "arm_loader_abi" in w:
            entry["fw114_arm_loader_abi"] = v["arm_loader_abi"]
            entry["fw115_arm_loader_abi"] = w["arm_loader_abi"]
            entry["static_arm_loader_abi_comparison"] = arm_loader.compare_abi(
                v["arm_loader_abi"], w["arm_loader_abi"])
        if "focused_function_proof" in v and "focused_function_proof" in w:
            entry["focused_native_function_body_comparison"] = focus.compare(
                v["focused_function_proof"], w["focused_function_proof"])
            if name == "libsif.so":
                entry["firmware114_old_115_sof_opcode_signature"] = {
                    "matches": v["focused_function_proof"][
                        "old_115_jpeg_sof_static_signature_all_match"],
                    "compared_opcode_words": v["focused_function_proof"][
                        "old_115_jpeg_sof_signature_points"],
                    "fw115_reference_matches": w["focused_function_proof"][
                        "old_115_jpeg_sof_static_signature_all_match"],
                    "camera_input_abi_verified": False,
                }
        by_file.append(entry)
    if not names:
        raise ValueError("No matching camera ELF basenames in the two images")
    return {
        "same_named_native_elf_count": len(names),
        "identical_native_elf_count": sum(x["file_identical"] for x in by_file),
        "changed_native_elf_count": sum(not x["file_identical"] for x in by_file),
        "compared_native_elfs": by_file,
        "model_and_native_camera_abi_verified": False,
        "firmware_offsets_reusable": False,
        "physical_camera_firmware_safe": False,
    }


def analyze(archives: dict[str, Path], private_root: Path,
            *, reader: str = "ubireader_extract_files") -> dict:
    private_dir(private_root)
    evidence = {}
    with tempfile.TemporaryDirectory(prefix="nx300m_fw_elf_", dir=private_root) as t:
        private = Path(t)
        inventories = {}
        route_paths = {}
        for version in ("1.14", "1.15"):
            source = archives[version]
            if source.is_symlink() or not source.is_file():
                raise ValueError("Missing private verified firmware ZIP")
            platform, s = split_platform(source, private, version)
            s["ubi"] = inspect_ubi_headers(platform)
            root = private / ("root_" + version.replace(".", ""))
            run_reader(reader, platform, root)
            s["native_elfs"] = inspected_candidates(root)
            s["cycc_ownership_provider_symbols"] = cycc_provider.inspect(root)
            s["offline_runtime_linkage"] = runtime_linkage.audit(root)
            route_paths[version] = select_route_elves(root)
            inventories[version] = s["native_elfs"]
            evidence[version] = s
        result = compare_inventory(inventories["1.14"], inventories["1.15"])
        runtime_delta = runtime_linkage.compare_report_114_115(
            evidence["1.14"]["offline_runtime_linkage"],
            evidence["1.15"]["offline_runtime_linkage"])
        route = static_route.compare_versions(
            route_paths["1.14"],route_paths["1.15"],inventories)
        sif_calls = sif_graph.compare_versions(
            route_paths["1.14"][static_route.SIF],
            route_paths["1.15"][static_route.SIF])
        sif_virtual_dispatch = sif_virtual.compare_versions(
            route_paths["1.14"][static_route.SIF],
            route_paths["1.15"][static_route.SIF])
        jfif_r6_provenance = jfif_arg.compare_versions(
            route_paths["1.14"][static_route.SIF],
            route_paths["1.15"][static_route.SIF])
        hal_producer = hal_plus8.compare_versions(
            route_paths["1.14"][static_route.SIF],
            route_paths["1.15"][static_route.SIF])
        ycc_copy_boundary = photo_buffer.compare_versions(
            route_paths["1.14"][static_route.PHOTO],
            route_paths["1.15"][static_route.PHOTO])
        memory_lifetime = lifetime.compare_versions(
            route_paths["1.14"][static_route.PHOTO],
            route_paths["1.15"][static_route.PHOTO])
        pool_writers = pool_slot8.compare_versions(
            route_paths["1.14"][static_route.PHOTO],
            route_paths["1.15"][static_route.PHOTO])
        pool_origins = pool_callers.compare_versions(
            route_paths["1.14"][static_route.PHOTO],
            route_paths["1.15"][static_route.PHOTO])
        pool_destructor_proof = {
            version: cycc_provider.proof_mode2_pool_and_trivial_cycc_destructor(
                evidence[version]["cycc_ownership_provider_symbols"],
                memory_lifetime["fw"+version.replace(".","")])
            for version in ("1.14","1.15")
        }
        return {
            "scope": "UNOFFICIAL_MIRROR_OFFLINE_HOST_ONLY",
            "source_chain_of_custody_confirmed": False,
            "fw114": evidence["1.14"],
            "fw115": evidence["1.15"],
            "comparison": result,
            "runtime_loader_libc_static_comparison":runtime_delta,
            "capture_to_jpeg_static_route": route,
            "version_specific_sif_jpeg_exif_callgraph": sif_calls,
            "version_specific_sif_virtual_dispatch": sif_virtual_dispatch,
            "jfif_encode_r6_argument_provenance": jfif_r6_provenance,
            "hal_table_plus8_initialization_witness":hal_producer,
            "fw114_photo_ycc_copy_boundary":ycc_copy_boundary,
            "fw114_photo_buffer_lifetime_branches":memory_lifetime,
            "fw114_pool_slot8_writer_inventory":pool_writers,
            "fw114_pool_creation_callers":pool_origins,
            "cycc_pool_destructor_native_proof":pool_destructor_proof,
            "camera_flash_permitted": False,
            "camera_isp_buffer_contract_verified": False,
            "camera_recovery_procedure_verified": False,
            "note": "Only ELF file hashes and limited dynamic symbols. "
                    "No live firmware ABI, DMA pointer, crop, or recovery proof.",
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-dir", type=Path, required=True)
    p.add_argument("--fw114", type=Path, required=True)
    p.add_argument("--fw115", type=Path, required=True)
    p.add_argument("--summary", type=Path)
    args = p.parse_args(argv)
    try:
        r = analyze({"1.14": args.fw114, "1.15": args.fw115}, args.private_dir)
        print("NX300M_NATIVE_FW_DIFF_JSON " + json.dumps(
            r, ensure_ascii=False, sort_keys=True))
        if args.summary:
            compared = r["comparison"]
            with args.summary.open("a", encoding="utf-8") as f:
                f.write("\n### FW1.14 vs FW1.15 actual camera ELF static comparison\n")
                f.write("UNOFFICIAL archive, NOT live ABI or flashing approval.\n\n")
                f.write("| Camera ELF | FW1.14 bytes | FW1.15 bytes | Same binary | Sampled changed symbol values |\n")
                f.write("|---|---:|---:|---|---:|\n")
                for x in compared["compared_native_elfs"]:
                    f.write(f'| {x["library"]} | {x["fw114_bytes"]:,} |'
                            f' {x["fw115_bytes"]:,} | {x["file_identical"]} |'
                            f' {len(x["sampled_symbol_value_changes"])} |\n')
                route = r["capture_to_jpeg_static_route"]
                f.write("\n### Capture → EncodeYcc → JPEG/EXIF static callsite proof\n")
                f.write("| Version | Mode-7 still calls | Photo JPEG edges | "
                        "SIF EncodeYCC symbol import/export |\n")
                f.write("|---|---:|---:|---|\n")
                for version in ("1.14","1.15"):
                    proof = route["fw"+version.replace(".","")]
                    f.write(f'| {version} | {proof["capture_recipe_calls_verified"]}'
                            f' | {proof["photo_encodeycc_edges_verified"]}'
                            f' | {proof["photo_to_sif_encodeycc_link"]["photolib_plt_import_sif_export_mangled_equal"]} |\n')
                f.write("\n### ARM EABI / float ABI / needed libs (read-only)\n")
                f.write("| Native ELF | EABI | FW1.14 float | FW1.15 float | "
                        "ABI differences |\n")
                f.write("|---|---:|---|---|---|\n")
                for x in compared["compared_native_elfs"]:
                    if "static_arm_loader_abi_comparison" not in x:
                        continue
                    a,b=x["fw114_arm_loader_abi"],x["fw115_arm_loader_abi"]
                    diff=x["static_arm_loader_abi_comparison"]
                    f.write(f'| {x["library"]} | {a["eabi"]}'
                            f' | {a["float_abi_eflags"]}/{a["float_abi_attributes"]}'
                            f' | {b["float_abi_eflags"]}/{b["float_abi_attributes"]}'
                            f' | {",".join(diff["different_static_abi_fields"]) or "none"} |\n')
                f.write("\nGNU/Linux ARM EABI test binary's glibc and PT_INTERP "
                        "do not establish NX300M Tizen runtime compatibility.\n")
                runtime_info = r["runtime_loader_libc_static_comparison"]
                f.write("\n### FW1.14 target dynamic loader / libc evidence\n")
                f.write("| Runtime ELF name | Both present | Exact SHA match | "
                        "FW1.14 max defined GLIBC | FW1.15 max defined GLIBC |\n")
                f.write("|---|---|---|---|---|\n")
                for x in runtime_info["static_libc_and_loader_file_deltas"]:
                    f.write(f'| {x["name"]} | {x["both_present"]} | '
                            f'{x["sha256_equal"]} | '
                            f'{x["fw114_max_glibc_tag"] or "not recorded"} | '
                            f'{x["fw115_max_glibc_tag"] or "not recorded"} |\n')
                f.write("\nFW1.14 camera application static PT_INTERP: "
                        f'{runtime_info["fw114_di_camera_app_interp"] or "not discovered"}\n')
                f.write("GNU test loader/GLIBC compatibility is NOT verified.\n")
                f.write("\nNo live callback, DMA/YCC ownership, MakerNotes, "
                        "recovery or camera flash proof.\n")
                f.write("\n**Physical NX300M integration still NO-GO.**\n")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile,
            subprocess.SubprocessError) as exc:
        print("NATIVE_FW_DIFF_REJECTED: "+str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
