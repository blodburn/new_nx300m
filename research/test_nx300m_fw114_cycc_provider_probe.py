#!/usr/bin/env python3
"""Safe native-provider path selection tests; no vendor firmware included."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
import struct

import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import nx300m_fw114_cycc_provider_probe as probe


class CyccProviderPathTests(unittest.TestCase):
    def test_missing_optional_provider_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(probe.safe_sources(Path(t)),{})

    def test_symlink_stays_within_private_root(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            target=root/"libmm-type.so.0.0.0"
            target.write_bytes(b"x"*128)
            (root/"libmm-type.so").symlink_to(target.name)
            indexed=probe.safe_sources(root)
            self.assertEqual(indexed["libmm-type.so"],target.resolve())

    def test_escape_symlink_rejects(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/"private";root.mkdir()
            out=Path(t)/"outside.so";out.write_bytes(b"x"*128)
            (root/"libmm-type.so").symlink_to(out)
            with self.assertRaisesRegex(ValueError,"escapes"):
                probe.safe_sources(root)

    def test_realistic_cycc_destructor_arm_lifecycle_is_only_static(self):
        # BL to same-ELF local method, register BLX, then return.
        words=(0xe92d4008,0xeb000001,0xe12fff33,0xe8bd8008)
        data=struct.pack("<IIII",*words)
        result=probe.critical_arm_body(
            data,[(0x1000,16,0)],0x1000,16,
            {0x1010:"CYcc::Cleanup()"},{}
        )
        self.assertEqual(result["arm_word_count"],4)
        self.assertEqual(
            result["direct_ARM_BL_edges"][0]["local_native_function"],
            "CYcc::Cleanup()"
        )
        self.assertEqual(
            result["register_indirect_branches"][0]["register"],3
        )
        self.assertFalse(result["native_actual_pixel_release_verified"])
        self.assertFalse(result["no_hidden_or_indirect_release_proven"])

    def test_fw114_pool_mode_2_and_trivial_destructor_static_only(self):
        expected=(
            (0x2a00,0xe52db004),(0x2a04,0xe28db000),
            (0x2a08,0xe24dd00c),(0x2a0c,0xe50b0008),
            (0x2a10,0xe51b3008),(0x2a14,0xe1a00003),
            (0x2a18,0xe28bd000),(0x2a1c,0xe8bd0800),
            (0x2a20,0xe12fff1e),
        )
        required_pool=(
            (0x35398,0xe51b3014),(0x3539c,0xe3530002),
            (0x353a0,0x1a000002),(0x353a4,0xe51b3010),
            (0x353a8,0xe5933008),(0x353ac,0xea00000a),
            (0x353dc,0xe1a00003),
        )
        def records(pairs):
            return [{"pc":f"0x{pc:08x}","opcode":f"0x{op:08x}"}
                    for pc,op in pairs]
        providers={"provider_elfs":{
            "libmm-type.so":{"present":True,"target_symbols":[{
                "name":"CYcc::~CYcc()","address":"0x00002a00",
                "function_bytes":36,
                "offline_native_ARM_body":{
                    "arm_instruction_words":records(expected),
                    "direct_ARM_BL_edges":[],"register_indirect_branches":[],
                },
            }]},
            "libmm-photo.so":{"present":True,"target_symbols":[{
                "name":"CMemoryPool::GetAddr(eMemMode)",
                "address":"0x0003534c","function_bytes":172,
                "offline_native_ARM_body":{
                    "arm_instruction_words":records(required_pool),
                },
            }]},
        }}
        lifetime={
            "code_windows":[{"arm_words":[
                {"pc":"0x00034b70","arm_word":"0xe3a01002"},
                {"pc":"0x00034b74","arm_word":"0xebffd3bd"},
                {"pc":"0x00034b50","arm_word":"0x0a000022"},
            ]}],
            "internal_arm_branch_edges":[{
                "pc":"0x00034b50","target":"0x00034be0","condition":0,
            }],
        }
        proof=probe.proof_mode2_pool_and_trivial_cycc_destructor(
            providers,lifetime
        )
        self.assertTrue(proof[
            "memorypool_GetAddr_enum_2_reads_pool_object_offset8"])
        self.assertTrue(proof[
            "CYcc_destructor_has_no_direct_free_or_calls"])
        self.assertFalse(proof[
            "pixel_YCC_input_DMA_coherency_or_lifetime_proven"])
        self.assertFalse(proof["safe_film_engine_hook_permitted"])
        original=providers["provider_elfs"]["libmm-type.so"][
            "target_symbols"][0]["offline_native_ARM_body"]
        original["direct_ARM_BL_edges"]=[{"pc":"0x2a14"}]
        with self.assertRaisesRegex(ValueError,"destructor"):
            probe.proof_mode2_pool_and_trivial_cycc_destructor(providers,lifetime)
        original["direct_ARM_BL_edges"]=[]
        pool=providers["provider_elfs"]["libmm-photo.so"][
            "target_symbols"][0]["offline_native_ARM_body"][
                "arm_instruction_words"]
        pool[4]["opcode"]="0xe5933004"
        with self.assertRaisesRegex(ValueError,"mode 2"):
            probe.proof_mode2_pool_and_trivial_cycc_destructor(providers,lifetime)

    def test_alias_conflict_is_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            one=root/"a";two=root/"b";one.mkdir();two.mkdir()
            for location in (one,two):
                (location/"libmm-type.so").write_bytes(b"x"*128)
            with self.assertRaisesRegex(ValueError,"Ambiguous"):
                probe.safe_sources(root)


if __name__=="__main__":
    unittest.main(verbosity=2)
