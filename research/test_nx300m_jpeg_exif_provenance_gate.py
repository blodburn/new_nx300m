#!/usr/bin/env python3
"""Host JPEG EXIF/MakerNote parity with actual encoder, negative file tests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_jpeg_exif_provenance_gate as gate

FIXTURE = Path(".build/nx300m_test_jpeg_pair_fixture").absolute()


class JPEGExifAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.is_file():
            raise AssertionError("Build .build/nx300m_test_jpeg_pair_fixture first")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.original = root / "original.jpg"
        self.film = root / "film.jpg"
        subprocess.run([str(FIXTURE), str(self.original), str(self.film)],
                       capture_output=True, check=True, timeout=15)

    def mutate(self, path, transform):
        path.write_bytes(transform(path.read_bytes()))

    def test_real_host_encoder_two_jpegs_and_makernote(self):
        before = {p: p.read_bytes() for p in (self.original, self.film)}
        result = gate.inspect_pair(self.original, self.film, True, 34, 22)
        self.assertEqual(result["result"], "HOST_JPEG_STRUCTURE_AND_APP1_EQUAL")
        self.assertEqual((result["width"], result["height"]), (34, 22))
        self.assertEqual(result["sampling"], "4:2:0")
        self.assertTrue(result["makernote_found"])
        self.assertEqual(result["makernote_size"], 8)
        self.assertEqual(result["makernote_sha256"],
                         hashlib.sha256(b"NX-MAKER").hexdigest())
        self.assertNotEqual(result["original_sha256"],
                            result["processed_sha256"])
        self.assertTrue(result["app_markers_preserved"])
        for field in ("native_samsung_exif_abi_verified",
                      "maker_note_semantics_verified",
                      "real_camera_capture_verified", "firmware_flash_permitted"):
            self.assertIs(result[field], False)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_exif_byte_change_blocked(self):
        self.mutate(self.film,
                    lambda b: b.replace(b"NX-MAKER", b"NX-MAKEX", 1))
        with self.assertRaisesRegex(ValueError, "APP1 is not byte-identical"):
            gate.inspect_pair(self.original, self.film, True)

    def test_wrong_sof_422_or_dimensions_blocked(self):
        a = self.film.read_bytes()
        marker = a.index(b"\xff\xc0")
        sampling_offset = marker + 4 + 6 + 1
        self.assertEqual(a[sampling_offset], 0x22)
        for edit in ("chroma", "width"):
            self.film.write_bytes(a)
            raw = bytearray(a)
            if edit == "chroma":
                raw[sampling_offset] = 0x21
            else:
                # SOF0 marker(2), segment length(2), depth(1),
                # height(2), width(2) -> low width byte
                raw[marker + 8] ^= 0x01
            self.film.write_bytes(raw)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                gate.inspect_pair(self.original, self.film, True, 34, 22)

    def test_missing_eoi_and_trailing_bytes_blocked(self):
        good = self.film.read_bytes()
        for payload in (good[:-2], good + b"junk", good[:-2] + b"\xff\xc0"):
            self.film.write_bytes(payload)
            with self.assertRaises(ValueError):
                gate.inspect_pair(self.original, self.film, True)

    def test_duplicate_exif_app1_blocked(self):
        raw = self.film.read_bytes()
        location = raw.index(b"\xff\xe1")
        length = int.from_bytes(raw[location+2:location+4], "big")
        segment = raw[location:location+length+2]
        self.film.write_bytes(raw[:location] + segment + raw[location:])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            gate.inspect_pair(self.original, self.film, True)

    def test_invalid_tiff_makernote_offset_blocked(self):
        raw_orig = self.original.read_bytes()
        raw_film = self.film.read_bytes()
        offset = raw_orig.index(b"NX-MAKER")
        # MakerNote payload is at TIFF offset 44; Exif IFD entry's value
        # offset starts at TIFF offset 36 -> eight bytes before payload.
        # Replace its pointer 44 with an out-of-range offset.
        orig = bytearray(raw_orig)
        film = bytearray(raw_film)
        expected = b"\x2c\x00\x00\x00"
        self.assertEqual(orig[offset-8:offset-4], expected)
        self.assertEqual(film[raw_film.index(b"NX-MAKER")-8:
                              raw_film.index(b"NX-MAKER")-4], expected)
        orig[offset-8:offset-4] = b"\xff\xff\xff\x7f"
        p = raw_film.index(b"NX-MAKER")
        film[p-8:p-4] = b"\xff\xff\xff\x7f"
        self.original.write_bytes(orig)
        self.film.write_bytes(film)
        with self.assertRaisesRegex(ValueError, "pointer"):
            gate.inspect_pair(self.original, self.film, True)

    def test_missing_makernote_rejected_when_required(self):
        for p in (self.original, self.film):
            data = p.read_bytes()
            # Exif MakerNote tag little-endian 0x927C -> unmatched 0x9281.
            self.assertIn(b"\x7c\x92\x07\x00", data)
            p.write_bytes(data.replace(b"\x7c\x92\x07\x00",
                                        b"\x81\x92\x07\x00", 1))
        result = gate.inspect_pair(self.original, self.film)
        self.assertFalse(result["makernote_found"])
        with self.assertRaisesRegex(ValueError, "Required MakerNote"):
            gate.inspect_pair(self.original, self.film, True)

    def test_symlinks_rejected(self):
        alias = self.original.with_suffix(".alias")
        alias.symlink_to(self.original)
        with self.assertRaisesRegex(ValueError, "symlink"):
            gate.inspect_pair(alias, self.film, True)

    def test_mismatched_exif_can_not_promote_as_camera_proof(self):
        result = gate.inspect_pair(self.original, self.film)
        self.assertFalse(result["real_camera_capture_verified"])
        self.assertFalse(result["native_samsung_exif_abi_verified"])
        self.assertFalse(result["maker_note_semantics_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
