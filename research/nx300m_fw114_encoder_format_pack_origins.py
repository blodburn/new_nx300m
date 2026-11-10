#!/usr/bin/env python3
"""Trace Y/C format and packing operands at NX300M FW1.14 JPEG callsite.

Strictly OFFLINE. Input is ARM32 instructions from an extracted, unauthenticated
third-party firmware image. This tool does not execute firmware or prove real
capture layout, DMA lifetime, a safe native hook, or flash readiness.

The YCC type and pack values passed to DscImage::EncodeYCC come from
[fp,-40] and [fp,-44]. A single local STR to either slot does NOT establish
the runtime value or exclude stack aliases, branch-dependent definitions,
interrupts, or other pointer writers. No color layout is inferred.
"""
from __future__ import annotations

import hashlib
import struct

import nx300m_fw114_jfif_r6_arg_provenance as arm
import nx300m_fw114_photo_ycc_copy_boundary as photo

START = 0x00034b18
BODY_BYTES = 644
ENCODER_CALL = 0x00034d78
FIELDS = {
    "eImgYCCType": {"slot": -40, "load_site": 0x34d48,
                    "expected_load": 0xe51b3028},
    "eImgYCCPackType": {"slot": -44, "load_site": 0x34d50,
                        "expected_load": 0xe51b302c},
}
MAX_CANDIDATE_STORES = 24

# Real opcode witnesses from the independently extracted third-party
# FW1.14/1.15 libmm-photo.so CI study. Each adjacent MOV immediate and
# direct STR to the frame slot is pinned. This is NOT a runtime value proof.
# (field-name, direct-store PC, preceding MOV immediate)
PINNED_DIRECT_WRITERS = {
    "eImgYCCType": (
        (0x34be4, 0),
        (0x34c10, 0),
        (0x34c40, 1),
    ),
    "eImgYCCPackType": (
        (0x34c48, 0),
        (0x34c74, 1),
        (0x34ca4, 0),
    ),
}


def pin_known_arm_direct_writer_values(proof: dict) -> dict:
    """Pin the six actual source-backed direct stores; never infer branches."""
    fields = proof["fields"]
    if set(fields) != set(PINNED_DIRECT_WRITERS):
        raise ValueError("FW Y/C type/pack writer fields changed")
    evidence = {}
    for name, exact in PINNED_DIRECT_WRITERS.items():
        stores = fields[name]["direct_frame_pointer_store_candidates"]
        observed = []
        for item in stores:
            move = item["immediate_preceding_mov_candidate"]
            if (item["source_register"] != "r3" or
                item["condition"] != "AL" or not move or
                move["kind"] != "MOV_IMM" or
                item["store_opcode"] != (
                    "0xe50b3028" if name == "eImgYCCType" else "0xe50b302c"
                )):
                raise ValueError("Unexpected native field writer A32 operation")
            observed.append((int(item["store_site"], 16), move["immediate"]))
        if tuple(observed) != exact:
            raise ValueError("Changed actual FW1.14/1.15 Y/C type/pack writer")
        evidence[name] = {
            "direct_store_count": len(observed),
            "verified_direct_store_sites":
                [f"0x{site:08x}" for site, _ in observed],
            "statically_assigned_immediate_candidates":
                [value for _, value in observed],
            "direct_store_values_within_zero_or_one":
                all(value in (0, 1) for _, value in observed),
            "runtime_path_values_or_precedence_proven": False,
            "unknown_indirect_stack_slot_writers_excluded": False,
            "native_pixels_are_BT601_NV12_or_other_pack_proven": False,
        }
    return {
        "pinned_fw114_115_known_direct_stores": evidence,
        "six_native_opcodes_and_preceding_immediates_pinned": True,
        "source_branch_path_exhaustive": False,
        "camera_firmware_flash_permitted": False,
    }



