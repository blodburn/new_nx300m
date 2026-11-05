#!/usr/bin/env python3
"""Locate candidate native ARM loads of verified listener GLOB_DAT slots.

This is a deliberately narrow static PIC/GOT data-flow scan of unofficial
NX300M FW1.14/1.15 libmm-photo.so. It does NOT prove a callback is registered,
invoked, or that an image/DMA memory region remains valid across a capture.
No firmware byte is executed, modified or uploaded.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_listener_callback_registration as callback
import nx300m_fw114_sif_callgraph as calls
import nx300m_native_jpeg_abi_boundary_audit as jpeg

MAX_FILE = 2 * 1024 * 1024
MAX_FUNCTIONS = 4000
MAX_FUNCTION_BYTES = 32768
MAX_CANDIDATES = 96


def ror32(value: int, bits: int) -> int:
    bits &= 31
    return ((value >> bits) | (value << (32 - bits))) & 0xffffffff if bits else value


def arm_operand2_immediate(word: int) -> int:
    return ror32(word & 255, 2 * ((word >> 8) & 15))


def arm_data_processing(word: int) -> tuple[str, int, int, int] | None:
    """Decode a small, exact ARM-state subset; ignore shift and Thumb forms."""
    if ((word >> 28) != 14 or ((word >> 26) & 3) != 0 or
        ((word >> 20) & 1)):
        return None
    immediate = bool((word >> 25) & 1)
    opcode = (word >> 21) & 15
    dst, src = (word >> 12) & 15, (word >> 16) & 15
    if opcode not in (4, 13):
        return None
    if immediate:
        value = arm_operand2_immediate(word)
    else:
        if word & 0xff0:  # register shift / shift-by-register unsupported
            return None
        value = word & 15
    if opcode == 13:
        return ("MOVI" if immediate else "MOVR", dst, src, value)
    return ("ADDI" if immediate else "ADDR", dst, src, value)


def arm_register_ldr(word: int) -> tuple[int, int, int] | None:
    """LDR rd,[rn,rm] with unshifted register offset, no writeback."""
    if ((word >> 28) != 14 or ((word >> 26) & 3) != 1 or
        ((word >> 25) & 1) != 1 or ((word >> 24) & 1) != 1 or
        ((word >> 22) & 1) != 0 or ((word >> 21) & 1) != 0 or
        ((word >> 20) & 1) != 1 or ((word >> 4) & 255) != 0):
        return None
    if (word >> 23) & 1 == 0:  # sign is resolved in the caller
        pass
    return (word >> 12) & 15, (word >> 16) & 15, word & 15


def scan_words(
    data: bytes,
    segments: list[tuple[int, int, int]],
    start: int,
    words: tuple[int, ...],
    target_slots: dict[int, str],
    function: str,
) -> list[dict]:
    """Conservative straight-line candidates; never control-flow proof.

    All conditionally executed instructions and direct B reset the simple
    register map. This intentionally misses more complex code and cannot be
    treated as an exhaustive callback-registration search.
    """
    if (not words or start & 3 or len(words) * 4 > MAX_FUNCTION_BYTES or
        len(target_slots) > 32):
        raise ValueError("Invalid bounded ARM function / listener slots")
    known: list[tuple[int, tuple[str, ...]] | None] = [None] * 16
    out = []
    for i, word in enumerate(words):
        pc = start + 4 * i
        if (word >> 28) != 14:
            known = [None] * 16
            continue
        if ((word >> 25) & 7) == 5:  # B or BL immediate
            if (word >> 24) & 1:
                for r in (0, 1, 2, 3, 12):
                    known[r] = None
            else:
                known = [None] * 16
            continue
        if (word & 0x0ffffff0) in (0x012fff10, 0x012fff30):
            known = [None] * 16
            continue

        ld = sif.decode_ldr_immediate(word)
        if ld:
            dst, base, off = ld["dst"], ld["base"], ld["offset"]
            if base == 15:
                vaddr = (pc + 8 + off) & 0xffffffff
                try:
                    offset = elf.file_range_for_vaddr(segments, vaddr, 4)
                except ValueError:
                    known[dst] = None
                    continue
                if offset + 4 > len(data):
                    known[dst] = None
                    continue
                value = struct.unpack_from("<I", data, offset)[0]
                known[dst] = (value, (f"LDR_LITERAL@0x{pc:08x}",
                                      f"literal@0x{vaddr:08x}"))
            else:
                base_state = known[base]
                if base_state:
                    address = (base_state[0] + off) & 0xffffffff
                    if address in target_slots:
                        out.append({
                            "function": function,
                            "load_site": f"0x{pc:08x}",
                            "load_opcode": f"0x{word:08x}",
                            "read_type": "LDR_IMM",
                            "GLOB_DAT_slot": f"0x{address:08x}",
                            "target_listener": target_slots[address],
                            "local_address_provenance":
                                list(base_state[1]) + [f"LDR@0x{pc:08x}"],
                            "is_registration_or_runtime_invocation_proof": False,
                        })
                known[dst] = None
            continue

        ldreg = arm_register_ldr(word)
        if ldreg:
            dst, base, index = ldreg
            b, j = known[base], known[index]
            if b and j:
                signed = j[0] if (word >> 23) & 1 else -j[0]
                address = (b[0] + signed) & 0xffffffff
                if address in target_slots:
                    out.append({
                        "function": function,
                        "load_site": f"0x{pc:08x}",
                        "load_opcode": f"0x{word:08x}",
                        "read_type": "LDR_REG",
                        "GLOB_DAT_slot": f"0x{address:08x}",
                        "target_listener": target_slots[address],
                        "local_address_provenance":
                            list(b[1]) + list(j[1]) + [f"LDR@0x{pc:08x}"],
                        "is_registration_or_runtime_invocation_proof": False,
                    })
            known[dst] = None
            continue

        op = arm_data_processing(word)
        if op:
            kind, dst, src, arg = op
            origin = None
            if kind == "MOVI":
                origin = (arg, (f"MOV_LITERAL@0x{pc:08x}",))
            elif kind == "MOVR" and known[arg]:
                origin = (known[arg][0], known[arg][1] +
                          (f"MOV@0x{pc:08x}",))
            elif kind in ("ADDI", "ADDR"):
                lhs = (pc + 8, (f"PC@0x{pc:08x}",)) if src == 15 else known[src]
                rhs = ((arg, ()) if kind == "ADDI" else
                       (known[arg] if arg != 15 else
                        (pc + 8, (f"PC@0x{pc:08x}",))))
                if lhs and rhs:
                    origin = ((lhs[0] + rhs[0]) & 0xffffffff,
                              lhs[1] + rhs[1] + (f"ADD@0x{pc:08x}",))
            known[dst] = origin
            continue

        # Invalidate possible writers rather than reusing stale registers.
        class2 = (word >> 26) & 3
        if class2 == 0:
            known[(word >> 12) & 15] = None
        elif class2 == 1:
            if (word >> 20) & 1:  # other load form
                known[(word >> 12) & 15] = None
            if (word >> 21) & 1:  # writeback
                known[(word >> 16) & 15] = None
        elif ((word >> 25) & 7) == 4 and ((word >> 20) & 1):
            known = [None] * 16
        if len(out) > MAX_CANDIDATES:
            raise ValueError("Unbounded native listener GOT consumers")
    return out


def bounded_arm_window(words: tuple[int, ...], start: int, site: int,
                       before: int = 10, after: int = 30) -> list[dict]:
    """Report limited ARM words around one verified static relocation read."""
    if (not words or start & 3 or (site - start) & 3 or
        site < start or site >= start + 4 * len(words) or
        len(words) * 4 > MAX_FUNCTION_BYTES or
        not 0 <= before <= 64 or not 0 <= after <= 64):
        raise ValueError("Invalid bounded native callback reader window")
    i = (site - start) // 4
    return [{"pc": f"0x{start+4*j:08x}",
             "word": f"0x{words[j]:08x}"}
            for j in range(max(0, i-before), min(len(words), i+after+1))]


def inspect(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not (
        1024 <= path.stat().st_size <= MAX_FILE
    ):
        raise ValueError("Bounded private photo ARM ELF required")
    raw = path.read_bytes()
    segments = elf.program_headers(path)
    listener = callback.inspect(path)
    slots = {}
    for name in callback.TARGETS:
        locations = listener["listener_pointer_evidence"][name][
            "explicit_dynamic_symbol_relocations"]
        matches = [x for x in locations if x["relocation_type"] ==
                   "R_ARM_GLOB_DAT"]
        if len(matches) != 1:
            raise ValueError("Expected unique native GLOB_DAT listener slot")
        slot = int(matches[0]["relocation_address"], 16)
        if slot in slots:
            raise ValueError("Conflicting listener GOT slot")
        slots[slot] = name
    symbols = sif.symbol_index(sif.arm.offline_tool(
        ["readelf", "-Ws", str(path)]))
    candidates = []
    registration = None
    defined = calls.defined_symbols(path)
    relocations = jpeg.relocations(sif.arm.offline_tool(
        ["readelf", "-Wr", str(path)]))
    examined = 0
    methods = [(name, item) for name, item in sorted(symbols.items())
               if item["kind"] == "FUNC" and
               4 <= item["size"] <= MAX_FUNCTION_BYTES and
               not (item["address"] & 3)]
    if not 1 <= len(methods) <= MAX_FUNCTIONS:
        raise ValueError("Invalid ARM ELF function inventory")
    for name, item in methods:
        address, size = item["address"], item["size"]
        if size & 3:
            continue
        try:
            offset = elf.file_range_for_vaddr(segments, address, size)
        except ValueError:
            continue
        words = struct.unpack_from("<" + "I" * (size // 4), raw, offset)
        examined += 1
        matched = scan_words(raw, segments, address, words, slots, name)
        candidates.extend(matched)
        if name == "RegisterMemoryMapListner()":
            if registration is not None:
                raise ValueError("Ambiguous native listener registration symbol")
            graph = calls.collect_edges(raw, segments, address, size,
                                        defined, relocations)
            if graph["identified_calls_truncated"]:
                raise ValueError("Truncated listener registration callgraph")
            registration = {
                "native_function": name,
                "function_address": f"0x{address:08x}",
                "function_bytes": size,
                "actual_GOT_load_sites": matched,
                "native_direct_call_candidates":
                    graph["identified_callsite_evidence"],
                "arm_word_windows": [
                    {"load_site": x["load_site"],
                     "words": bounded_arm_window(
                         words, address, int(x["load_site"], 16))}
                    for x in matched
                ],
                "callback_registration_call_verified": False,
                "camera_thread_or_callback_execution_verified": False,
            }
        if len(candidates) > MAX_CANDIDATES:
            raise ValueError("Too many listener GOT readers")
    if registration is None or set(
        x["target_listener"] for x in registration["actual_GOT_load_sites"]
    ) != set(callback.TARGETS):
        raise ValueError("Missing both listener GOT loads in registration owner")
    return {
        "scope": "UNOFFICIAL_FW114_PHOTO_ARM_STATIC_GOT_CONSUMERS_ONLY",
        "focused_registration_symbol": registration,
        "libmm_photo_sha256": hashlib.sha256(raw).hexdigest(),
        "listener_GLOB_DAT_slots":
            {name: f"0x{site:08x}" for site, name in sorted(slots.items())},
        "scanned_ARM_function_count": examined,
        "possible_listener_GOT_loads": candidates,
        "candidate_count": len(candidates),
        "exhaustive_registration_search": False,
        "actual_camera_callback_invocation_proven": False,
        "physical_capture_DMA_buffer_lifetime_verified": False,
        "camera_firmware_flash_permitted": False,
    }


def compare_versions(p114: Path, p115: Path) -> dict:
    a, b = inspect(p114), inspect(p115)
    return {
        "fw114": a, "fw115": b,
        "same_photo_ELF_sha256": a["libmm_photo_sha256"] ==
                                  b["libmm_photo_sha256"],
        "same_GLOB_DAT_slot_addresses":
            a["listener_GLOB_DAT_slots"] == b["listener_GLOB_DAT_slots"],
        "on_camera_callback_registration_proven": False,
        "firmware_flash_permitted": False,
    }
