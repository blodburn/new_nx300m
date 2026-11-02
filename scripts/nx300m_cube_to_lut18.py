#!/usr/bin/env python3
"""Independent, host-only .cube -> NX300M 18^3 linear 12-bit LUT bridge.

Reads an Adobe 3D LUT with sRGB-encoded input/output, as emitted by an
appropriately configured offline LUT generator. No spektrafilm source or
profile data are included. No firmware or camera access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

GRID = 18
MAGIC = "NX18_RGB12_TEXT_V1"
MAX_SOURCE_BYTES = 24 * 1024 * 1024
MAX_GRID = 65
RGB12 = 4095
NUM = re.compile(r"^[0-9]+$")


def reject(message: str):
    raise ValueError(message)


def decode_srgb(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def encode_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def quant12(x: float) -> int:
    return min(RGB12, max(0, int(x * RGB12 + 0.5)))


def parse_triplet(parts: list[str], message: str) -> tuple[float, float, float]:
    if len(parts) != 3:
        reject(message + ": expected three numbers")
    try:
        result = tuple(float(x) for x in parts)
    except ValueError as e:
        raise ValueError(message + ": nonnumeric value") from e
    if not all(math.isfinite(x) for x in result):
        reject(message + ": nonfinite value")
    return result


def parse_cube(path: Path):
    if path.suffix.lower() != ".cube":
        reject("Input extension must be .cube")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
            reject("Input must be a bounded regular .cube")
        raw = f.read(MAX_SOURCE_BYTES + 1)
        after = os.fstat(f.fileno())
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in keys):
            reject("Input changed while reading")
    if len(raw) > MAX_SOURCE_BYTES or b"\x00" in raw:
        reject("Oversized or binary input")
    try:
        contents = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError("Input must be UTF-8 .cube") from e
    grid = None
    domain_min, domain_max = None, None
    values: list[tuple[float, float, float]] = []
    title_seen = False
    started = False
    for lineno, rawline in enumerate(contents.splitlines(), 1):
        line = rawline.split("#", 1)[0].strip()
        if not line:
            continue
        items = line.split()
        key = items[0].upper()
        if key in ("TITLE", "LUT_3D_SIZE", "DOMAIN_MIN", "DOMAIN_MAX", "LUT_1D_SIZE"):
            if started:
                reject("Header directive after LUT data on line " + str(lineno))
            if key == "TITLE":
                if title_seen:
                    reject("Repeated TITLE")
                title_seen = True
            elif key == "LUT_1D_SIZE":
                reject("Shaper/1D LUT is unsupported; bake a single sRGB 3D LUT")
            elif key == "LUT_3D_SIZE":
                if grid is not None or len(items) != 2 or not NUM.fullmatch(items[1]):
                    reject("Invalid or repeated LUT_3D_SIZE")
                grid = int(items[1])
                if not 2 <= grid <= MAX_GRID:
                    reject("LUT grid outside 2..65")
            elif key == "DOMAIN_MIN":
                if domain_min is not None:
                    reject("Repeated DOMAIN_MIN")
                domain_min = parse_triplet(items[1:], "DOMAIN_MIN")
            else:
                if domain_max is not None:
                    reject("Repeated DOMAIN_MAX")
                domain_max = parse_triplet(items[1:], "DOMAIN_MAX")
            continue
        if grid is None:
            reject("LUT_3D_SIZE must come before LUT data")
        if len(values) >= grid ** 3:
            reject("Too many LUT nodes")
        rgb = parse_triplet(items, "LUT node " + str(lineno))
        if any(x < 0.0 or x > 1.0 for x in rgb):
            reject("Out-of-gamut LUT output; implicit clipping forbidden")
        values.append(rgb)
        started = True
    if grid is None or len(values) != grid ** 3:
        reject("LUT node count does not match LUT_3D_SIZE")
    if domain_min not in (None, (0.0, 0.0, 0.0)):
        reject("Only DOMAIN_MIN 0 0 0 is supported")
    if domain_max not in (None, (1.0, 1.0, 1.0)):
        reject("Only DOMAIN_MAX 1 1 1 is supported")
    return grid, values, hashlib.sha256(raw).hexdigest()


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def sample_cube(nodes, n: int, rgb: tuple[float, float, float]):
    axes = []
    for c in rgb:
        x = min(1.0, max(0.0, c)) * (n - 1)
        lo = min(n - 1, int(x))
        hi = min(n - 1, lo + 1)
        axes.append((lo, hi, x - lo))
    (r0, r1, tr), (g0, g1, tg), (b0, b1, tb) = axes
    def at(r, g, b):
        return nodes[(b * n + g) * n + r]
    out = []
    for channel in range(3):
        v00 = lerp(at(r0, g0, b0)[channel], at(r1, g0, b0)[channel], tr)
        v10 = lerp(at(r0, g1, b0)[channel], at(r1, g1, b0)[channel], tr)
        v01 = lerp(at(r0, g0, b1)[channel], at(r1, g0, b1)[channel], tr)
        v11 = lerp(at(r0, g1, b1)[channel], at(r1, g1, b1)[channel], tr)
        out.append(lerp(lerp(v00, v10, tg), lerp(v01, v11, tg), tb))
    return tuple(out)


def make_nx18(n: int, source):
    nodes = []
    for b in range(GRID):
        for g in range(GRID):
            for r in range(GRID):
                rgb_in_linear = (r / 17, g / 17, b / 17)
                encoded = tuple(encode_srgb(c) for c in rgb_in_linear)
                color = sample_cube(source, n, encoded)
                nodes.append(tuple(quant12(decode_srgb(c)) for c in color))
    return nodes


def lerp_fixed(a: int, b: int, factor: int) -> int:
    return (a * (65536 - factor) + b * factor + 32768) >> 16


def sample_nx18(nodes, linear_rgb):
    axes = []
    for c in linear_rgb:
        integer = quant12(c)
        scaled = integer * 17
        lo, rem = divmod(scaled, RGB12)
        hi = min(17, lo + 1)
        axes.append((lo, hi, (rem * 65536 + 2047) // RGB12))
    (r0, r1, tr), (g0, g1, tg), (b0, b1, tb) = axes
    def at(r, g, b, channel):
        return nodes[(b * GRID + g) * GRID + r][channel]
    result = []
    for channel in range(3):
        v00 = lerp_fixed(at(r0,g0,b0,channel),at(r1,g0,b0,channel),tr)
        v10 = lerp_fixed(at(r0,g1,b0,channel),at(r1,g1,b0,channel),tr)
        v01 = lerp_fixed(at(r0,g0,b1,channel),at(r1,g0,b1,channel),tr)
        v11 = lerp_fixed(at(r0,g1,b1,channel),at(r1,g1,b1,channel),tr)
        x0 = lerp_fixed(v00,v10,tg)
        x1 = lerp_fixed(v01,v11,tg)
        result.append(lerp_fixed(x0,x1,tb) / RGB12)
    return tuple(result)


def halton(index: int, base: int) -> float:
    f, v = 1.0, 0.0
    while index:
        f /= base
        index, d = divmod(index, base)
        v += d * f
    return v


def quality_check(n, original, packed, count):
    errors = []
    maximum = 0.0
    for i in range(1, count + 1):
        lin = (halton(i, 2), halton(i, 3), halton(i, 5))
        reference = sample_cube(original, n, tuple(encode_srgb(x) for x in lin))
        encoded_nx = tuple(encode_srgb(x) for x in sample_nx18(packed, lin))
        rgb_err = max(abs(a-b) * 255 for a,b in zip(reference, encoded_nx))
        errors.append(rgb_err)
        maximum = max(maximum, rgb_err)
    errors.sort()
    return {"samples": count,
            "max_abs_channel_8bit": round(maximum, 5),
            "mean_max_channel_8bit": round(sum(errors) / count, 5),
            "p99_abs_channel_8bit": round(errors[min(count - 1, int(count * 0.99))], 5),
            "method": "Halton off-grid; sRGB code value; max RGB channel absolute error; quantized NX18 12-bit trilinear"}


def convert(source_path, output_path, qa_path, max_error, mean_error, samples, provenance):
    n, source, source_sha = parse_cube(source_path)
    packed = make_nx18(n, source)
    qa = quality_check(n, source, packed, samples)
    if qa["max_abs_channel_8bit"] > max_error or qa["mean_max_channel_8bit"] > mean_error:
        reject("Resampling QA exceeds declared error limits; no LUT published: " + str(qa))
    if output_path == qa_path or output_path == source_path or qa_path == source_path:
        reject("Output, QA and input paths must differ")
    if output_path.exists() or output_path.is_symlink() or qa_path.exists() or qa_path.is_symlink():
        reject("Output exists; do not replace or overwrite")
    if not output_path.parent.is_dir() or not qa_path.parent.is_dir():
        reject("Output directory missing")
    data = MAGIC + "\n" + "".join("%d %d %d\n" % row for row in packed)
    report = {
        "status": "PASS", "camera_firmware_installable": False,
        "actual_firmware_114_verified": False,
        "input_encoding": "sRGB", "output_encoding": "sRGB",
        "nx_lut_encoding": "linear-light RGB12", "input_cube_grid": n,
        "output_grid": GRID, "output_nodes": len(packed),
        "output_bytes": GRID ** 3 * 8, "source_sha256": source_sha,
        "nx18_text_sha256": hashlib.sha256(data.encode()).hexdigest(),
        "max_error_8bit_limit": max_error, "mean_error_8bit_limit": mean_error,
        "quality": qa, "provenance": provenance,
        "licensing": "Preserve upstream license/attribution for any derivative LUT; not an automatic distribution grant",
    }
    created_output = False
    created_qa = False
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as f:
            created_output = True
            f.write(data)
        with qa_path.open("x", encoding="utf-8", newline="\n") as f:
            created_qa = True
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except BaseException:
        if created_output:
            output_path.unlink(missing_ok=True)
        if created_qa:
            qa_path.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=Path, help="single sRGB-in/sRGB-out .cube")
    ap.add_argument("--output", required=True, type=Path, help="new .nx18.txt file; never overwrite")
    ap.add_argument("--qa", type=Path, help="new QA JSON; default output with .qa.json suffix")
    ap.add_argument("--max-error-8bit", type=float, default=12.0)
    ap.add_argument("--mean-error-8bit", type=float, default=2.0)
    ap.add_argument("--samples", type=int, default=2048)
    ap.add_argument("--source-name", default="user-provided LUT")
    ap.add_argument("--license-id", default="UNVERIFIED_TEST_ONLY")
    args = ap.parse_args(argv)
    if not (math.isfinite(args.max_error_8bit) and args.max_error_8bit >= 0 and
            math.isfinite(args.mean_error_8bit) and args.mean_error_8bit >= 0 and
            128 <= args.samples <= 20000):
        ap.error("QA limits or samples outside supported range")
    target_qa = args.qa if args.qa else args.output.with_suffix(args.output.suffix + ".qa.json")
    try:
        report = convert(args.input, args.output, target_qa, args.max_error_8bit,
                         args.mean_error_8bit, args.samples,
                         {"source": args.source_name, "license_id": args.license_id})
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as e:
        print("NX18_CONVERSION_REJECTED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
