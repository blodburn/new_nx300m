#!/usr/bin/env python3
"""Synthetic 65^3 LUT output, SHA and numerical gate regression."""
from __future__ import annotations
import hashlib
import importlib.util
import tempfile
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"scripts/nx300m_cube_to_lut65.py"
s=importlib.util.spec_from_file_location("lut65_converter",p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

def synthetic(path,n=9):
    with path.open("w",encoding="utf-8") as f:
        f.write(f"LUT_3D_SIZE {n}\n")
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    f.write(f"{r/(n-1):.9g} {g/(n-1):.9g} {b/(n-1):.9g}\n")

class LUT65Tests(unittest.TestCase):
    def test_full_grid_host_format_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/"synthetic.cube"
            dst=root/"synthetic.nx65.txt";qa=root/"qa.json"
            synthetic(src)
            q=m.convert(src,dst,qa,n=65,count=128,
                      source_name="synthetic only",license_id="ORIGINAL_FIXTURE")
            self.assertEqual(q["status"],"PASS_NUMERICAL_ONLY")
            self.assertEqual(q["nodes"],274625)
            self.assertEqual(q["table_bytes"],2197000)
            self.assertFalse(q["camera_installable"])
            self.assertLess(q["metrics"]["peak_8bit"],12)
            self.assertEqual(q["lut_text_sha256"],hashlib.sha256(dst.read_bytes()).hexdigest())
            with dst.open() as f:
                self.assertEqual(f.readline(),"NX_LUT_RGB12_GRID_V1\n")
                self.assertEqual(f.readline(),"grid=65\n")
                self.assertEqual(f.readline(),"0 0 0\n")
            self.assertEqual(len(dst.read_text().splitlines()),274627)
            with self.assertRaisesRegex(ValueError,"Existing"):
                m.convert(src,dst,qa,n=65,count=128)
    def test_strict_reject_has_no_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/"synthetic.cube";synthetic(src)
            dst=root/"bad.nx33.txt";qa=root/"bad.qa.json"
            with self.assertRaisesRegex(ValueError,"Numerical"):
                m.convert(src,dst,qa,n=33,count=128,peak_limit=0,mean_limit=0)
            self.assertFalse(dst.exists());self.assertFalse(qa.exists())
    def test_unsupported_grid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/"synthetic.cube";synthetic(src)
            with self.assertRaisesRegex(ValueError,"Only grid"):
                m.convert(src,root/"bad.nx18.txt",root/"qa.json",n=18,count=128)
if __name__=="__main__":
    unittest.main(verbosity=2)