# Actual FW1.14/1.15 A32 control flow, independently observed in the
# offline mirror ELF. A zero CMP result causes a BEQ that skips the direct
# MOV/STR pair. Not every field writer has an adjacent BEQ; this is NOT
# a global path or runtime enum-value proof.
#
# (direct store PC, UXTB PC, CMP PC, BEQ PC, BEQ opcode, skip target)
PINNED_LOCAL_BRANCH_GUARDS = {
    "eImgYCCType": (
        (0x34c10, 0x34c00, 0x34c04, 0x34c08, 0x0a000002, 0x34c18),
        (0x34c40, 0x34c30, 0x34c34, 0x34c38, 0x0a000001, 0x34c44),
    ),
    "eImgYCCPackType": (
        (0x34c74, 0x34c64, 0x34c68, 0x34c6c, 0x0a000002, 0x34c7c),
        (0x34ca4, 0x34c94, 0x34c98, 0x34c9c, 0x0a000001, 0x34ca8),
    ),
}
EXPECTED_UXTB_R3_R3 = 0xe6ef3073
EXPECTED_CMP_R3_ZERO = 0xe3530000


def a32_beq_direct_target(word: int, site: int) -> int:
    """Decode A32 conditional BEQ imm24 to PC-relative target.

    This only decodes a direct BEQ; it does not infer the condition flags'
    provenance across arbitrary instructions or virtual/indirect calls.
    """
    if (type(word) is not int or type(site) is not int or
        not 0 <= word <= 0xffffffff or site < 0 or site & 3 or
        (word >> 24) != 0x0a):
        raise ValueError("Expected an aligned ARM-state BEQ immediate")
    signed_imm = word & 0xffffff
    if signed_imm & 0x800000:
        signed_imm -= 0x1000000
    target = site + 8 + signed_imm * 4
    if target < 0 or target > 0xffffffff or target & 3:
        raise ValueError("Invalid A32 BEQ target")
    return target


