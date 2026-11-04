#!/usr/bin/env python3
"""Integration: real compiled C model CLI + SHA-validated Y/C/RGB copies."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import nx300m_capture_evidence_model_gate as gate
import nx300m_capture_manifest_gate as manifest_gate

W, H = 48, 32
YS, CS, RS = W + 8, W + 8, W * 3 + 7
COLORS = (
    (244, 30, 15), (10, 48, 250), (35, 235, 20), (253, 130, 15),
    (183, 15, 240), (13, 231, 236), (248, 242, 10), (33, 15, 180),
)
BIN = Path(".build/nx300m_ycc420_multimodel_probe").absolute()


def u8(value):
    return max(0, min(255, int(math.floor(value + 0.5))))


def encode(rgb, model):
    kr, kb = (0.2126, 0.0722) if model in (1, 3) else (0.299, 0.114)
    lum = kr * rgb[0] + (1 - kr - kb) * rgb[1] + kb * rgb[2]
    cb = 128 + (rgb[2] - lum) / (2 * (1 - kb))
    cr = 128 + (rgb[0] - lum) / (2 * (1 - kr))
    if model >= 2:
        lum = 16 + lum * 219 / 255
        cb = 128 + (cb - 128) * 224 / 255
        cr = 128 + (cr - 128) * 224 / 255
    return u8(lum), u8(cb), u8(cr)


def fixture(root: Path, model=0, order=0, grayscale=False):
    y = bytearray(b"\xa5" * (H * YS))
    c = bytearray(b"\xc3" * ((H // 2) * CS))
    rgb = bytearray(b"\x5a" * (H * RS))
    for row in range(H):
        for x in range(W):
            px = (128, 128, 128) if grayscale else COLORS[
                ((x // 2) + (row // 2) * 7) % len(COLORS)
            ]
            rgb[row * RS + 3 * x:row * RS + 3 * x + 3] = bytes(px)
            y[row * YS + x] = encode(px, model)[0]
    for row in range(0, H, 2):
        for x in range(0, W, 2):
            cb = cr = 0
            for dy in range(2):
                for dx in range(2):
                    px = rgb[(row + dy) * RS + 3 * (x + dx):
                             (row + dy) * RS + 3 * (x + dx) + 3]
                    _, cb1, cr1 = encode(px, model)
                    cb += cb1
                    cr += cr1
            c[(row // 2) * CS + x + order] = (cb + 2) // 4
            c[(row // 2) * CS + x + (1 - order)] = (cr + 2) // 4
    planes = {}
    for name, buffer, stride in (
        ("y", y, YS), ("c", c, CS), ("rgb", rgb, RS)
    ):
        data = bytes(buffer)
        (root / (name + ".bin")).write_bytes(data)
        planes[name] = {
            "file": name + ".bin", "stride": stride, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    obj = {
        "format": manifest_gate.MARKER,
        "camera_model": "NX300M", "firmware_version": "1.14",
        "same_stage_copy_declared": True, "width": W, "height": H,
        "planes": planes,
    }
    (root / "capture.json").write_text(json.dumps(obj))
    return obj


class TestEvidenceToEightModelProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BIN.is_file():
            raise AssertionError("run make multimodel-probe before test")
        cls.sha = hashlib.sha256(BIN.read_bytes()).hexdigest()

    def run_gate(self, root):
        return gate.verify_bundle(root, BIN, self.sha)

    def test_eight_real_c_probe_color_hypotheses(self):
        for model, name in enumerate(gate.MODELS):
            for order, order_name in enumerate(gate.ORDERS):
                with self.subTest(model=name, order=order_name):
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        fixture(root, model=model, order=order)
                        original = {
                            p.name: p.read_bytes() for p in root.iterdir()
                        }
                        result = self.run_gate(root)
                        winner = result["host_probe_verdict"]
                        self.assertEqual(winner["host_color_hypothesis"],
                                         "DISTINCT_ONLY")
                        self.assertEqual(winner["candidate_model"], name)
                        self.assertEqual(winner["candidate_chroma_order"],
                                         order_name)
                        self.assertGreaterEqual(
                            winner["gap_mae_milli"], 2500
                        )
                        self.assertEqual(
                            original, {p.name: p.read_bytes()
                                       for p in root.iterdir()}
                        )
                        for key in (
                            "on_camera_color_model_authenticated",
                            "same_stage_camera_capture_authenticated",
                            "native_dma_buffer_ownership_verified",
                            "native_jpeg_exif_makernotes_verified",
                            "firmware_114_manufacturer_authenticated",
                            "camera_firmware_install_permitted",
                        ):
                            self.assertIs(result[key], False)

    def test_grayscale_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root, grayscale=True)
            result = self.run_gate(root)
            self.assertEqual(
                result["host_probe_verdict"]["host_color_hypothesis"],
                "INCONCLUSIVE"
            )
            self.assertIsNone(
                result["host_probe_verdict"]["candidate_model"]
            )
            self.assertEqual(
                gate.main(["--bundle-dir", str(root),
                           "--probe", str(BIN),
                           "--probe-sha256", self.sha]),
                3,
            )

    def test_corrupt_plane_or_forged_metadata_rejected(self):
        for corrupt in ("y", "c", "rgb", "metadata"):
            with self.subTest(corrupt=corrupt):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    fixture(root)
                    if corrupt == "metadata":
                        p = root / "capture.json"
                        p.write_text(p.read_text().replace('"1.14"', '"1.15"'))
                    else:
                        path = root / (corrupt + ".bin")
                        payload = bytearray(path.read_bytes())
                        payload[len(payload)//2] ^= 0x80
                        path.write_bytes(payload)
                    with self.assertRaises(ValueError):
                        self.run_gate(root)

    def test_bogus_binary_sha_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            with self.assertRaises(ValueError):
                gate.verify_bundle(root, BIN, "0" * 64)
            self.assertEqual(
                gate.main(["--bundle-dir", str(root), "--probe",
                           str(BIN), "--probe-sha256", "0" * 64]), 2
            )

    def test_symlink_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            fixture(root)
            alias = Path(tmp) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.run_gate(alias)

    def test_forged_incomplete_probe_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            fake = root / "forged-probe"
            fake.write_text(
                "#!/bin/sh\n"
                "echo 'sampled_chroma_pairs=384'\n"
                "echo 'result=HOST_HYPOTHESIS_ONLY model=BT601_FULL "
                "order=CbCr gap=999.000'\n"
                "exit 0\n"
            )
            fake.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            expected = hashlib.sha256(fake.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                gate.verify_bundle(root, fake, expected)

    def test_inconsistent_winner_rejected(self):
        good = [
            "sampled_chroma_pairs=384",
            "informative_pairs=384",
        ]
        for model in gate.MODELS:
            for order in gate.ORDERS:
                delta = "0.000" if model == "BT601_FULL" and order == "CbCr" else "4.000"
                good.append("hypothesis=" + model + ":" + order +
                            " y_mae=" + delta +
                            " chroma_mae=0.000 combined=" + delta)
        good.extend([
            "result=HOST_HYPOTHESIS_ONLY model=BT709_FULL order=CbCr gap=4.000",
            gate.WARNING,
        ])
        with self.assertRaises(ValueError):
            gate.parse_probe("\n".join(good), 0, W, H)


if __name__ == "__main__":
    unittest.main(verbosity=2)
