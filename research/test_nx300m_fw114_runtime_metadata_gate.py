#!/usr/bin/env python3
"""Host tests for passive camera runtime metadata; never touches a camera."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

import nx300m_fw114_runtime_metadata_gate as gate

FIELDS={
    "probe_scope":"read_only_metadata",
    "kernel_machine":"armv7l",
    "mem_total_kib":"256000",
    "mem_available_kib":"64000",
    "mem_free_kib":"18000",
    "camera_process":"observed",
    "camera_maps_readable":"observed",
    "camera_libmm_photo_loaded":"observed",
    "camera_libsif_loaded":"observed",
    "camera_libcapture_fw_loaded":"not_observed",
    "firmware_114_independently_authenticated":"no",
    "live_capture_callback_verified":"no",
    "live_ycc420_layout_verified":"no",
    "native_buffer_ownership_verified":"no",
    "calibration_recovery_verified":"no",
    "firmware_flash_permitted":"no",
    "firmware_write_performed":"no",
}

def sample(updates:dict|None=None)->str:
    p=FIELDS.copy()
    p.update(updates or {})
    return gate.HEADER+"\n"+"\n".join(f"{k}={v}" for k,v in p.items())+"\n"


class MetadataGateTests(unittest.TestCase):
    def test_valid_arm_metadata_only_never_claims_abi(self):
        r=gate.inspect_text(sample())
        self.assertEqual(r["report_integrity"],"PASS_FORMAT_ONLY")
        self.assertTrue(r["camera_process"]=="observed")
        for k in ("actual_camera_and_firmware_origin_attested",
                  "native_capture_callback_invoked",
                  "film_pixels_connected_to_native_encoder",
                  "native_isp_layout_and_ownership_verified",
                  "physical_camera_memory_budget_verified",
                  "camera_firmware_install_permitted"):
            self.assertIs(r[k],False)

    def test_real_shell_probe_on_linux_without_root(self):
        script=Path(__file__).resolve().parents[1]/"scripts/nx300m_fw114_runtime_metadata_probe.sh"
        proc=subprocess.run(["sh",str(script)],capture_output=True,text=True,
                            check=True,timeout=10)
        report=gate.inspect_text(proc.stdout)
        self.assertEqual(report["report_integrity"],"PASS_FORMAT_ONLY")
        self.assertNotIn("pid=",proc.stdout.lower())
        self.assertNotIn("serial",proc.stdout.lower())
        self.assertNotIn("mac_address",proc.stdout.lower())
        self.assertFalse(report["camera_firmware_install_permitted"])

    def test_incomplete_report_rejected(self):
        with self.assertRaisesRegex(ValueError,"Missing required"):
            gate.inspect_text(gate.HEADER+"\nprobe_scope=read_only_metadata\n")

    def test_duplicate_and_extra_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            gate.inspect_text(sample()+"camera_process=observed\n")
        with self.assertRaisesRegex(ValueError,"unexpected"):
            gate.inspect_text(sample()+"serial_number=secret\n")

    def test_no_runtime_hardware_proof_possible(self):
        for k in gate.BLOCKED:
            for value in ("yes","true","1","observed"):
                with self.subTest(k=k,value=value):
                    with self.assertRaisesRegex(ValueError,"Unproven"):
                        gate.inspect_text(sample({k:value}))

    def test_no_library_observed_when_maps_unavailable(self):
        r=gate.inspect_text(sample({
            "camera_maps_readable":"not_observed",
            "camera_libmm_photo_loaded":"not_observed",
            "camera_libsif_loaded":"not_observed"}))
        self.assertEqual(r["camera_maps_readable"],"not_observed")
        with self.assertRaisesRegex(ValueError,"without observed"):
            gate.inspect_text(sample({"camera_maps_readable":"not_observed"}))

    def test_missing_process_with_library_rejected(self):
        with self.assertRaisesRegex(ValueError,"without observed"):
            gate.inspect_text(sample({"camera_process":"not_observed"}))

    def test_memory_bounds_and_unknown(self):
        self.assertEqual(gate.inspect_text(sample({
            "mem_total_kib":"unknown",
            "mem_available_kib":"unknown",
            "mem_free_kib":"unknown"
        }))["mem_total_kib"],"unknown")
        with self.assertRaisesRegex(ValueError,"memory"):
            gate.inspect_text(sample({"mem_available_kib":"999999"}))
        with self.assertRaisesRegex(ValueError,"syntax"):
            gate.inspect_text(sample({"mem_total_kib":"-1"}))

    def test_injection_multiline_and_unicode_rejected(self):
        with self.assertRaises(ValueError):
            gate.inspect_text(sample()+"root_access=1\n")
        with self.assertRaises(ValueError):
            gate.inspect_text(sample().replace(
                "kernel_machine=armv7l","kernel_machine=$(id)"))
        with self.assertRaises(ValueError):
            gate.inspect_text(sample()+"\x00")

    def test_report_file_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/"original.txt"
            original.write_text(sample())
            link=Path(d)/"link.txt"
            link.symlink_to(original)
            self.assertEqual(gate.main(["--report",str(original)]),0)
            self.assertEqual(gate.main(["--report",str(link)]),2)


if __name__=="__main__":
    unittest.main(verbosity=2)
