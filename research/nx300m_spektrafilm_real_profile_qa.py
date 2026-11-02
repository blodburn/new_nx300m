#!/usr/bin/env python3
"""Summarize an EPHEMERAL real-profile SpektraFilm -> NX18 bridge trial.

No LUT/profile contents leave the CI workspace; only numerical metrics and
upstream provenance identifiers are printed to logs/GitHub step summary.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

UPSTREAM = "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
EXPECTED_FILM = "fujifilm_provia_100f"
EXPECTED_PRINT = "fujifilm_crystal_archive_typeii"
STRICT_PEAK = 12.0
STRICT_MEAN = 2.0


def evaluate(report: dict) -> dict:
    if report.get("status") != "PASS" or report.get("output_nodes") != 5832:
        raise ValueError("Conversion report did not pass structural checks")
    if report.get("input_encoding") != "sRGB" or report.get("output_encoding") != "sRGB":
        raise ValueError("Report is not sRGB-in/sRGB-out")
    if report.get("nx_lut_encoding") != "linear-light RGB12":
        raise ValueError("Unexpected NX18 encoding")
    if report.get("camera_firmware_installable") is not False:
        raise ValueError("Camera flash gate unexpectedly enabled")
    q = report.get("quality", {})
    peak = float(q.get("max_abs_channel_8bit"))
    avg = float(q.get("mean_max_channel_8bit"))
    if not (0 <= peak <= 255 and 0 <= avg <= peak):
        raise ValueError("Invalid numerical QA metrics")
    good = peak <= STRICT_PEAK and avg <= STRICT_MEAN
    return {
        "upstream_commit": UPSTREAM,
        "source_film": EXPECTED_FILM,
        "source_print": EXPECTED_PRINT,
        "test": "SpektraFilm real-profile ephemeral offline LUT",
        "decision": "PASS_NUMERICAL_RESCALING_ONLY" if good else "REJECT_NUMERICAL_RESCALING",
        "max_error_8bit": peak,
        "mean_error_8bit": avg,
        "strict_max_error_limit": STRICT_PEAK,
        "strict_mean_error_limit": STRICT_MEAN,
        "source_lut_sha256": report.get("source_sha256"),
        "nx18_text_sha256": report.get("nx18_text_sha256"),
        "firmware_114_verified": False,
        "camera_deployment_allowed": False,
        "notes": "No camera calibration, no camera sample, no GPU/CPU camera timing, no proprietary LUT files published.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--github-summary", type=Path)
    p.add_argument("--observe-only", action="store_true",
                   help="Report REJECT without failing exploratory CI; never authorizes deployment")
    args = p.parse_args(argv)
    try:
        result = evaluate(json.loads(args.report.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.github_summary:
            with args.github_summary.open("a", encoding="utf-8") as summary:
                summary.write("\n### NX300M SpektraFilm real-profile HOST trial\n\n")
                for k, v in result.items():
                    summary.write(f"- **{k}:** {v}\n")
        # Nonzero when model loses more color precision than the declared
        # numerical thresholds. NEVER a camera deployment authorization.
        return 0 if args.observe_only or result["decision"] == "PASS_NUMERICAL_RESCALING_ONLY" else 3
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("REAL_PROFILE_QA_REJECTED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
