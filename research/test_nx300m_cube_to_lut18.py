#!/usr/bin/env python3
"""Synthetic-only tests: no spektrafilm profiles, camera I/O or firmware."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[1] / "scripts" / "nx300m_cube_to_lut18.py"
spec = importlib.util.spec_from_file_location("nx_cube", GATE)
assert spec and spec.loader
cube = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cube)


def fixture(path: Path, n=17, header="", exponent=1.0):
    with path.open("w", encoding="utf-8") as f:
        f.write('TITLE "Synthetic test LUT"\nLUT_3D_SIZE %d\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n' % n)
        if header:
            f.write(header)
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    f.write("%.10g %.10g %.10g\n" %
                            ((r/(n-1))**exponent,(g/(n-1))**exponent,(b/(n-1))**exponent))


class CubeBridgeTests(unittest.TestCase):
    def test_realistic_33grid_identity_qa(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            source, output, report = d / "source.cube", d / "profile.nx18.txt", d / "report.json"
            fixture(source, 33)
            info = cube.convert(source, output, report, 12, 2, 1024,
                                {"source": "synthetic", "license_id": "UNVERIFIED_TEST_ONLY"})
            self.assertEqual(info["status"], "PASS")
            self.assertEqual(info["output_nodes"], 5832)
            self.assertFalse(info["camera_firmware_installable"])
            self.assertEqual(info["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            lines = output.read_text().splitlines()
            self.assertEqual(len(lines), 5833)
            self.assertEqual(lines[0], cube.MAGIC)
            self.assertEqual(lines[1], "0 0 0")
            self.assertEqual(lines[-1], "4095 4095 4095")
            self.assertLess(info["quality"]["max_abs_channel_8bit"], 3.0)
            self.assertEqual(json.loads(report.read_text())["output_grid"], 18)
            before = (output.read_bytes(), report.read_bytes())
            with self.assertRaisesRegex(ValueError, "exists"):
                cube.convert(source, output, report, 12, 2, 128, {"source": "synthetic"})
            self.assertEqual(before, (output.read_bytes(), report.read_bytes()))

    def test_nontrivial_generated_film_style(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            fixture(d / "tone.cube", 33, exponent=1.25)
            result = cube.convert(d / "tone.cube", d / "tone.nx18.txt",
                                  d / "tone.qa.json", 12, 2, 256,
                                  {"source": "synthetic"})
            self.assertGreater(result["quality"]["max_abs_channel_8bit"], 0)
            self.assertEqual(result["output_nodes"], cube.GRID**3)

    def test_explicit_error_gate_rejects_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);fixture(d/"a.cube",17)
            with self.assertRaisesRegex(ValueError,"QA exceeds"):
                cube.convert(d/"a.cube",d/"out.nx18.txt",d/"out.qa.json",
                             0,0,128,{"source":"synthetic"})
            self.assertFalse((d/"out.nx18.txt").exists())
            self.assertFalse((d/"out.qa.json").exists())

    def invalid(self, mutation):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td);p=d/"invalid.cube";fixture(p,3)
            p.write_text(mutation(p.read_text()))
            with self.assertRaises((OSError,ValueError)):
                cube.parse_cube(p)

    def test_1d_not_supported(self):
        self.invalid(lambda x:x.replace("DOMAIN_MIN","LUT_1D_SIZE 16\nDOMAIN_MIN",1))
    def test_out_of_range_output(self):
        self.invalid(lambda x:x.replace("\n0 0 0\n", "\n1.1 0 0\n",1))
    def test_nonfinite_node(self):
        self.invalid(lambda x:x.replace("0 0 0\n", "nan 0 0\n",1) if False else x.replace("\n0 0 0\n","\nnan 0 0\n",1))
    def test_invalid_domain(self):
        self.invalid(lambda x:x.replace("DOMAIN_MIN 0 0 0","DOMAIN_MIN 0.1 0 0"))
    def test_repeat_grid(self):
        self.invalid(lambda x:x.replace("DOMAIN_MIN","LUT_3D_SIZE 3\nDOMAIN_MIN",1))
    def test_missing_node(self):
        self.invalid(lambda x:"\n".join(x.splitlines()[:-1])+"\n")
    def test_traversal_and_symlink_input(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/"actual.cube";fixture(p,3)
            (d/"alias.cube").symlink_to(p)
            with self.assertRaises((ValueError, OSError)):cube.parse_cube(d/"alias.cube")
    def test_cli_success_and_guard(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);fixture(d/"in.cube",5)
            cmd=[sys.executable,str(GATE),"--input",str(d/"in.cube"),
                 "--output",str(d/"out.nx18.txt"),"--samples","128",
                 "--source-name","synthetic fixture"]
            r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(r.stdout)["provenance"]["source"],"synthetic fixture")
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)


if __name__=="__main__":
    unittest.main(verbosity=2)
