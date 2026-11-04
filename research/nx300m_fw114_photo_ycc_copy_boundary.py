#!/usr/bin/env python3
"""Actual FW1.14/1.15 photo ELF Y/C JPEG call sequence + copy-surface audit.

Read-only, version-specific 32-bit ARM static analysis of libmm-photo.so.
Do not treat BlockCopy or getter calls as evidence of owned DMA buffers.
No proprietary file is committed; no camera or native firmware is executed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_sif_callgraph as graph
import nx300m_fw114_sif_virtual_dispatch as symbols
import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_fw114_jfif_r6_arg_provenance as mem

MAX_PHOTO_BYTES=2*1024*1024
METHODS=(
    "CMmDeviceDriver::EncodeYcc(",
    "CMmDeviceDriver::ResizeImage(CYcc&, CYcc&)",
    "CMmDeviceDriver::BlockCopy(CYcc&, CYcc&)",
    "CMmDeviceDriver::BlockCopy(CYcc&, sYccAddr)",
    "CMmDeviceDriver::ConvertYccToRGB(",
)
GETTERS=(
    "CYcc::GetY0()", "CYcc::GetY1()",
    "CYcc::GetC0()", "CYcc::GetC1()",
    "CYcc::GetWidth()", "CYcc::GetHeight()",
    "CYcc::GetStride()", "DscImage::EncodeYCC(",
)
CALL_SITES=tuple(site for site,_ in jpeg.EDGES)
WINDOW_BEFORE=6
WINDOW_AFTER=2


def native_words(image:bytes,loads:list[tuple[int,int,int]],
                 start:int,size:int)->tuple[int,...]:
    if start&3 or size&3 or not 12<=size<=8192:
        raise ValueError("Unbounded ARM32 function code range")
    off=elf.file_range_for_vaddr(loads,start,size)
    return struct.unpack_from("<"+"I"*(size//4),image,off)


def site_window(words:tuple[int,...],start:int,site:int)->dict:
    if (site-start)&3 or site<start or site>=start+4*len(words):
        raise ValueError("Callsite outside native function")
    i=(site-start)//4
    values=[]
    for j in range(max(0,i-WINDOW_BEFORE),min(i+WINDOW_AFTER+1,len(words))):
        op=words[j]
        m=mem.decode_mem_word(op)
        values.append({
            "pc":"0x%08x"%(start+4*j),
            "opcode":"0x%08x"%op,
            "is_this_call":j==i,
            "memory_op":(
                {"kind":m["kind"],"base":"r%d"%m["base_register"],
                 "register":"r%d"%m["data_register"],"offset":m["offset"]}
                if m else None
            )
        })
    return {
        "callsite":"0x%08x"%site,
        "bounded_arm_instruction_window":values,
        "register_arg_values_runtime_proven":False,
        "DMA_or_owned_lifetime_proven":False,
    }


def validate_jpeg_abi_marshal(words:tuple[int,...],start:int)->dict:
    """Exact real ARM getter-result register transfers to JPEG call R0-R3.

    Proves register transfer words, not live CYcc descriptors, DMA ownership,
    Cb/Cr byte order, RAW coherence or a safe location for overwriting pixels.
    """
    expected_getter_moves=(
        ("Y0","0x00034cc0",0xe1a06003,"r6"),
        ("Y1","0x00034cd0",0xe1a05003,"r5"),
        ("C0","0x00034ce0",0xe1a04003,"r4"),
        ("C1","0x00034cf0",0xe1a09003,"r9"),
        ("Width","0x00034d00",0xe1a0a003,"r10"),
        ("Height","0x00034d10",0xe1a08003,"r8"),
    )
    getter_witness=[]
    for name,address,opcode,register in expected_getter_moves:
        site=int(address,16);index=(site-start)//4
        if index<0 or index>=len(words) or words[index]!=opcode:
            raise ValueError("Native FW1.14 YCC getter return register transfer changed")
        getter_witness.append({
            "getter_result":name,"site":address,"opcode":"0x%08x"%opcode,
            "destination_register":register,
        })
    expected_call_regs=(
        ("DscImage instance","0x00034d68",0xe1a00007,"r0","r7"),
        ("Y0","0x00034d6c",0xe1a01006,"r1","r6"),
        ("Y1","0x00034d70",0xe1a02005,"r2","r5"),
        ("C0","0x00034d74",0xe1a03004,"r3","r4"),
    )
    arg_witness=[]
    for name,address,opcode,dst,src in expected_call_regs:
        site=int(address,16);index=(site-start)//4
        if index<0 or index>=len(words) or words[index]!=opcode:
            raise ValueError("Native FW1.14 JPEG entry register ABI changed")
        arg_witness.append({
            "argument":name,"site":address,"opcode":"0x%08x"%opcode,
            "destination":dst,"source":src,
        })
    pc=0x00034d78
    if (pc-start)//4>=len(words):
        raise ValueError("Missing native FW1.14 codec call")
    return {
        "getter_retval_register_transfers":getter_witness,
        "DscImage_EncodeYCC_first_four_arm_args":arg_witness,
        "JPEG_callsite":"0x00034d78",
        "C1_and_geometry_stack_arg_values_proven":False,
        "photography_live_pixel_input_dma_owned":False,
        "safe_copy_insertion_proven":False,
    }


def validate_native_ycc_jpeg_stack_args(words:tuple[int,...],start:int)->dict:
    """Verify 11 consecutive AAPCS stack arguments before DscImage EncodeYCC.

    Each ARM opcode is checked against the independently analyzed FW1.14
    photo ELF. This proves register/store byte patterns only, not the
    runtime buffer addresses, validity or actual on-camera execution.
    """
    expected=(
        (0x34d20,0xe58d9000,0,"C1","r9"),
        (0x34d28,0xe58d2004,4,"pointer/aux arg5","r2=0"),
        (0x34d30,0xe58d2008,8,"pointer/aux arg6","r2=0"),
        (0x34d38,0xe58d200c,12,"pointer/aux arg7","r2=[fp-104]"),
        (0x34d3c,0xe58da010,16,"Width","r10"),
        (0x34d40,0xe58d8014,20,"Height","r8"),
        (0x34d44,0xe58d3018,24,"Stride","r3"),
        (0x34d4c,0xe58d301c,28,"eImgYCCType","r3=[fp-40]"),
        (0x34d54,0xe58d3020,32,"eImgYCCPackType","r3=[fp-44]"),
        (0x34d5c,0xe58d3024,36,"eImgQuality","r3=2"),
        (0x34d64,0xe58d3028,40,"final int","r3=2000"),
    )
    immediately_prior=(
        (0x34d24,0xe3a02000),
        (0x34d2c,0xe3a02000),
        (0x34d34,0xe51b2068),
        (0x34d48,0xe51b3028),
        (0x34d50,0xe51b302c),
        (0x34d58,0xe3a03002),
        (0x34d60,0xe3a03e7d),
    )
    for site,opcode in immediately_prior:
        i=(site-start)//4
        if i<0 or i>=len(words) or words[i]!=opcode:
            raise ValueError("Native YCC JPEG stack source opcode changed")
    args=[]
    for site,opcode,off,arg_name,source in expected:
        i=(site-start)//4
        if i<0 or i>=len(words) or words[i]!=opcode:
            raise ValueError("Native YCC JPEG stack argument opcode changed")
        args.append({
            "SP_byte_offset":off,
            "native_abi_arg":arg_name,
            "stored_from":source,
            "store_site":"0x%08x"%site,
            "opcode":"0x%08x"%opcode,
        })
    return {
        "DscImage_EncodeYCC_stack_args":args,
        "stack_parameter_count":len(args),
        "code_confirmed_immediate_quality":2,
        "code_confirmed_last_integer":2000,
        "C1_and_geometry_stack_arg_opcode_verified":True,
        "source_descriptor_runtime_values_proven":False,
        "raw_DMA_buffer_copy_safe":False,
        "camera_firmware_flash_permitted":False,
    }


def decode_edges(
    image:bytes,loads:list[tuple[int,int,int]],
    defined:dict[int,str],relocs:dict[int,str],
    index:dict[str,dict],prefix:str
)->dict:
    fn=symbols.select(index,prefix,"FUNC")
    start=fn["address"];size=fn["size"]
    words=native_words(image,loads,start,size)
    report=graph.collect_edges(image,loads,start,size,defined,relocs)
    calls=report["identified_callsite_evidence"]
    rawnames=sorted({e["target_symbol"] for e in calls if
                     e["target_kind"]=="import"})
    if len(rawnames)>512:
        raise ValueError("Too many native imported callees")
    pretty=symbols.arm.offline_tool(["c++filt"],
        "\n".join(rawnames)+"\n").splitlines() if rawnames else []
    if len(pretty)!=len(rawnames):
        raise ValueError("Incomplete native callee symbol resolution")
    named=dict(zip(rawnames,pretty))
    edges=[dict(e,
                target_demangled=named.get(e["target_symbol"],
                                          e["target_symbol"]))
           for e in calls]
    ycc=[e for e in edges if e["target_demangled"].startswith("CYcc::")]
    copy=[e for e in edges if "BlockCopy(" in e["target_demangled"] or
          "memcpy" in e["target_demangled"] or
          "memmove" in e["target_demangled"] or
          "bblt" in e["target_demangled"].lower()]
    return {
        "method":fn["name"],
        "symbol_address":"0x%08x"%start,
        "function_size":size,
        "function_sha256":hashlib.sha256(
            struct.pack("<"+"I"*len(words),*words)).hexdigest(),
        "direct_bl_candidates":report["arm_direct_bl_candidate_count"],
        "named_call_edges":edges,
        "native_ycc_getter_calls":ycc,
        "named_copy_like_call_edges":copy,
        "all_named_edges_reported":not report["identified_calls_truncated"],
        "source_bl_calls":[
            {"source":e["callsite"],
             "target":e["target_demangled"]}
            for e in edges
        ],
        "raw_arm_words":words,
        "real_isp_dma_buffer_ownership_proven":False,
        "safe_copied_buffer_lifetime_proven":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (
        1024<=path.stat().st_size<=MAX_PHOTO_BYTES
    ):
        raise ValueError("Expected bounded extracted ARM libmm-photo.so")
    image=path.read_bytes()
    loads=elf.program_headers(path)
    index=symbols.symbol_index(symbols.arm.offline_tool(
        ["readelf","-Ws",str(path)]))
    defined=graph.defined_symbols(path)
    relocs=jpeg.relocations(symbols.arm.offline_tool(
        ["readelf","-Wr",str(path)]))
    results={}
    for prefix in METHODS:
        result=decode_edges(image,loads,defined,relocs,index,prefix)
        words=result.pop("raw_arm_words")
        results[prefix]=result
        if prefix=="CMmDeviceDriver::EncodeYcc(":
            if result["symbol_address"]!="0x00034b18":
                raise ValueError("Unexpected FW114 YCC encoder symbol")
            if not result["all_named_edges_reported"]:
                raise ValueError("YCC native BL report truncated")
            targets={e["callsite"]:e["target_demangled"]
                     for e in result["named_call_edges"]}
            getter_sequence=[]
            for site,expected in jpeg.EDGES:
                got=targets.get("0x%08x"%site)
                if got is None or not got.startswith(expected):
                    raise ValueError("Missing version-local native YCC getter/encoder callsite")
                getter_sequence.append({
                    "expected_native_method":got,
                    **site_window(words,0x34b18,site),
                })
            result["validated_ycc_getter_to_encoder_order"]=getter_sequence
            result["native_arm_jpeg_getter_register_abi"]=validate_jpeg_abi_marshal(words,start=0x34b18)
            result["native_arm_jpeg_stack_arg_abi"]=validate_native_ycc_jpeg_stack_args(words,start=0x34b18)
            result["pre_encode_stack_marshalling_arm"]=[
                {"pc":"0x%08x"%(0x34d20+i*4),
                 "opcode":"0x%08x"%words[(0x34d20-0x34b18)//4+i]}
                for i in range((0x34d78-0x34d20)//4)
            ]
    encode=results["CMmDeviceDriver::EncodeYcc("]
    return {
        "scope":"READ_ONLY_PRIVATE_FW114_PHOTO_ELF_STATIC",
        "libmm_photo_sha256":hashlib.sha256(image).hexdigest(),
        "native_methods":results,
        "native_getters_and_encode_method_count":
            len(encode["validated_ycc_getter_to_encoder_order"]),
        "native_blockcopy_overloads_present":True,
        "encoder_directly_invokes_blockcopy_or_memcpy":
            bool(encode["named_copy_like_call_edges"]),
        "encoder_owned_copy_and_DMA_lifetime_proven":False,
        "Y0_Y1_C0_C1_runtime_sample_verified":False,
        "film_engine_native_insertion_point_safe":False,
        "camera_patch_or_flash_permitted":False,
    }


def compare_versions(p114:Path,p115:Path)->dict:
    a=inspect(p114)
    b=inspect(p115)
    return {
        "fw114":a,"fw115":b,
        "photo_elf_sha256_equal":a["libmm_photo_sha256"]==b["libmm_photo_sha256"],
        "photo_native_method_code_equal":all(
            a["native_methods"][prefix]["function_sha256"]==
            b["native_methods"][prefix]["function_sha256"]
            for prefix in METHODS
        ),
        "real_device_ycc_buffer_provenance_known":False,
        "camera_firmware_flash_permitted":False,
    }
