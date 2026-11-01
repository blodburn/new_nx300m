#!/usr/bin/env python3
"""Synthetic host-only Y/C420 capture manifest regression."""
import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
p=Path(__file__).with_name("nx300m_capture_manifest_gate.py")
s=importlib.util.spec_from_file_location("capture_manifest",p)
gate=importlib.util.module_from_spec(s);s.loader.exec_module(gate)
def make(root):
    planes={}
    for name,stride,rows in (("y",8,4),("c",8,2),("rgb",16,4)):
        b=bytes((k*29+len(name))%256 for k in range(stride*rows))
        (root/(name+".bin")).write_bytes(b)
        planes[name]={"file":name+".bin","stride":stride,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
    m={"format":gate.MARKER,"camera_model":"NX300M","firmware_version":"1.14",
       "same_stage_copy_declared":True,"width":4,"height":4,"planes":planes}
    (root/"capture.json").write_text(json.dumps(m));return m
class TestGate(unittest.TestCase):
    def invalid(self,fn):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);m=make(r);fn(m,r);(r/"capture.json").write_text(json.dumps(m))
            with self.assertRaises((ValueError,OSError)):gate.verify(r)
    def test_valid_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);make(r);saved={p.name:p.read_bytes() for p in r.iterdir()};v=gate.verify(r)
            self.assertEqual(v["integrity"],"PASS")
            for k in ("same_stage_verified","native_camera_layout_verified","camera_abi_verified","firmware_flash_safe"):self.assertFalse(v[k])
            self.assertEqual(saved,{p.name:p.read_bytes() for p in r.iterdir()})
    def test_firmware(self):self.invalid(lambda m,r:m.update(firmware_version="1.15"))
    def test_camera(self):self.invalid(lambda m,r:m.update(camera_model="NX300"))
    def test_format(self):self.invalid(lambda m,r:m.update(format="wrong"))
    def test_declaration(self):self.invalid(lambda m,r:m.update(same_stage_copy_declared=False))
    def test_odd_width(self):self.invalid(lambda m,r:m.update(width=3))
    def test_bool_width(self):self.invalid(lambda m,r:m.update(width=True))
    def test_missing_c(self):self.invalid(lambda m,r:m["planes"].pop("c"))
    def test_short_stride(self):self.invalid(lambda m,r:m["planes"]["rgb"].update(stride=3))
    def test_bad_length(self):self.invalid(lambda m,r:m["planes"]["y"].update(bytes=31))
    def test_bad_hash(self):self.invalid(lambda m,r:m["planes"]["y"].update(sha256="0"*64))
    def test_invalid_hash(self):self.invalid(lambda m,r:m["planes"]["y"].update(sha256="a"))
    def test_duplicate_file(self):self.invalid(lambda m,r:m["planes"]["c"].update(file="y.bin"))
    def test_traversal(self):self.invalid(lambda m,r:m["planes"]["y"].update(file="../f"))
    def test_symlink(self):
        def mod(m,r):(r/"y.bin").unlink();(r/"y.bin").symlink_to(r/"c.bin")
        self.invalid(mod)
    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);make(r);p=r/"capture.json";p.write_text(p.read_text().replace('"width": 4','"width": 4, "width": 4'))
            with self.assertRaises(ValueError):gate.verify(r)
    def test_bad_json_cli(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);make(r);(r/"capture.json").write_text("{")
            self.assertEqual(gate.main(["--bundle-dir",str(r)]),2)
if __name__=="__main__":unittest.main(verbosity=2)
