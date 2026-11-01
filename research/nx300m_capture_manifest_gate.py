#!/usr/bin/env python3
"""Host-only, read-only Y/C420 plus RGB capture evidence preflight (NO CAMERA I/O)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MARKER = "NX300M_HOST420_EVIDENCE_V1"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_BYTES = 192 * 1024 * 1024

def refuse(message):
    raise ValueError(message)

def valid_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value) or value in (".", ".."):
        refuse("Invalid local filename")
    return value

def valid_int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        refuse("Invalid dimension, stride or file length")
    return value

def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            refuse("Duplicate JSON key")
        out[key] = value
    return out

def hash_file(root, name, length, expected):
    path = root / valid_name(name)
    if path.is_symlink():
        refuse("Symlink refused")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != length:
            refuse("Input length or type mismatch")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > length:
                refuse("Input grew while reading")
            digest.update(chunk)
        after = os.fstat(f.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in fields):
            refuse("Input changed during validation")
    if total != length or digest.hexdigest() != expected.lower():
        refuse("Input SHA-256 mismatch")
    return digest.hexdigest()

def verify(root, manifest="capture.json"):
    if root.is_symlink() or not root.is_dir():
        refuse("Bundle root must be a real directory")
    file = root / valid_name(manifest)
    if file.is_symlink():
        refuse("Manifest symlink refused")
    fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > 65536:
            refuse("Manifest must be a bounded regular file")
        data = json.loads(f.read(65537).decode("utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict) or data.get("format") != MARKER:
        refuse("Wrong evidence format")
    if data.get("camera_model") != "NX300M" or data.get("firmware_version") != "1.14":
        refuse("Wrong declared camera or firmware version")
    if data.get("same_stage_copy_declared") is not True:
        refuse("Same-stage declaration missing")
    w = valid_int(data.get("width"), 2, 10000)
    h = valid_int(data.get("height"), 2, 10000)
    if w % 2 or h % 2 or w * h > 40000000:
        refuse("Invalid 420 geometry")
    parts = data.get("planes")
    if not isinstance(parts, dict) or set(parts) != {"y", "c", "rgb"}:
        refuse("All three planes required")
    used = {manifest}
    proof = {}
    for role, rows, minimum in (("y", h, w), ("c", h // 2, w), ("rgb", h, w * 3)):
        part = parts[role]
        if not isinstance(part, dict) or set(part) != {"file", "bytes", "stride", "sha256"}:
            refuse("Invalid plane description")
        name = valid_name(part["file"])
        if name in used:
            refuse("Repeated evidence filename")
        used.add(name)
        stride = valid_int(part["stride"], minimum, 99999)
        size = valid_int(part["bytes"], 1, MAX_BYTES)
        digest = part["sha256"]
        if size != stride * rows or not isinstance(digest, str) or not SHA.fullmatch(digest):
            refuse("Plane geometry or fingerprint mismatch")
        proof[role] = {"file": name, "stride": stride, "bytes": size,
                       "sha256": hash_file(root, name, size, digest)}
    return {"integrity": "PASS", "format": MARKER, "width": w, "height": h,
            "verified_plane_hashes": proof,
            "same_stage_verified": False, "native_camera_layout_verified": False,
            "camera_abi_verified": False, "firmware_flash_safe": False,
            "note": "Manifest association is a declaration, not proof of same-stage camera acquisition"}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle-dir", required=True, type=Path)
    ap.add_argument("--manifest", default="capture.json")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(verify(args.bundle_dir, args.manifest), indent=2))
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as e:
        print("CAPTURE_REJECTED: " + str(e), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
