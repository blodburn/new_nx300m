#!/usr/bin/env python3
"""Synthetic register argument windows, never vendor firmware code."""
from __future__ import annotations
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_pool_create_caller_audit as a

class PoolCallerWindows(unittest.TestCase):
    def test_bounded_arm_argument_window(self):
        code=(0xe1a00004,0xe1a01002,0xeb000000,0xe1a00000)
        value=a.caller_context(code,0x1000,0x1008)
        self.assertEqual(value["site"],"0x00001008")
        self.assertEqual(value["before"][0]["opcode"],"0xe1a00004")
        self.assertFalse(value["input_base_virtual_address_proven"])
        self.assertFalse(value["memory_pool_alloc_size_proven"])

    def test_lifecycle_only_filters_hotpath_calls(self):
        self.assertTrue(a.is_pool_lifecycle_call(
            "_ZN11CMemoryPool14CreateInstanceEj"))
        self.assertTrue(a.is_pool_lifecycle_call(
            "CMemoryPool::Destory()"))
        self.assertFalse(a.is_pool_lifecycle_call(
            "CMemoryPool::GetInstance()"))
        self.assertFalse(a.is_pool_lifecycle_call(
            "_ZN11CMemoryPool7GetAddrE8eMemMode"))

    def test_outside_and_unaligned_reject(self):
        words=(0xe1a00000,0xe1a01000)
        for site in (0xffc,0x1001,0x1008):
            with self.subTest(site=site),self.assertRaises(ValueError):
                a.caller_context(words,0x1000,site)
        with self.assertRaises(ValueError):
            a.caller_context(words,0x1001,0x1004)

if __name__=="__main__":
    unittest.main(verbosity=2)
