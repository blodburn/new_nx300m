#!/usr/bin/env python3
"""Source-only ARM callsite tests; no vendor firmware or camera data."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nx300m_fw114_listener_registration_callers as auditor


class RegistrationCallers(unittest.TestCase):
    def test_exact_local_registration_call_only(self):
        candidates = {
            "identified_calls_truncated": False,
            "identified_callsite_evidence": [
                {"callsite":"0x00001008",
                 "target_kind":"local",
                 "target_symbol":"RegisterMemoryMapListner()"},
                {"callsite":"0x0000100c",
                 "target_kind":"import",
                 "target_symbol":"RegisterMemoryMapListner()"},
                {"callsite":"0x00001010",
                 "target_kind":"local",
                 "target_symbol":"RegisterMemoryMapListener()"},
            ],
        }
        self.assertEqual(auditor.direct_target_sites(candidates),
                         [{"callsite":"0x00001008",
                           "target_kind":"local",
                           "target_symbol":"RegisterMemoryMapListner()"}])
        self.assertEqual(auditor.direct_target_sites(
            {"identified_calls_truncated":False,
             "identified_callsite_evidence":[]}), [])

    def test_reject_truncated_or_invalid_inventory(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            auditor.direct_target_sites({
                "identified_calls_truncated":True,
                "identified_callsite_evidence":[]})
        with self.assertRaisesRegex(ValueError, "No bounded"):
            auditor.direct_target_sites({})

    def test_bounded_arm_call_windows_and_unknown_runtime(self):
        words = tuple(range(32))
        item = auditor.call_window(words, 0x1000, 0x1040)
        self.assertEqual(item["site"], "0x00001040")
        self.assertEqual(item["preceding_arm_words"][0]["pc"],"0x00001010")
        self.assertEqual(item["following_arm_words"][0]["pc"],"0x00001040")
        self.assertFalse(item["runtime_callback_registration_invoked"])
        self.assertFalse(item["camera_capture_event_or_thread_proven"])
        for site in (0xffc,0x1001,0x1080):
            with self.subTest(site=site), self.assertRaises(ValueError):
                auditor.call_window(words,0x1000,site)
        with self.assertRaises(ValueError):
            auditor.call_window(words,0x1001,0x1004)


if __name__ == "__main__":
    unittest.main(verbosity=2)
