#!/usr/bin/env python3
"""Pure synthetic ARM instruction fixtures for the read-only setter auditor."""
from __future__ import annotations
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

FILE=Path(__file__).with_name("nx300m_picture_wizard_setter_evidence.py")
SPEC=importlib.util.spec_from_file_location("nx_pw_setter_audit",FILE)
assert SPEC and SPEC.loader
audit=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

def fixture()->dict:
    asm=[]
    counter=0
    def append(s):
        nonlocal counter
        asm.append(f"0x{0x1000+counter*4:x}: {s}")
        counter+=1
    append("str r11, [sp,#-0x4]!")
    append("add r11, sp, #0x0")
    append("sub sp, sp, #0x44")
    append("str r0, [r11,#-0x40]")
    append("ldr r3, [r11,#-0x40]")
    append("cmp r3, #0x0")
    append("blt 0x00001028")
    append("ldr r3, [r11,#-0x40]")
    append("cmp r3, #0xc")
    append("movge r3, #0xc")
    append("b 0x00001030")
    append("mov r3, #0x0")
    append("str r3, [r11,#-0x40]")
    append("sub r3, r11, #0x38")
    for _ in range(13):
        append("mov r2, #0x0")
        append("str r2, [r3,#0x0]")
        append("add r3, r3, #0x4")
    for i in range(13):
        append(f"movw r3, 0x{0x1234+i:x}")
        append("movt r3, 0x22")
        append(f"str r3, [r11,#-0x{0x38-i*4:x}]")
    append("add sp, r11, #0x0")
    append("ldmia sp!,{r11}")
    append("bx lr")
    return {"normalized_result":{
        "procedure":{"name":"_Z18set_picture_wizardi","address":"0x1000"},
        "assembly":asm, "callers":[], "callees":[]}}

class StaticEvidenceTests(unittest.TestCase):
    def test_local_only_pattern_not_native_proof(self):
        result=audit.inspect(fixture())
        self.assertTrue(result["exact_reference_local_only_pattern"])
        self.assertEqual(result["candidate_pointer_count"],13)
        self.assertEqual((result["clamp_lower_bound"],result["clamp_upper_bound"]),(0,12))
        self.assertEqual(result["direct_calls"],[])
        self.assertFalse(result["real_picture_wizard_setter_effect_verified"])
        self.assertFalse(result["native_picture_wizard_mode_count_verified"])
        self.assertFalse(result["firmware_114_equivalence_verified"])
        self.assertFalse(result["device_patching_authorized"])

    def test_external_call_prevents_local_only_classification(self):
        d=fixture()
        d["normalized_result"]["assembly"][-1]=d["normalized_result"]["assembly"][-1].replace("bx lr","bl 0x00200400")
        result=audit.inspect(d)
        self.assertFalse(result["exact_reference_local_only_pattern"])
        self.assertEqual(len(result["direct_calls"]),1)

    def test_missing_pointer_entry_refuses_pattern(self):
        d=fixture()
        entries=d["normalized_result"]["assembly"]
        idx=next(i for i,s in enumerate(entries) if "movt r3" in s)
        entries[idx]=entries[idx].replace("movt r3","mov r3")
        self.assertEqual(audit.inspect(d)["candidate_pointer_count"],12)
        self.assertFalse(audit.inspect(d)["exact_reference_local_only_pattern"])

    def test_nonstack_store_rejects_pattern(self):
        d=fixture()
        lines=d["normalized_result"]["assembly"]
        idx=next(i for i,x in enumerate(lines) if "str r2, [r3,#0x0]" in x)
        lines[idx]=lines[idx].replace("[r3,#0x0]","[r9,#0x0]")
        self.assertFalse(audit.inspect(d)["exact_reference_local_only_pattern"])

    def test_wrong_procedure_and_invalid_order_rejected(self):
        d=fixture()
        d["normalized_result"]["procedure"]["name"]="set_other_function"
        with self.assertRaisesRegex(ValueError,"expected"):
            audit.inspect(d)
        d=fixture()
        d["normalized_result"]["assembly"][10]=d["normalized_result"]["assembly"][9]
        with self.assertRaisesRegex(ValueError,"ascending"):
            audit.inspect(d)

    def test_missing_or_malformed_evidence_rejected(self):
        for data in (None,{},{"normalized_result":{}},
                     {"normalized_result":{"procedure":{"name":"_Z18set_picture_wizardi"},"assembly":[]}}):
            with self.assertRaises(ValueError):audit.inspect(data)

    def test_cli_disables_patching_even_for_valid_pattern(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"evidence.json"
            p.write_text(json.dumps(fixture()),encoding="utf8")
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result=audit.main(["--evidence",str(p)])
            self.assertEqual(result,0)
            data=json.loads(stdout.getvalue())
            self.assertTrue(data["exact_reference_local_only_pattern"])
            self.assertFalse(data["device_patching_authorized"])
            alias=Path(folder)/"symlink.json"
            alias.symlink_to(p)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main(["--evidence",str(alias)]),2)

if __name__=="__main__":
    unittest.main(verbosity=2)