def pin_local_ycc_branch_guards(
    words: tuple[int, ...], direct_pins: dict
) -> dict:
    """Verify four zero-tested local skip edges from real A32 code.

    A taken BEQ skips an adjacent direct store. It DOES NOT prove that the
    store runs when BEQ is not taken, since other paths/calls and aliasing
    are not modeled. It never identifies NV12/NV21/CbCr byte layouts.
    """
    if (len(words) != BODY_BYTES // 4 or
        any(type(w) is not int or not 0 <= w <= 0xffffffff for w in words) or
        set(direct_pins.get("pinned_fw114_115_known_direct_stores", {})) !=
        set(PINNED_LOCAL_BRANCH_GUARDS)):
        raise ValueError("Wrong native branch guard body or direct writer pins")
    result = {}
    for name, guards in PINNED_LOCAL_BRANCH_GUARDS.items():
        pins = direct_pins["pinned_fw114_115_known_direct_stores"][name]
        known_stores = {int(pc, 16) for pc in pins["verified_direct_store_sites"]}
        observed = []
        for store_pc, byte_pc, cmp_pc, branch_pc, opcode, skip_target in guards:
            if (store_pc not in known_stores or
                not START <= byte_pc < cmp_pc < branch_pc < store_pc <
                ENCODER_CALL or
                cmp_pc != byte_pc + 4 or branch_pc != cmp_pc + 4 or
                store_pc != branch_pc + 8 or
                words[(byte_pc - START)//4] != EXPECTED_UXTB_R3_R3 or
                words[(cmp_pc - START)//4] != EXPECTED_CMP_R3_ZERO or
                words[(branch_pc - START)//4] != opcode or
                words[(store_pc-4-START)//4] not in
                (0xe3a03000, 0xe3a03001)):
                raise ValueError(
                    f"Changed native {name} zero-test/branch/field-store path"
                )
            computed_target = a32_beq_direct_target(opcode, branch_pc)
            if (computed_target != skip_target or
                not branch_pc < store_pc < computed_target):
                raise ValueError("BEQ no longer skips the expected direct store")
            observed.append({
                "store_site": f"0x{store_pc:08x}",
                "byte_extract_site": f"0x{byte_pc:08x}",
                "byte_extract_instruction": "UXTB r3,r3",
                "zero_compare_site": f"0x{cmp_pc:08x}",
                "compare_instruction": "CMP r3,#0",
                "branch_site": f"0x{branch_pc:08x}",
                "branch_opcode": f"0x{opcode:08x}",
                "taken_when": "r3_equals_zero",
                "branch_target": f"0x{computed_target:08x}",
                "bypassed_store_site": f"0x{store_pc:08x}",
                "branch_takes_skip_of_this_direct_store": True,
                "runtime_r3_input_origin_proven": False,
                "fallthrough_store_guaranteed": False,
            })
        result[name] = {
            "pinned_local_beq_skip_edges": observed,
            "direct_stores_without_nearby_pinned_beq": [
                f"0x{pc:08x}" for pc in sorted(
                    known_stores - {x[0] for x in guards}
                )
            ],
            "full_reaching_definitions_or_alias_analysis_complete": False,
            "actual_camera_runtime_branch_outcome_proven": False,
        }
    return {
        "direct_zero_test_guard_count": sum(
            len(value["pinned_local_beq_skip_edges"])
            for value in result.values()
        ),
        "fields": result,
        "direct_beq_skip_targets_source_backed": True,
        "all_function_paths_or_external_calls_resolved": False,
        "live_ycc_format_or_chroma_pack_verified": False,
        "camera_dma_buffer_ownership_verified": False,
        "firmware_flash_permitted": False,
    }


# Exact version-local native imported getter calls and their adjacent A32
# return-value-to-boolean sequence. Verified by independent PLT relocation
# name resolution (no guessed symbols from a nearby BL instruction).
# (call site, getter symbol, associated guarded field writer site)
GETTER_CALLS = {
    "eImgYCCType": (
        (0x34bec, "CYcc::GetType()", 0x34c10, 0),
        (0x34c1c, "CYcc::GetType()", 0x34c40, 1),
    ),
    "eImgYCCPackType": (
        (0x34c50, "CYcc::GetScanMode()", 0x34c74, 0),
        (0x34c80, "CYcc::GetScanMode()", 0x34ca4, 1),
    ),
}
GETTER_BOOLEAN_SEQUENCE = (
    (4, 0xe1a03000, "MOV r3,r0"),
    (8, None, "CMP r3,#case"),
    (12, 0x13a03000, "MOVNE r3,#0"),
    (16, 0x03a03001, "MOVEQ r3,#1"),
    (20, EXPECTED_UXTB_R3_R3, "UXTB r3,r3"),
    (24, EXPECTED_CMP_R3_ZERO, "CMP r3,#0"),
)
# A nonzero getter result bypasses the first field write and enters the
# fallback getter block; after first store an unconditional B bypasses it.
FALLBACK_SKIP_BRANCHES = (
    (0x34c14, 0xea00000a, 0x34c44, 0x34c18),
    (0x34c78, 0xea00000a, 0x34ca8, 0x34c7c),
)


def pin_getter_result_boolean_paths(
    words: tuple[int, ...], named_calls: list[dict],
    source_guards: dict,
) -> dict:
    """Prove four local imported getter -> r0 -> r3 -> equality sequences.

    The getter names must be resolved via actual .rel.plt symbols. No real
    camera callback execution, native getter argument object identity,
    indirect stack aliases or full reaching definitions are proven.
    """
    if (len(words) != BODY_BYTES//4 or
        any(type(w) is not int or not 0 <= w <= 0xffffffff for w in words) or
        source_guards.get("direct_zero_test_guard_count") != 4):
        raise ValueError("Wrong FW native getter-source body/branch guards")
    actual = {}
    for edge in named_calls:
        if not isinstance(edge, dict):
            raise ValueError("Wrong native imported-call witness format")
        site = edge.get("callsite")
        if not isinstance(site, str):
            raise ValueError("Invalid native getter callsite record")
        try:
            address = int(site,16)
        except ValueError as exc:
            raise ValueError("Invalid imported callsite address") from exc
        if address in actual:
            raise ValueError("Ambiguous FW native imported getter callsite")
        actual[address] = edge
    evidence = {}
    for field, pairs in GETTER_CALLS.items():
        native_guards = source_guards["fields"][field]["pinned_local_beq_skip_edges"]
        if len(native_guards) != len(pairs):
            raise ValueError("Missing associated native field branches")
        result = []
        for i,(call_site,getter,writer_site,case_value) in enumerate(pairs):
            idx = (call_site-START)//4
            # ARM-state unconditional BL immediate. Relocation resolution
            # below verifies exactly which native symbol is called.
            if (idx<0 or idx>=len(words) or
                words[idx] >> 24 != 0xeb):
                raise ValueError("Changed FW native getter BL instruction")
            edge = actual.get(call_site)
            if (not edge or edge.get("target_kind")!="import" or
                edge.get("target_demangled")!=getter):
                raise ValueError("Changed FW native getter/PLT symbol link")
            raw = []
            for delta, opcode, assembly in GETTER_BOOLEAN_SEQUENCE:
                pc = call_site + delta
                expected = (0xe3530000 | case_value) if opcode is None else opcode
                if pc<START or pc>=START+4*len(words) or (
                    words[(pc-START)//4] != expected
                ):
                    actual=(f"0x{words[(pc-START)//4]:08x}"
                            if START<=pc<START+4*len(words) else "out-of-bounds")
                    raise ValueError(
                        f"Changed {getter} return-to-boolean ARM code at "
                        f"{pc:#x}; expected 0x{expected:08x}, found {actual}"
                    )
                raw.append({"site":f"0x{pc:08x}",
                            "opcode":f"0x{expected:08x}",
                            "instruction":assembly.replace("#case",f"#{case_value}")})
            zero_branch = native_guards[i]
            if (zero_branch["store_site"] != f"0x{writer_site:08x}" or
                zero_branch["zero_compare_site"] != f"0x{call_site+24:08x}" or
                zero_branch["branch_site"] != f"0x{call_site+28:08x}" or
                zero_branch["bypassed_store_site"] != f"0x{writer_site:08x}"):
                raise ValueError("Getter output does not feed pinned local BEQ")
            result.append({
                "imported_native_getter": getter,
                "imported_callsite": f"0x{call_site:08x}",
                "return_register": "r0",
                "return_copied_to": "r3",
                "booleanized_local_r3": True,
                "compared_getter_return_value":case_value,
                "when_getter_equals_compared_value":"local_BEQ_not_taken",
                "when_getter_differs_from_compared_value":"local_BEQ_taken",
                "direct_store_on_matching_return_if_sequential_entry":
                    f"0x{writer_site:08x}",
                "native_arm_witnesses": raw,
                "native_getter_receiver_pointer_proven": False,
                "live_runtime_return_value_proven": False,
                "all_reaching_definitions_and_side_effects_proven": False,
            })
        evidence[field]=result
    skip_edges=[]
    for site, opcode, target, fallback_begin in FALLBACK_SKIP_BRANCHES:
        idx=(site-START)//4
        if idx < 0 or idx >= len(words) or words[idx]!=opcode:
            raise ValueError("Changed FW native success-path skip branch")
        off=opcode&0xffffff
        if off&0x800000:
            off-=0x1000000
        observed=site+8+off*4
        if observed!=target or fallback_begin!=site+4 or target<=fallback_begin:
            raise ValueError("Wrong FW native first-getter skip target")
        skip_edges.append({
            "branch_site":f"0x{site:08x}",
            "branch_target":f"0x{target:08x}",
            "bypassed_fallback_start":f"0x{fallback_begin:08x}",
            "native_opcode":f"0x{opcode:08x}",
            "runtime_branch_execution_verified":False,
        })
    return {
        "scope": "SOURCE_BACKED_LOCAL_CYCC_GETTER_RETURN_TO_JPEG_FIELDS",
        "four_native_imported_getter_calls_and_r0_r3_paths_verified":True,
        "getters":evidence,
        "first_case_unconditional_fallback_skips":skip_edges,
        "four_local_getter_equality_tests":4,
        "caller_receivers_or_cycc_object_identity_proven":False,
        "runtime_getter_values_or_actual_pixel_pack_proven":False,
        "complete_native_function_control_flow_verified":False,
        "camera_dma_ownership_or_cache_sync_proven":False,
        "firmware_flash_permitted":False,
    }


def decode_arm_simple_mov(word: int, target_register: int) -> dict | None:
    """Only unconditional ARM32 MOV Rd,#imm / MOV Rd,Rm (no shifts)."""
    if not isinstance(word, int) or not 0 <= word <= 0xffffffff:
        raise ValueError("Invalid ARM instruction")
    if word >> 28 != 14 or ((word >> 26) & 3) or ((word >> 21) & 15) != 13 or (
        (word >> 20) & 1
    ) or ((word >> 12) & 15) != target_register:
        return None
    if (word >> 25) & 1:
        shift = 2 * ((word >> 8) & 15)
        imm8 = word & 255
        value = ((imm8 >> shift) | (imm8 << (32 - shift))) & 0xffffffff if shift else imm8
        return {"kind": "MOV_IMM", "immediate": value}
    # No special shifter operands or shifted-register syntax accepted.
    if word & 0xff0:
        return None
    return {"kind": "MOV_REG", "source_register": f"r{word & 15}"}


def trace_field_origins(words: tuple[int, ...], start: int = START) -> dict:
    """Enumerate every *direct* stack slot store before native JPEG call.

    Does not interpret indirect writes or infer constant value on all paths.
    The known callsite marshalling is checked using the independent ABI audit.
    """
    if (start != START or len(words) != BODY_BYTES // 4 or
        any(type(op) is not int or not 0 <= op <= 0xffffffff for op in words)):
        raise ValueError("Unexpected FW1.14 native encoder code body")
    photo.validate_native_ycc_jpeg_stack_args(words, start)
    call_index = (ENCODER_CALL - start) // 4
    evidence = {}
    for label, spec in FIELDS.items():
        site = spec["load_site"]
        index = (site - start) // 4
        if words[index] != spec["expected_load"]:
            raise ValueError("Changed Y/C encoder stack source load")
        loads = arm.decode_mem_word(words[index])
        if (not loads or loads["kind"] != "LDR" or
            loads["base_register"] != 11 or
            loads["data_register"] != 3 or
            loads["offset"] != spec["slot"] or
            loads["condition"] != 14):
            raise ValueError("Changed Y/C encoder stack source operands")
        found = []
        for i, opcode in enumerate(words[:index]):
            decoded = arm.decode_mem_word(opcode)
            if not decoded or decoded["kind"] != "STR" or (
                decoded["base_register"] != 11 or
                decoded["offset"] != spec["slot"]
            ):
                continue
            immediate_predecessor = (
                decode_arm_simple_mov(words[i-1], decoded["data_register"])
                if i else None
            )
            found.append({
                "store_site": f"0x{start + 4*i:08x}",
                "store_opcode": f"0x{opcode:08x}",
                "source_register": f"r{decoded['data_register']}",
                "condition": "AL" if decoded["condition"] == 14 else
                             f"ARM_COND_{decoded['condition']}",
                "immediate_preceding_mov_candidate": immediate_predecessor,
                "preceding_arm_words": [
                    {"site": f"0x{start + 4*j:08x}",
                     "word": f"0x{words[j]:08x}"}
                    for j in range(max(0, i-6), i)
                ],
                "source_runtime_value_proven": False,
            })
            if len(found) > MAX_CANDIDATE_STORES:
                raise ValueError("Unexpected Y/C format/pack slot writer count")
        evidence[label] = {
            "stack_offset_from_fp": spec["slot"],
            "native_jpeg_argument_stack_offset":
                28 if label == "eImgYCCType" else 32,
            "verified_stack_load": f"0x{site:08x}",
            "direct_frame_pointer_store_candidates": found,
            "direct_writer_count": len(found),
            "single_direct_writer_candidate": len(found) == 1,
            "actual_native_enum_value_proven": False,
            "indirect_alias_writers_excluded": False,
            "control_flow_and_calls_exhaustively_modeled": False,
            "real_camera_ycc_interleave_and_stride_verified": False,
        }
    # The same body length and return values are audited on each firmware.
    return {
        "scope": "OFFLINE_UNAUTHENTICATED_FIRMWARE_ARM32_ENCODER_FIELD_WRITERS",
        "native_function": "CMmDeviceDriver::EncodeYcc",
        "native_function_start": f"0x{start:08x}",
        "native_jpeg_callsite": f"0x{ENCODER_CALL:08x}",
        "encoder_body_sha256": hashlib.sha256(
            struct.pack("<" + "I"*len(words), *words)
        ).hexdigest(),
        "fields": evidence,
        "jpeg_callsite_arg_marshalling_verified": True,
        "image_pack_type_constant_proven": False,
        "image_ycc_type_constant_proven": False,
        "live_camera_capture_layout_proven": False,
        "native_camera_dma_ownership_proven": False,
        "firmware_flash_permitted": False,
    }


def inspect_photo_elf(path):
    """Require exact previously verified encoder location from source ELF."""
    import nx300m_fw114_function_proofs as elf
    import nx300m_fw114_sif_virtual_dispatch as symbols

    if (path.is_symlink() or not path.is_file() or
        not 1024 <= path.stat().st_size <= photo.MAX_PHOTO_BYTES):
        raise ValueError("Expected bounded private ARM32 libmm-photo.so")
    blob = path.read_bytes()
    loads = elf.program_headers(path)
    index = symbols.symbol_index(
        symbols.arm.offline_tool(["readelf", "-Ws", str(path)])
    )
    fn = symbols.select(index, "CMmDeviceDriver::EncodeYcc(", "FUNC")
    if fn["address"] != START or fn["size"] != BODY_BYTES:
        raise ValueError("FW1.14 encoder symbol differs from reference")
    words = photo.native_words(blob, loads, START, BODY_BYTES)
    proof = trace_field_origins(words)
    proof["actual_static_direct_writer_pins"] = pin_known_arm_direct_writer_values(
        proof
    )
    proof["native_local_conditional_branch_guards"] = pin_local_ycc_branch_guards(
        words, proof["actual_static_direct_writer_pins"]
    )
    # Independently resolve the imported ARM BL targets rather than
    # treating nearby code as proof of any particular GetType/GetScanMode.
    import nx300m_fw114_sif_callgraph as callgraph
    import nx300m_native_jpeg_abi_boundary_audit as jpeg
    defined=callgraph.defined_symbols(path)
    relocations=jpeg.relocations(
        symbols.arm.offline_tool(["readelf","-Wr",str(path)])
    )
    native_calls=photo.decode_edges(
        blob,loads,defined,relocations,index,"CMmDeviceDriver::EncodeYcc("
    )
    if not native_calls["all_named_edges_reported"]:
        raise ValueError("Incomplete native getter callsite evidence")
    proof["native_getter_return_boolean_paths"] = pin_getter_result_boolean_paths(
        words,native_calls["named_call_edges"],
        proof["native_local_conditional_branch_guards"]
    )
    # A separate receiver audit records exact R0 setup at the four calls.
    # It never promotes static same-frame-slot evidence to physical
    # pointer identity, YCC buffer lifetime or native DMA readiness.
    import nx300m_fw114_ycc_getter_receiver_sources as receiver_sources
    proof["native_ycc_getter_receiver_sources"] = (
        receiver_sources.trace_receiver_inputs(
            words,proof["native_getter_return_boolean_paths"]
        )
    )
    return proof


def compare_versions(fw114, fw115):
    left = inspect_photo_elf(fw114)
    right = inspect_photo_elf(fw115)
    return {
        "fw114": left,
        "fw115": right,
        "same_encoder_body_bytes":
            left["encoder_body_sha256"] == right["encoder_body_sha256"],
        "actual_ycc_format_and_pack_runtime_values_proven": False,
        "live_camera_ycc_geometry_verified": False,
        "firmware_flash_permitted": False,
    }
