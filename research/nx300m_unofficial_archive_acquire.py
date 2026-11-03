#!/usr/bin/env python3
"""Bounded, offline-after-download audit of archived NX300M 1.14 / 1.15.

Source is an unofficial Samsung NX archive, NOT proof of official provenance.
No camera I/O, installation, image extraction, firmware execution, patch,
repository artifact upload or source files committed. Run only in isolated CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zipfile

import nx300m_fw114_binary_delta as delta
import nx300m_slp_firmware_integrity as slp

ARCHIVE_ORIGIN = "https://nxfiles.ydns.eu"
ARCHIVE_BASE = ARCHIVE_ORIGIN + "/files/NX300M/Firmware/"
MAX_ZIP_BYTES = 300 * 1024 * 1024
MIN_ZIP_BYTES = 100 * 1024 * 1024
MAX_ELAPSED_SECONDS = 540
BLOCK_SIZE = 1024 * 1024


class StrictRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        # Refuse redirects outside the exact known mirror origin/path.
        if u.scheme != "https" or u.netloc != "nxfiles.ydns.eu" or (
            not u.path.startswith("/files/NX300M/Firmware/")
        ) or u.username or u.password or u.query or u.fragment:
            raise ValueError("Untrusted archive redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def archive_url(version: str) -> str:
    if version not in ("1.14", "1.15"):
        raise ValueError("Unsupported firmware version")
    return ARCHIVE_BASE + "NX300M_FW_v" + version + ".zip"


def validate_target(folder: Path) -> None:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Private output directory must exist and not be a symlink")
    if (folder.stat().st_mode & stat.S_IWOTH):
        raise ValueError("World-writable output directory refused")


def fetch_one(version: str, folder: Path, *, opener=None) -> dict:
    """Download a pinned-name archive into a private temp file, with size cap."""
    url = archive_url(version)
    folder = folder.resolve(strict=True)
    validate_target(folder)
    path = folder / ("NX300M_FW_v" + version + ".zip")
    # Never overwrite existing evidence. Do not guess a URL, source or hash.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    digest = hashlib.sha256()
    total = 0
    started = time.monotonic()
    opener = opener or build_opener(StrictRedirect)
    try:
        try:
            request = Request(url, headers={
                "User-Agent": "NX300M-research-offline-audit/1.0",
                "Accept": "application/zip, application/octet-stream",
            })
            with opener.open(request, timeout=60) as source, os.fdopen(fd, "wb") as out:
                fd = -1
                final_url = source.geturl()
                if final_url != url:
                    raise ValueError("Unexpected archive origin or URL")
                if getattr(source, "status", 200) != 200:
                    raise ValueError("Expected complete HTTP 200 response")
                header = source.headers.get("Content-Length")
                if header is not None and int(header) > MAX_ZIP_BYTES:
                    raise ValueError("Archive too large from HTTP header")
                while True:
                    if time.monotonic() - started > MAX_ELAPSED_SECONDS:
                        raise TimeoutError("Archive download time exceeded")
                    chunk = source.read(BLOCK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ZIP_BYTES:
                        raise ValueError("Archive byte cap exceeded")
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
                if header is not None and int(header) != total:
                    raise ValueError("HTTP archive length mismatch")
                if total < MIN_ZIP_BYTES:
                    raise ValueError("Unexpectedly short NX300M archive")
                if not zipfile.is_zipfile(path):
                    raise ValueError("Source is not a ZIP archive")
        except Exception:
            if fd >= 0:
                os.close(fd)
            raise
        return {
            "path": str(path), "source_url": url, "bytes": total,
            "download_sha256": digest.hexdigest(),
            "source_is_official_samsung": False,
        }
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def acquire_and_inspect(folder: Path, *, fetcher=fetch_one) -> dict:
    a = fetcher("1.14", folder)
    target = slp.inspect(Path(a["path"]), expected_version="1.14")
    b = fetcher("1.15", folder)
    reference = slp.inspect(Path(b["path"]), expected_version="1.15")
    # Do NOT pass a self-computed download hash as an *external* trusted
    # fingerprint. Only assert consistency of independent local reads.
    # A vendor-signed external SHA-256 is not presently available.
    comparison = delta.compare(Path(a["path"]), Path(b["path"]))
    if target["archive_sha256"] != a["download_sha256"] or (
        reference["archive_sha256"] != b["download_sha256"]
    ) or comparison["target"]["source_sha256"] != a["download_sha256"] or (
        comparison["reference"]["source_sha256"] != b["download_sha256"]
    ):
        raise ValueError("Downloaded archive changed during analysis")
    comparison["source_class"] = "UNOFFICIAL_MIRROR_UNAUTHENTICATED"
    comparison["download_sha256_matches_recheck"] = True
    comparison["manufacturer_binary_identity_proven"] = False
    comparison["on_camera_validated"] = False
    comparison["archive_url_fw114"] = a["source_url"]
    comparison["archive_url_fw115"] = b["source_url"]
    comparison["archive_114_zip_size"] = a["bytes"]
    comparison["archive_115_zip_size"] = b["bytes"]
    return comparison


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-dir", type=Path, required=True,
                   help="existing isolated private directory in CI; archives ephemeral")
    p.add_argument("--summary", type=Path, help="optional CI step summary path")
    args = p.parse_args(argv)
    try:
        output = acquire_and_inspect(args.private_dir)
        # Emit data only, never binary/image payload.
        print("NX300M_ARCHIVE_COMPARE_JSON " + json.dumps(
            output, ensure_ascii=False, sort_keys=True))
        if args.summary:
            with args.summary.open("a", encoding="utf-8") as writer:
                writer.write("\n### NX300M FW1.14 and FW1.15 (unofficial mirror)\n")
                writer.write("Integrity verified for downloaded archives, NOT Samsung provenance. "
                             "No firmware installation or device access.\n\n")
                writer.write("| SLP image | FW1.14 size | FW1.15 size | SHA-256 equal |\n")
                writer.write("|---|---:|---:|---|\n")
                for row in output["images"]:
                    writer.write(
                        f'| {row["index"]} | {row["fw114_bytes"]:,} '
                        f'| {row["fw115_bytes"]:,} | {row["sha256_equal"]} |\n')
                writer.write(
                    f'\nDiffering SLP image count: **{output["changed_image_count"]}/5**. '
                    "Camera ABI identity, recovery and installability remain **NO-GO**.\n")
        return 0
    except (ValueError, OSError, TimeoutError, zipfile.BadZipFile,
            RuntimeError, EOFError) as exc:
        print("ARCHIVE_AUDIT_FAILED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
