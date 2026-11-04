#!/usr/bin/env python3
"""OFFLINE host gate: SHA-256 copied Y/C/RGB evidence -> 8-model C probe.

Never obtains camera samples, executes Samsung firmware, accesses DMA,
modifies firmware or promotes a matrix guess to on-camera ABI proof.
Requires a separately built and explicitly SHA-pinned HOST probe executable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import nx300m_capture_manifest_gate as manifest

SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
MODELS = ("BT601_FULL", "BT709_FULL", "BT601_LIMITED", "BT709_LIMITED")
ORDERS = ("CbCr", "CrCb")
SAMPLE = re.compile(r"sampled_chroma_pairs=([0-9]{1,12})\Z")
INFO = re.compile(r"informative_pairs=([0-9]{1,12})\Z")
SCORE = re.compile(
    r"hypothesis=(BT601_FULL|BT709_FULL|BT601_LIMITED|BT709_LIMITED):"
    r"(CbCr|CrCb) y_mae=([0-9]{1,6}\.[0-9]{3}) "
    r"chroma_mae=([0-9]{1,6}\.[0-9]{3}) "
    r"combined=([0-9]{1,6}\.[0-9]{3})\Z"
)
RESULT_DISTINCT = re.compile(
    r"result=HOST_HYPOTHESIS_ONLY model="
    r"(BT601_FULL|BT709_FULL|BT601_LIMITED|BT709_LIMITED) "
    r"order=(CbCr|CrCb) gap=([0-9]{1,6}\.[0-9]{3})\Z"
)
RESULT_INCONCLUSIVE = re.compile(
    r"result=INCONCLUSIVE gap=([0-9]{1,6}\.[0-9]{3})\Z"
)
WARNING = (
    "WARNING: Does NOT establish Samsung NX300M 1.14 DMA layout, "
    "actual matrix/range, capture ABI, or firmware safety."
)
MAX_OUTPUT = 16 * 1024
MAX_PROBE_BYTES = 8 * 1024 * 1024


def refuse(message: str):
    raise ValueError(message)


def probe_hash(binary: Path, expected: str) -> str:
    if not SHA.fullmatch(expected):
        refuse("Expected probe SHA-256 must be 64 hex digits")
    if binary.is_symlink():
        refuse("Executable is a symlink")
    fd = os.open(binary, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_PROBE_BYTES:
            refuse("Probe is not a bounded regular executable")
        if not before.st_mode & 0o111 or before.st_mode & 0o022:
            refuse("Probe lacks execute permission or is group/world writable")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            refuse("Probe changed during SHA validation")
    value = digest.hexdigest()
    if value != expected.lower():
        refuse("Probe SHA-256 mismatch")
    return value


def parse_probe(text: str, code: int, width: int, height: int) -> dict:
    if len(text.encode("utf-8")) > MAX_OUTPUT or "\r" in text or "\x00" in text:
        refuse("Probe output exceeds strict text limits")
    lines = text.strip().split("\n")
    if len(lines) != 12 or lines[-1] != WARNING:
        refuse("Probe output has an unexpected record count or safety warning")
    m = SAMPLE.fullmatch(lines[0])
    n = INFO.fullmatch(lines[1])
    if not m or not n:
        refuse("Missing chroma sample counters")
    sampled, informative = int(m[1]), int(n[1])
    if not 1 <= sampled <= width * height // 4 or informative > sampled:
        refuse("Invalid chroma counters")
    scores = {}
    for line in lines[2:10]:
        entry = SCORE.fullmatch(line)
        if not entry:
            refuse("Invalid candidate model output")
        key = (entry[1], entry[2])
        if key in scores:
            refuse("Duplicate candidate model score")
        a, b, c = (int(entry[k].replace(".", "")) for k in (3, 4, 5))
        if abs((a + b) - c) > 2:
            refuse("Candidate scores do not add up")
        scores[key] = c
    if set(scores) != {(m, o) for m in MODELS for o in ORDERS}:
        refuse("Incomplete set of eight color hypotheses")
    order = sorted(scores, key=lambda k: scores[k])
    gap = scores[order[1]] - scores[order[0]]
    distinct = RESULT_DISTINCT.fullmatch(lines[10])
    ambiguous = RESULT_INCONCLUSIVE.fullmatch(lines[10])
    if distinct and code == 0:
        model_order = (distinct[1], distinct[2])
        if model_order != order[0] or abs(int(distinct[3].replace(".", "")) - gap) > 1:
            refuse("Winner or gap contradicts eight model scores")
        best = scores[order[0]]
        # Match the published algorithm's fail-closed distinct criteria.
        # y_mae/chroma_mae limits are independently checked below.
        winner = next(
            SCORE.fullmatch(x) for x in lines[2:10]
            if x.startswith("hypothesis=" + distinct[1] + ":" + distinct[2] + " ")
        )
        y_mae = int(winner[3].replace(".", ""))
        c_mae = int(winner[4].replace(".", ""))
        if (sampled < 16 or informative < 8 or informative * 10 < sampled
                or y_mae > 8000 or c_mae > 6000 or gap < 2500 or best < 0):
            refuse("False distinct verdict on insufficient evidence")
        return {
            "host_color_hypothesis": "DISTINCT_ONLY",
            "candidate_model": distinct[1],
            "candidate_chroma_order": distinct[2],
            "gap_mae_milli": gap,
            "sampled_chroma_pairs": sampled,
            "informative_pairs": informative,
        }
    if ambiguous and code == 3:
        if abs(int(ambiguous[1].replace(".", "")) - gap) > 1:
            refuse("Ambiguous gap contradicts scores")
        return {
            "host_color_hypothesis": "INCONCLUSIVE",
            "candidate_model": None,
            "candidate_chroma_order": None,
            "gap_mae_milli": gap,
            "sampled_chroma_pairs": sampled,
            "informative_pairs": informative,
        }
    refuse("Probe return code and verdict disagree")


def verify_bundle(
    bundle: Path, executable: Path, executable_sha256: str,
    manifest_name: str = "capture.json",
) -> dict:
    if not executable.is_absolute():
        refuse("Explicit absolute path required for independent HOST executable")
    hash_before = probe_hash(executable, executable_sha256)
    original = manifest.verify(bundle, manifest_name)
    roles = original["verified_plane_hashes"]
    args = [
        str(executable), str(original["width"]), str(original["height"]),
        str(roles["y"]["stride"]), str(roles["c"]["stride"]),
        str(roles["rgb"]["stride"]),
        str(bundle / roles["y"]["file"]),
        str(bundle / roles["c"]["file"]),
        str(bundle / roles["rgb"]["file"]),
    ]
    try:
        process = subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=60,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            cwd=str(bundle),
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Offline C probe failed to execute or timed out") from exc
    if process.returncode not in (0, 3) or process.stderr:
        refuse("Offline C probe rejected evidence or emitted diagnostics")
    verdict = parse_probe(process.stdout, process.returncode,
                          original["width"], original["height"])
    # Detect ordinary modifications / replacement during external probe.
    if probe_hash(executable, executable_sha256) != hash_before:
        refuse("Executable changed while processing")
    again = manifest.verify(bundle, manifest_name)
    if again != original:
        refuse("Copied planes or manifest changed while probing")
    return {
        "capture_file_integrity": "PASS",
        "probe_executable_sha256": hash_before,
        "host_probe_verdict": verdict,
        "on_camera_color_model_authenticated": False,
        "same_stage_camera_capture_authenticated": False,
        "native_dma_buffer_ownership_verified": False,
        "native_jpeg_exif_makernotes_verified": False,
        "firmware_114_manufacturer_authenticated": False,
        "camera_firmware_install_permitted": False,
        "notes": (
            "SHA association and a distinct host model are NOT camera provenance "
            "or live FW1.14 ABI proof; no pixels are sent to a camera."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle-dir", type=Path, required=True)
    ap.add_argument("--probe", type=Path, required=True)
    ap.add_argument("--probe-sha256", required=True)
    ap.add_argument("--manifest", default="capture.json")
    args = ap.parse_args(argv)
    try:
        outcome = verify_bundle(args.bundle_dir.absolute(),
                                args.probe, args.probe_sha256, args.manifest)
        print(json.dumps(outcome, sort_keys=True))
        return 3 if outcome["host_probe_verdict"]["host_color_hypothesis"] == "INCONCLUSIVE" else 0
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("NX300M_CAPTURE_EVIDENCE_REJECTED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
