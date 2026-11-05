#!/usr/bin/env python3
"""Offline NX300M FW1.14/FW1.15 memory-map size safety contract.

This examines real, unofficial firmware ARM32 instructions read ONLY
inside a private ephemeral CI runner. It does not execute firmware,
observe real allocations, or approve a camera firmware patch.

Observed pool layout:
  pool[0] = sysmmap base
  pool[4] = base + 30 MiB
  pool[8] = base + 40 MiB
Therefore any allocation containing these pointer ranges requires at least
40 MiB. The actual descriptor requested size, actual mapping size, and DMA
coherency cannot be inferred from pointer arithmetic.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_pool_slot8_writer_audit as pool
import nx300m_fw114_jfif_r6_arg_provenance as arm

MAX_ELF = 2 * 1024 * 1024
MIN_ARENA_BYTES = 40 * 1024 * 1024
MAX_WINDOW = 80

ARM_EXPECTED = {
    "AllocListener": {
        0x00034e24: 0xe3530000,  # strcmp outcome compared to zero
        0x00034e28: 0x1a000009,  # BNE -> ordinary sysmmap_alloc path
        0x00034e2c: 0xe51b301c,  # cached branch descriptor
        0x00034e30: 0xe5932004,  # cached size descriptor+4 -> r2
        0x00034e34: 0xe51b301c,
        0x00034e38: 0xe593300c,  # cached mode descriptor+12
        0x00034e3c: 0xe1a00002,  # cached requested size -> r0
        0x00034e40: 0xe1a01003,  # cached mode -> r1
        0x00034e44: 0xebffcd3c,  # BL sysmmap_cached_alloc (native relocation)
        0x00034e50: 0xea000008,  # B -> common CreateInstance block
        0x00034e54: 0xe51b301c,  # ordinary descriptor from fp-28
        0x00034e58: 0xe5932004,  # descriptor+4 -> r2 requested size
        0x00034e5c: 0xe51b301c,
        0x00034e60: 0xe593300c,  # descriptor+12 -> r3 mmap mode
        0x00034e64: 0xe1a00002,  # syscall arg r0 = requested size
        0x00034e68: 0xe1a01003,  # syscall arg r1 = mode
        0x00034e6c: 0xebffca32,  # BL sysmmap_alloc
        0x00034e78: 0xe51b0010,  # common r0 from mapped pointer
        0x00034e7c: 0xebffc8ae,  # BL CMemoryPool::CreateInstance
    },
    "FreeListener": {
        0x00035044: 0xe51b3018,  # callback descriptor from fp-24
        0x00035048: 0xe5932004,  # descriptor+4 -> r2 free length
        0x0003504c: 0xe51b3010,  # pool base previously read
        0x00035050: 0xe1a00002,  # sysmmap_free arg r0 = length
        0x00035054: 0xe1a01003,  # sysmmap_free arg r1 = pool base
    },
}

CONTRACT = {
    "minimum_region_bytes": MIN_ARENA_BYTES,
    "pool_slot0_offset_bytes": 0,
    "pool_slot4_offset_bytes": 30 * 1024 * 1024,
    "pool_slot8_offset_bytes": MIN_ARENA_BYTES,
    "alloc_size_descriptor_offset_bytes": 4,
    "free_size_descriptor_offset_bytes": 4,
}


def assert_contract(sample_alloc_bytes: int, sample_free_bytes: int) -> dict:
    """A *real* runtime measurement is needed; never fabricate a sample."""
    if (type(sample_alloc_bytes) is not int or
        type(sample_free_bytes) is not int):
        raise ValueError("Require explicit integer size samples")
    if (sample_alloc_bytes < MIN_ARENA_BYTES or
        sample_free_bytes < MIN_ARENA_BYTES):
        raise ValueError("Memory map below pool[8] pointer lower bound")
    if sample_alloc_bytes != sample_free_bytes:
        raise ValueError("Allocation/free length mismatch")
    return {
        "size_lower_bound_satisfied": True,
        "identical_alloc_and_free_size": True,
        "actual_runtime_dma_coherency_established": False,
        "firmware_flash_permitted": False,
    }


def read_arm_words(
    image: bytes, loads: list[tuple[int, int, int]],
    address: int, size: int
) -> tuple[int, ...]:
    if (address & 3 or size & 3 or not 4 <= size <= 2048):
        raise ValueError("Bad bounded native ARM function")
    pos = elf.file_range_for_vaddr(loads, address, size)
    if pos + size > len(image):
        raise ValueError("Truncated mapped ELF function")
    return struct.unpack_from("<" + "I" * (size // 4), image, pos)


def exact_listener_words(
    words: tuple[int, ...], start: int, name: str
) -> dict:
    if name not in ARM_EXPECTED:
        raise ValueError("Unknown native mmap callback")
    sites = ARM_EXPECTED[name]
    for pc, opcode in sites.items():
        idx = (pc - start) // 4
        if (pc < start or (pc - start) & 3 or idx >= len(words) or
            words[idx] != opcode):
            raise ValueError(f"Changed ARM descriptor size path {name} {pc:#x}")

    size_sites = ((0x00034e30, 0x00034e58)
                  if name == "AllocListener" else (0x00035048,))
    for pc in size_sites:
        instruction = words[(pc - start) // 4]
        mem = arm.decode_mem_word(instruction)
        if (mem is None or mem["kind"] != "LDR" or
            mem["offset"] != 4 or mem["base_register"] != 3 or
            mem["data_register"] != 2):
            raise ValueError("ARM descriptor size no longer loaded from r3+4")
    if name == "AllocListener":
        # Cond=NE, branch ARM PC+8+imm24*4; exact branch to normal path.
        branch_word = words[(0x34e28-start)//4]
        ordinary_target = 0x34e28+8+(branch_word & 0xffffff)*4
        common_word = words[(0x34e50-start)//4]
        common_target = 0x34e50+8+(common_word & 0xffffff)*4
        if ordinary_target != 0x34e54 or common_target != 0x34e78:
            raise ValueError("Changed cached vs ordinary map branch targets")
    return {
        "callback": name,
        "native_descriptor_size_load": f"0x{size_sites[-1]:08x}",
        "all_descriptor_size_load_sites": [
            f"0x{pc:08x}" for pc in size_sites],
        "cached_and_plain_paths_use_same_descriptor_size_offset":
            name == "AllocListener",
        "both_paths_join_before_CreateInstance":
            name == "AllocListener",
        "descriptor_size_offset": 4,
        "verified_arm_opcodes": {
            f"0x{pc:08x}": f"0x{op:08x}" for pc, op in sites.items()
        },
        "actual_descriptor_size_bytes_observed": False,
        "runtime_mapping_bounds_verified": False,
    }


def bounded_window(
    words: tuple[int, ...], start: int, begin: int, end: int
) -> list[dict]:
    if (start & 3 or begin & 3 or end & 3 or begin >= end or
        begin < start or end > start + len(words) * 4 or
        (end - begin) // 4 > MAX_WINDOW):
        raise ValueError("Invalid bounded ARM callback context")
    return [
        {"pc": f"0x{pc:08x}",
         "word": f"0x{words[(pc - start) // 4]:08x}"}
        for pc in range(begin, end, 4)
    ]


def inspect(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file() or
        not 1024 <= path.stat().st_size <= MAX_ELF):
        raise ValueError("Require bounded private ARM32 libmm-photo ELF")
    image = path.read_bytes()
    loads = elf.program_headers(path)
    syms = sif.symbol_index(sif.arm.offline_tool(
        ["readelf", "-Ws", str(path)]))
    ctor = sif.select(syms, "CMemoryPool::CMemoryPool(", "FUNC")
    ctor_words = read_arm_words(image, loads, ctor["address"], ctor["size"])
    layout = pool.prove_ctor_immutable_slot_base(
        ctor_words, ctor["address"])
    if layout["field_offset_to_base"] != {
        "0": 0, "4": 30*1024*1024, "8": MIN_ARENA_BYTES
    }:
        raise ValueError("Pool pointer layout changed from exact ARM proof")
    listeners = {}
    for name in ("AllocListener", "FreeListener"):
        fn = sif.select(syms, name, "FUNC")
        words = read_arm_words(image, loads, fn["address"], fn["size"])
        listeners[name] = exact_listener_words(
            words, fn["address"], name)
        if name == "AllocListener":
            listeners[name]["allocation_branch_words"] = bounded_window(
                words, fn["address"], 0x00034e00, 0x00034e80)
        else:
            listeners[name]["release_branch_words"] = bounded_window(
                words, fn["address"], 0x00035024, 0x0003506c)
    return {
        "scope": "UNOFFICIAL_FW114_NATIVE_ARM_STATIC_SIZE_CONTRACT",
        "libmm_photo_sha256": hashlib.sha256(image).hexdigest(),
        "static_contract": CONTRACT,
        "pool_constructor": layout["constructor"],
        "pool_constructor_native_address": layout["native_address"],
        "listeners": listeners,
        "descriptor_size_bytes_at_runtime": None,
        "actual_sysmmap_allocated_region_bytes": None,
        "actual_free_region_size_bytes": None,
        "mapping_meets_40MiB_minimum": None,
        "cached_and_normal_allocation_use_descriptor_plus4_size": True,
        "cached_allocation_returned_byte_length_verified": False,
        "live_pixel_buffer_or_dma_ownership_verified": False,
        "camera_firmware_flash_permitted": False,
    }


def compare_versions(fw114: Path, fw115: Path) -> dict:
    a, b = inspect(fw114), inspect(fw115)
    if a["static_contract"] != b["static_contract"]:
        raise ValueError("ARM pool size contract differs by firmware")
    return {
        "fw114": a, "fw115": b,
        "libmm_photo_elf_identical":
            a["libmm_photo_sha256"] == b["libmm_photo_sha256"],
        "descriptor_size_observed_on_camera": False,
        "dma_coherency_proven": False,
        "firmware_flash_permitted": False,
    }
