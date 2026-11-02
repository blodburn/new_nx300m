#!/usr/bin/env python3
"""Synthetic-only LUT grid diagnostic regression."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

p=Path(__file__).with_name("nx300m_lut_grid_diagnostics.py")
spec=importlib.util.spec_from_file_location("lut_grid_diag",p)
diag=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)

def fixture(p,n=9):
    with p.open("w",encoding="utf-8") as f:
        f.write(f"LUT_3D_SIZE {n}\n")
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    f.write(f"{r/(n-1):.8f} {g/(n-1):.8f} {b/(n-1):.8f}\n")
class TestGridDiagnostics(unittest.TestCase):
    def test_18_grid_matches_existing_qa_fixed_math(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"synth.cube";fixture(p,9)
            n,data,_=diag.bridge.parse_cube(p)
            nodes=diag.bridge.make_nx18(n,data)
            expected=diag.bridge.quality_check(n,data,nodes,128)
            report=diag.diagnostics(p,(18,33),128)
            got=report["results"][0]
            self.assertEqual(report["samples"],128)
            self.assertAlmostEqual(got["peak_8bit"],expected["max_abs_channel_8bit"],places=4)
            self.assertAlmostEqual(got["mean_8bit"],expected["mean_max_channel_8bit"],places=4)
            self.assertEqual(got["rgb12_table_bytes"],46656)
            self.assertEqual(report["results"][1]["nodes"],35937)
            self.assertTrue(report["no_derivative_lut_output"])
            self.assertFalse(report["firmware_tested"])
    def test_invalid_grid_or_count(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"synth.cube";fixture(p)
            with self.assertRaises(ValueError):diag.diagnostics(p,(1,),128)
            with self.assertRaises(ValueError):diag.diagnostics(p,(18,),1)
            with self.assertRaises(ValueError):diag.diagnostics(p,tuple(range(7,13)),128)
if __name__=="__main__":
    unittest.main(verbosity=2)
