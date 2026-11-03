#!/usr/bin/env python3
"""Synthetic, no-network tests for NX300M unofficial archival acquisition."""
from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
import zipfile

import nx300m_unofficial_archive_acquire as acquire
from test_nx300m_slp_firmware_integrity import fixture


def zipped(data: bytes, inner: str = "NX300M.bin") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(inner, data, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


class MemoryResponse(io.BytesIO):
    def __init__(self, data: bytes, url: str, claimed: int | None = None):
        super().__init__(data)
        self.url = url
        self.status = 200
        self.headers = {"Content-Length": str(len(data) if claimed is None else claimed)}

    def geturl(self) -> str:
        return self.url


class StubOpener:
    def __init__(self, payload: bytes, *, final_url: str | None = None,
                 claimed: int | None = None):
        self.payload = payload
        self.final_url = final_url
        self.claimed = claimed

    def open(self, request: Request, timeout: float = 0):
        return MemoryResponse(self.payload, self.final_url or request.full_url,
                              self.claimed)


class ArchiveAcquisitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.TemporaryDirectory()
        self.dir = Path(self.root.name)

    def tearDown(self) -> None:
        self.root.cleanup()

    def test_url_is_exact_pinned_archive_name(self) -> None:
        self.assertEqual(acquire.archive_url("1.14"), (
            "https://nxfiles.ydns.eu/files/NX300M/Firmware/NX300M_FW_v1.14.zip"))
        self.assertRaises(ValueError, acquire.archive_url, "../1.14")
        self.assertRaises(ValueError, acquire.archive_url, "1.16")

    def test_small_synthetic_zip_success_and_original_immutable(self) -> None:
        data = zipped(fixture(version="1.14"))
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            result = acquire.fetch_one("1.14", self.dir, opener=StubOpener(data))
        self.assertEqual(result["bytes"], len(data))
        self.assertEqual(result["download_sha256"], hashlib.sha256(data).hexdigest())
        self.assertFalse(result["source_is_official_samsung"])
        self.assertEqual(Path(result["path"]).read_bytes(), data)
        self.assertEqual(acquire.slp.inspect(Path(result["path"]),
                                             expected_version="1.14")[
                                                 "version_from_binary"], "1.14")

    def test_preexisting_path_is_never_overwritten(self) -> None:
        p = self.dir / "NX300M_FW_v1.14.zip"
        p.write_bytes(b"original")
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            with self.assertRaises(FileExistsError):
                acquire.fetch_one("1.14", self.dir, opener=StubOpener(
                    zipped(fixture(version="1.14"))))
        self.assertEqual(p.read_bytes(), b"original")

    def test_outside_redirect_refused_no_zip_left(self) -> None:
        data = zipped(fixture(version="1.14"))
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "origin"):
                acquire.fetch_one("1.14", self.dir, opener=StubOpener(
                    data, final_url="https://untrusted.invalid/firmware.zip"))
        self.assertFalse((self.dir / "NX300M_FW_v1.14.zip").exists())

    def test_response_length_mismatch_refused_no_zip_left(self) -> None:
        data = zipped(fixture(version="1.14"))
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "length mismatch"):
                acquire.fetch_one("1.14", self.dir, opener=StubOpener(
                    data, claimed=len(data)+1))
        self.assertFalse((self.dir / "NX300M_FW_v1.14.zip").exists())

    def test_not_zip_refused_and_cleanup(self) -> None:
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "not a ZIP"):
                acquire.fetch_one("1.14", self.dir,
                                  opener=StubOpener(b"<html>no archive</html>"))
        self.assertFalse((self.dir / "NX300M_FW_v1.14.zip").exists())

    def test_oversized_or_undersized_refused(self) -> None:
        data = zipped(fixture(version="1.14"))
        with patch.object(acquire, "MAX_ZIP_BYTES", 10), patch.object(
            acquire, "MIN_ZIP_BYTES", 1
        ):
            with self.assertRaisesRegex(ValueError, "too large"):
                acquire.fetch_one("1.14", self.dir, opener=StubOpener(data))
        with self.assertRaisesRegex(ValueError, "short"):
            acquire.fetch_one("1.14", self.dir, opener=StubOpener(data))

    def test_wrong_115_as_114_is_rejected(self) -> None:
        data = zipped(fixture(version="1.15"))
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            acquired = acquire.fetch_one("1.14", self.dir, opener=StubOpener(data))
        with self.assertRaisesRegex(ValueError, "version"):
            acquire.slp.inspect(Path(acquired["path"]), expected_version="1.14")

    def test_two_version_end_to_end_static_delta_no_camera_claims(self) -> None:
        payloads = {"1.14": zipped(fixture(version="1.14")),
                    "1.15": zipped(fixture(version="1.15"))}
        def stub(version: str, folder: Path):
            return acquire.fetch_one(version, folder,
                                     opener=StubOpener(payloads[version]))
        with patch.object(acquire, "MIN_ZIP_BYTES", 1):
            result = acquire.acquire_and_inspect(self.dir, fetcher=stub)
        self.assertEqual(result["changed_image_count"], 0)
        self.assertEqual(result["source_class"], "UNOFFICIAL_MIRROR_UNAUTHENTICATED")
        self.assertFalse(result["manufacturer_binary_identity_proven"])
        self.assertFalse(result["on_camera_validated"])
        self.assertFalse(result["camera_firmware_modification_permitted"])
        self.assertFalse(result["binary_abi_equivalence_verified"])
        self.assertEqual(result["target"]["internal_version"], "1.14")
        self.assertEqual(result["reference"]["internal_version"], "1.15")

    def test_no_symlink_or_world_writable_directory(self) -> None:
        link = self.dir / "linked"
        link.symlink_to(self.dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            acquire.validate_target(link)
        private = self.dir / "private"
        private.mkdir(mode=0o777)
        private.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "World-writable"):
            acquire.validate_target(private)

    def test_cli_refuses_missing_without_download(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        nonexistent = self.dir / "not_found"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = acquire.main(["--private-dir", str(nonexistent)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ARCHIVE_AUDIT_FAILED", stderr.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
