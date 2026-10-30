#!/usr/bin/env python3
"""Fixture tests for host-only Picture Wizard ELF function-body comparison."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).parent
MODULE=HERE/"nx300m_picture_wizard_abi_gate.py"
SPEC=importlib.util.spec_from_file_location("nx300m_picture_wizard_abi_gate",MODULE)
assert SPEC and SPEC.loader
gate=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

def fake_lib(root:Path,stem:str,retval:int=1,remove_one:bool=False)->Path:
    code="""
    struct CProcessParameter {
      struct T_PWPARAM { int value; };
      int GetPictureWizardMode();
      int GetPictureWizardParameter(T_PWPARAM &);
      int updatePictureWizardBracket();
    };
    struct CCapCmdIf {
      int setPictureWizardBracket(int,int,int);
    };
    int CProcessParameter::GetPictureWizardMode(){ return %s; }
    int CProcessParameter::GetPictureWizardParameter(T_PWPARAM &a){
      return a.value + 8;
    }
    %s
    int CCapCmdIf::setPictureWizardBracket(int a,int b,int c){
      return a+b-c;
    }
    """%(retval,"" if remove_one else
         "int CProcessParameter::updatePictureWizardBracket(){ return 9; }")
    root.mkdir(exist_ok=True)
    src=root/(stem+".cpp")
    out=root/(stem+".so")
    src.write_text(code,encoding="utf8")
    subprocess.run(["g++","-std=c++11","-shared","-fPIC","-O0",
                    "-o",str(out),str(src)],check=True,capture_output=True)
    return out

class PictureWizardAbiTests(unittest.TestCase):
    def test_four_functions_found_and_full_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            p=fake_lib(Path(temp),"libreference")
            before=p.read_bytes()
            a=gate.fingerprints(p,allow_non_arm=True)
            self.assertEqual(a["found_count"],4)
            self.assertEqual(len(a["functions"]),4)
            self.assertEqual(a["elf_class"],64)
            self.assertFalse(a["arm_eabi5_candidate"])
            for item in a["functions"].values():
                self.assertEqual(len(item["code_sha256"]),64)
                self.assertGreater(item["size"],0)
            self.assertEqual(p.read_bytes(),before)

    def test_same_bodies_in_separate_compilations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            first=fake_lib(root,"libreference")
            second=fake_lib(root,"libother")
            a=gate.fingerprints(first,allow_non_arm=True)
            b=gate.fingerprints(second,allow_non_arm=True)
            compare=gate.compare(a,b)
            self.assertTrue(compare["all_four_function_bodies_identical"])
            self.assertFalse(compare["safe_to_flash_or_hook"])
            self.assertFalse(compare["safe_to_reuse_reference_addresses"])

    def test_one_function_changed_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a=gate.fingerprints(fake_lib(root,"liba",retval=1),allow_non_arm=True)
            b=gate.fingerprints(fake_lib(root,"libb",retval=42),allow_non_arm=True)
            compare=gate.compare(a,b)
            self.assertEqual(compare["results"][gate.TARGETS[0]],"BODY_BYTES_DIFFER")
            self.assertFalse(compare["all_four_function_bodies_identical"])
            self.assertFalse(compare["safe_to_flash_or_hook"])

    def test_missing_required_function_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a=gate.fingerprints(fake_lib(root,"liba"),allow_non_arm=True)
            b=gate.fingerprints(fake_lib(root,"libb",remove_one=True),allow_non_arm=True)
            self.assertEqual(b["found_count"],3)
            self.assertEqual(gate.compare(a,b)["results"][gate.TARGETS[2]],"MISSING")

    def test_malformed_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p=root/"notelf.so"
            p.write_bytes(b"invalid")
            with self.assertRaises(ValueError):
                gate.fingerprints(p,allow_non_arm=True)
            symlink=root/"alias.so"
            symlink.symlink_to(p)
            with self.assertRaises(ValueError):
                gate.headers(symlink)

    def test_production_requires_arm32_eabi5(self):
        with tempfile.TemporaryDirectory() as temp:
            p=fake_lib(Path(temp),"libhost")
            with self.assertRaisesRegex(ValueError,"ELF32"):
                gate.fingerprints(p)

    def test_cli_reports_no_patching_permission_on_identical_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p=fake_lib(root,"liba")
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                code=gate.main(["--reference-lib",str(p),
                                "--candidate-lib",str(p),
                                "--allow-host-fixtures"])
            self.assertEqual(code,0)
            parsed=json.loads(out.getvalue())
            self.assertTrue(parsed["comparison"]["all_four_function_bodies_identical"])
            self.assertFalse(parsed["device_patching_authorized"])
            self.assertFalse(parsed["candidate_firmware_114_version_verified"])
            self.assertFalse(parsed["comparison"]["safe_to_reuse_reference_addresses"])

if __name__=="__main__":
    unittest.main(verbosity=2)
