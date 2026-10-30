#!/usr/bin/env python3
"""Host-only tests for static NX300M ELF symbol/dependency analysis.

All shared objects in this test are compiled from original tiny fixtures.
No camera binaries or firmware files are copied, executed or published.
"""
from __future__ import annotations
import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

MODULE=Path(__file__).with_name("nx300m_capture_elf_surface_audit.py")
SPEC=importlib.util.spec_from_file_location("nx_capture_symbol_audit",MODULE)
assert SPEC and SPEC.loader
audit=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

def compile_lib(root:Path,name:str,code:str,linked:list[str]|None=None)->Path:
    src=root/(name+".c")
    out=root/("lib"+name+".so")
    src.write_text(code,encoding="utf8")
    cmd=["gcc","-shared","-fPIC","-Wl,-soname,"+out.name,"-o",str(out),str(src)]
    if linked:cmd+=["-L",str(root)]+["-l"+x for x in linked]
    subprocess.run(cmd,check=True,capture_output=True)
    return out

class ElfAuditTests(unittest.TestCase):
    def test_real_host_elf_fixture_detects_capture_and_deps(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-static-elf-") as temp:
            root=Path(temp)
            helper=compile_lib(root,"helper","int fixture_helper(void){return 7;}\n")
            camera=compile_lib(root,"camera",
                "extern int fixture_helper(void);\n"
                "int convertUserData_DIALMODE(int i){return fixture_helper()+i;}\n"
                "int GetPictureWizardMode(void){return 1;}\n"
                "int CaptureStillImage(void){return 3;}\n",
                ["helper"])
            original=helper.read_bytes(),camera.read_bytes()
            report=audit.audit(root)
            self.assertEqual(report["shared_elf_count"],2)
            item=next(x for x in report["libraries"] if x["file"]=="libcamera.so")
            self.assertIn("libhelper.so",item["needed"])
            self.assertIn("libhelper.so",item["needed_present_in_extraction"])
            self.assertEqual(len(item["evidence"]["dial_mode_word"]["defined"]),1)
            self.assertEqual(len(item["evidence"]["picture_wizard_word"]["defined"]),1)
            self.assertEqual(len(item["evidence"]["capture_still_word"]["defined"]),1)
            self.assertEqual(len(item["evidence"]["efl_userspace_word"]["defined"]),0)
            self.assertFalse(report["picture_wizard_efl_connection_verified"])
            self.assertFalse(report["firmware_114_binary_identity_verified"])
            self.assertEqual((helper.read_bytes(),camera.read_bytes()),original)

    def test_missing_dependency_is_not_hidden(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-missing-dep-") as temp:
            root=Path(temp)
            compile_lib(root,"helper","int fixture_helper(void){return 7;}\n")
            camera=compile_lib(root,"camera",
                "extern int fixture_helper(void); int CaptureStillImage(void)"
                "{return fixture_helper();}",["helper"])
            (root/"libhelper.so").unlink()
            report=audit.audit(root)
            self.assertEqual(report["shared_elf_count"],1)
            self.assertIn("libhelper.so",report["libraries"][0]["needed_missing_from_extraction"])
            self.assertGreater(report["dependency_edges_missing"],0)
            self.assertTrue(camera.is_file())

    def test_nonelf_and_symlink_not_read(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-symlink-") as temp:
            root=Path(temp)
            (root/"fake.so").write_bytes(b"not an ELF")
            (root/"link.so").symlink_to(root/"fake.so")
            result=audit.audit(root)
            self.assertEqual(result["shared_elf_count"],0)

    def test_cli_summary_lacks_addresses_and_binary_bytes(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-summary-") as temp:
            root=Path(temp)
            compile_lib(root,"camera","int GetPictureWizardMode(void){return 3;}\n")
            stdout=io.StringIO()
            with redirect_stdout(stdout):
                code=audit.main(["--root",str(root),"--summary"])
            self.assertEqual(code,0)
            data=json.loads(stdout.getvalue())
            self.assertEqual(data["shared_elf_count"],1)
            self.assertNotIn("evidence",data["libraries"][0])
            self.assertNotIn("needed",data["libraries"][0])
            self.assertFalse(data["on_camera_symbol_execution_verified"])

    def test_rejects_missing_root_and_no_elf(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-empty-") as temp:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(audit.main(["--root",temp]),2)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--root",str(Path(temp)/"missing")]),2)

    def test_classifier_is_not_physical_dial_verification(self):
        for name in ("convertUserData_DIALMODE(int, int*)",
                     "GetPictureWizardMode()"):
            group="dial_mode_word" if "DIALMODE" in name else "picture_wizard_word"
            self.assertTrue(audit.GROUPS[group].search(name))
            self.assertFalse(audit.GROUPS["physical_key_input_word"].search(name))

    def test_bounds_on_symlink_and_invalid_tool(self):
        with tempfile.TemporaryDirectory(prefix="nx300m-bound-") as temp:
            root=Path(temp)
            (root/"elsewhere").mkdir()
            alias=root/"alias"
            alias.symlink_to(root/"elsewhere",target_is_directory=True)
            with self.assertRaises(ValueError):
                audit.audit(alias)
            with self.assertRaises(ValueError):
                audit.tool(["/nonexistent/camera_elf_tool"])

if __name__=="__main__":
    unittest.main(verbosity=2)
