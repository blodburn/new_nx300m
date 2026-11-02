#!/usr/bin/env python3
"""Regression of numerical SpektraFilm profile smoke report (no profile data)."""
import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).with_name("nx300m_spektrafilm_real_profile_qa.py")
spec=importlib.util.spec_from_file_location("spektrafilm_quality",p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def report(peak=5.0,avg=1.1):
    return {
      "status":"PASS","output_nodes":5832,"input_encoding":"sRGB",
      "output_encoding":"sRGB","nx_lut_encoding":"linear-light RGB12",
      "camera_firmware_installable":False,
      "source_sha256":"a"*64,"nx18_text_sha256":"b"*64,
      "quality":{"max_abs_channel_8bit":peak,
                 "mean_max_channel_8bit":avg}
    }
class SmokeTest(unittest.TestCase):
    def test_pass(self):
        r=module.evaluate(report())
        self.assertEqual(r["decision"],"PASS_NUMERICAL_RESCALING_ONLY")
        self.assertFalse(r["camera_deployment_allowed"])
        self.assertFalse(r["firmware_114_verified"])
    def test_peak_reject(self):
        self.assertEqual(module.evaluate(report(20,1))["decision"],"REJECT_NUMERICAL_RESCALING")
    def test_mean_reject(self):
        self.assertEqual(module.evaluate(report(8,3))["decision"],"REJECT_NUMERICAL_RESCALING")
    def test_malicious_firmware_claim_rejected(self):
        r=report()
        r["camera_firmware_installable"]=True
        with self.assertRaises(ValueError):module.evaluate(r)
    def test_corrupt_report_rejected(self):
        r=report()
        r["output_nodes"]=17
        with self.assertRaises(ValueError):module.evaluate(r)
    def test_invalid_errors_rejected(self):
        with self.assertRaises(ValueError):module.evaluate(report(-1,1))
        with self.assertRaises(ValueError):module.evaluate(report(1,5))
if __name__ == "__main__":
    unittest.main(verbosity=2)
