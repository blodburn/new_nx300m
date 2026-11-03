#!/usr/bin/env python3
"""NX300M FW1.14 static Capture->Y/C->JPEG/EXIF witness (NO CAMERA I/O).

All inputs are *private*, previously SLP-verified unpacked research ELFs.
This tool reads ARM instructions, PLT relocations and ELF dynsym only. It
NEVER calls native code, patches firmware or claims runtime DMA safety.

Old modified-MFW1.1 call addresses may only be tested on FW1.14 *after*
FW1.14 and FW1.15 exact source ELFs have been hash-compared. Every
instruction and symbol is rechecked against each actual version.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_native_still_mode7_boundary_audit as still

CAPTURE="libcapture-fw-slpcam-nx300.so"
PHOTO="libmm-photo.so"
SIF="libsif.so"
EXPECTED_STILL=9
EXPECTED_JPEG=8
EXPECTED_SOF=12
MAX_DYNSYM_CHARS=8_000_000
DYN_LINE=re.compile(
    r"^\s*\d+:\s+\S+\s+\d+\s+FUNC\s+"
    r"(?:GLOBAL|WEAK)\s+\S+\s+(\S+)\s+(\S+)"
)


def exported_dynamic_symbols(readelf_output: str) -> set[str]:
    """Only defined FUNC names; never equate imported UND with an export."""
    if len(readelf_output)>MAX_DYNSYM_CHARS:
        raise ValueError("Oversized dynsym metadata")
    result=set()
    for line in readelf_output.splitlines():
        found=DYN_LINE.match(line)
        if found and found.group(1)!="UND":
            symbol=found.group(2).split("@",1)[0]
            if symbol:
                result.add(symbol)
    return result


def import_mangled_encodeycc(relocation_map: dict[int,str]) -> str:
    names=sorted(set(relocation_map.values()))
    if not names or len(names)>50000:
        raise ValueError("No bounded photo PLT relocation names")
    decoded=jpeg.arm.offline_tool(["c++filt"],"\n".join(names)+"\n").splitlines()
    if len(decoded)!=len(names):
        raise ValueError("Incomplete photo relocation demangling")
    matching=[raw for raw,name in zip(names,decoded)
              if name.startswith("DscImage::EncodeYCC(")]
    if len(matching)!=1:
        raise ValueError("Missing or ambiguous DscImage::EncodeYCC import")
    return matching[0]


def exported_binding(photo: Path, sif: Path) -> dict:
    """Prove photo's EncodeYCC relocation is exported by same-version SIF."""
    reloc=jpeg.relocations(jpeg.arm.offline_tool(
        ["readelf","-Wr",str(photo)]))
    exported=exported_dynamic_symbols(jpeg.arm.offline_tool(
        ["readelf","-W","--dyn-syms",str(sif)]))
    imported=import_mangled_encodeycc(reloc)
    if imported not in exported:
        raise ValueError("Native EncodeYCC import unresolved in same-version libsif")
    return {
        "photolib_plt_import_sif_export_mangled_equal": True,
        "resolved_native_function": "DscImage::EncodeYCC",
        "runtime_dynamic_loader_binding_proven": False,
    }


def inspect_version(paths: dict[str,Path]) -> dict:
    if set(paths)!=set((CAPTURE,PHOTO,SIF)):
        raise ValueError("Exactly capture/photo/sif static ELFs are required")
    for name,path in paths.items():
        if path.is_symlink() or not path.is_file() or path.stat().st_size>96*1024*1024:
            raise ValueError("Missing, symlink or oversized private ELF: "+name)
    capture=still.inspect(paths[CAPTURE])
    encode=jpeg.inspect(paths[PHOTO],paths[SIF])
    calls=capture["native_main_still_configuration"][
        "source_backed_callsite_identities"]
    edges=encode["callsite_to_plt_to_relocation_evidence"]
    if len(calls)!=EXPECTED_STILL or len(edges)!=EXPECTED_JPEG:
        raise ValueError("Expected camera native callsite count changed")
    if capture["native_main_still_configuration"][
        "main_image_ycc_format"]!=1 or (
        capture["native_main_still_configuration"][
            "main_image_address_mode"]!=7
    ):
        raise ValueError("Native still recipe Y/C format or address mode changed")
    target_methods=[edge["symbol"] for edge in edges]
    expected=(
        "CYcc::GetY0()", "CYcc::GetY1()", "CYcc::GetC0()",
        "CYcc::GetC1()", "CYcc::GetWidth()", "CYcc::GetHeight()",
        "CYcc::GetStride()", "DscImage::EncodeYCC("
    )
    if any(not got.startswith(want) for got,want in zip(
        target_methods,expected
    )):
        raise ValueError("Photo encoder imported method order changed")
    resolved=exported_binding(paths[PHOTO],paths[SIF])
    sample=encode["native_jpeg_parser_sof_sampling_type_evidence"]
    if sample.get("SOF_component_sampling_0x22")!="YCC type 1 (4:2:0)":
        raise ValueError("JPEG 4:2:0 sampling contract opcode witness missing")
    return {
        "evidence_class":"read_only_static_arm_bl_plt_relocation",
        "capture_recipe_calls_verified":len(calls),
        "photo_encodeycc_edges_verified":len(edges),
        "capture_ycc_format":1,
        "capture_addr_mode":7,
        "capture_mode7_y1_c1_stride_witness":True,
        "photo_to_sif_encodeycc_link":resolved,
        "jpeg_sof_sampling_420_witness":True,
        "jpg_four_to_zero_pixel_order_or_layout_proven":False,
        "live_capture_callback_invocation_proven":False,
        "live_encoder_receives_film_pixels_proven":False,
        "native_buffer_ownership_verified":False,
        "camera_install_or_flash_permitted":False,
    }


def compare_versions(
    p114: dict[str,Path],p115: dict[str,Path],
    manifests: dict[str,dict[str,dict]]
) -> dict:
    """Guard all previously-versioned addresses via exact capture/photo hash."""
    if set(manifests)!=set(("1.14","1.15")):
        raise ValueError("Both firmware manifests required")
    for version,paths in (("1.14",p114),("1.15",p115)):
        if set(paths)!=set((CAPTURE,PHOTO,SIF)):
            raise ValueError("Missing camera native ELF: "+version)
        if not set(paths).issubset(set(manifests[version])):
            raise ValueError("Route manifest names disagree with private paths")
        for name,path in paths.items():
            from nx300m_fw114_native_elf_diff import sha
            if sha(path)!=manifests[version][name]["sha256"]:
                raise ValueError("ELF SHA-256 changed after inventory: "+name)
    for name in (CAPTURE,PHOTO):
        if manifests["1.14"][name]["sha256"]!=manifests["1.15"][name]["sha256"]:
            raise ValueError("Capture/photo ELF mismatch: reuse of old callsite REJECTED")
    # Even same hashes are only *preconditions* to rerunning exact opcodes.
    reports={}
    for version,paths in (("1.14",p114),("1.15",p115)):
        reports[version]=inspect_version(paths)
    return {
        "scope":"UNOFFICIAL_MIRROR_OFFLINE_STATIC_WITNESS",
        "capture_and_photo_files_sha256_identical_between_114_and_115":True,
        "native_callsite_rechecked_on_each_version":True,
        "fw114":reports["1.14"],
        "fw115":reports["1.15"],
        "firmware_abi_equivalence_proven":False,
        "camera_isp_format_buffer_lifetime_and_dma_verified":False,
        "exif_makernote_write_compatible_verified":False,
        "physical_camera_complete_recovery_verified":False,
        "camera_firmware_flash_permitted":False,
    }
