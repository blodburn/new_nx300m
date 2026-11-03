#!/usr/bin/env python3
"""Strict host validator for *untrusted*, read-only NX300M runtime text.

Parsing this report does not prove capture callback activity or ISP/DMA safety.
No device I/O, process introspection or firmware modifications occur here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

HEADER="NX300M_FW114_RUNTIME_METADATA_V1"
MAX_REPORT_BYTES=8192
MEM=("mem_total_kib","mem_available_kib","mem_free_kib")
TRISTATE=("camera_process","camera_maps_readable","camera_libmm_photo_loaded",
          "camera_libsif_loaded","camera_libcapture_fw_loaded")
BLOCKED=("firmware_114_independently_authenticated",
         "live_capture_callback_verified","live_ycc420_layout_verified",
         "native_buffer_ownership_verified","calibration_recovery_verified",
         "firmware_flash_permitted","firmware_write_performed")
EXPECTED={"probe_scope","kernel_machine",*MEM,*TRISTATE,*BLOCKED}
SAFE_MACHINE={"armv7l","armv6l","armv5tel","aarch64","x86_64","i686",
              "other","unknown"}
GOOD=re.compile(r"[a-z0-9_]+=[A-Za-z0-9_]+\Z")
NUM=re.compile(r"(?:0|[1-9][0-9]{0,9})\Z")


def inspect_text(src: str) -> dict:
    if len(src.encode("utf-8"))>MAX_REPORT_BYTES or "\r" in src or "\0" in src:
        raise ValueError("Unbounded or invalid runtime metadata")
    lines=src.splitlines()
    if not lines or lines[0]!=HEADER:
        raise ValueError("Missing fixed runtime metadata header")
    parts={}
    for line in lines[1:]:
        if not GOOD.fullmatch(line):
            raise ValueError("Unexpected runtime report syntax")
        key,value=line.split("=",1)
        if key in parts or key not in EXPECTED:
            raise ValueError("Duplicate or unexpected runtime report key")
        parts[key]=value
    if set(parts)!=EXPECTED:
        raise ValueError("Missing required fail-closed evidence keys")
    if parts["probe_scope"]!="read_only_metadata":
        raise ValueError("Not a read-only probe")
    if parts["kernel_machine"] not in SAFE_MACHINE:
        raise ValueError("Unsupported machine indicator")
    for field in MEM:
        if parts[field]!="unknown" and not NUM.fullmatch(parts[field]):
            raise ValueError("Invalid reported memory value")
    available=[int(parts[k]) for k in MEM if parts[k]!="unknown"]
    if len(available)==3 and (
        int(parts["mem_available_kib"])>int(parts["mem_total_kib"]) or
        int(parts["mem_free_kib"])>int(parts["mem_total_kib"])
    ):
        raise ValueError("Physically inconsistent memory counters")
    for field in TRISTATE:
        if parts[field] not in ("observed","not_observed"):
            raise ValueError("Not a bounded runtime observation")
    if parts["camera_process"]=="not_observed" or (
        parts["camera_maps_readable"]=="not_observed"
    ):
        if any(parts[field]=="observed" for field in TRISTATE[2:]):
            raise ValueError("Library reported loaded without observed process maps")
    for field in BLOCKED:
        if parts[field]!="no":
            raise ValueError("Unproven hardware gate was asserted true")
    return {
        "report_integrity":"PASS_FORMAT_ONLY",
        "kernel_machine":parts["kernel_machine"],
        "mem_total_kib":parts["mem_total_kib"],
        "mem_available_kib":parts["mem_available_kib"],
        "mem_free_kib":parts["mem_free_kib"],
        "camera_process":parts["camera_process"],
        "camera_maps_readable":parts["camera_maps_readable"],
        "camera_libmm_photo_loaded":parts["camera_libmm_photo_loaded"],
        "camera_libsif_loaded":parts["camera_libsif_loaded"],
        "camera_libcapture_fw_loaded":parts["camera_libcapture_fw_loaded"],
        "actual_camera_and_firmware_origin_attested":False,
        "native_capture_callback_invoked":False,
        "film_pixels_connected_to_native_encoder":False,
        "native_isp_layout_and_ownership_verified":False,
        "physical_camera_memory_budget_verified":False,
        "camera_firmware_install_permitted":False,
        "note":"Only passive OS/process metadata; no active shooting event or "
               "actual firmware fingerprint, JPEG quality or full recovery proof."
    }


def main(argv: list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report",required=True,type=Path,
                    help="private captured stdout of explicitly authorized read-only probe")
    args=ap.parse_args(argv)
    try:
        if args.report.is_symlink() or not args.report.is_file() or (
            args.report.stat().st_size>MAX_REPORT_BYTES
        ):
            raise ValueError("Missing, symlinked or oversized probe report")
        text=args.report.read_text(encoding="utf-8")
        print(json.dumps(inspect_text(text),sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError) as exc:
        print("NX300M_RUNTIME_METADATA_REJECTED: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())
