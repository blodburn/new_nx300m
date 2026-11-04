#!/usr/bin/env python3
"""Read-only actual FW1.14/1.15 SIF HAL callback producer investigation.

Trace native DscJPEG::DscJPEG(... tDscHal*) and Instance(.. tDscHal*)
to DscJfif::HalRegister, recording exact ARM32 BL/PLT and table
pointer passing. Scan direct writes to the +8 field only within
relevant named native functions, and distinguish presence of a
GLOB_DAT relocation from proof of callback assignment.

All inputs are ephemeral, previously header-checked third-party
unofficial firmware ELFs. Never execute code or patch firmware.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as elf
import nx300m_fw114_jfif_r6_arg_provenance as arg
import nx300m_fw114_sif_virtual_dispatch as sif
import nx300m_fw114_sif_callgraph as graph
import nx300m_native_jpeg_abi_boundary_audit as jpeg

MAX_SOURCE=2*1024*1024
MAX_METHOD=4096
METHODS=(
    "DscJfif::HalRegister(",
    "DscImage::DscJpegInstance(",
    "DscJPEG::DscJPEG(unsigned long",
    "DscJPEG::Instance(",
    "DscJfif::DscJfif()",
)
HAL_SYMBOL="DscJfifHal::Encode("
HAL_REGISTER_SYMBOL="DscJfif::HalRegister("
MAX_RELEVANT_FUNCS=128


def candidate_mem_store_sites(
    words:tuple[int,...],address:int,offset:int=8
)->list[dict]:
    """Direct STR [reg,#8] statements; never infer object base."""
    found=[]
    for i,w in enumerate(words):
        item=arg.decode_mem_word(w)
        if not item or item["kind"]!="STR" or item["offset"]!=offset:
            continue
        if len(found)>=40:
            raise ValueError("Unbounded HAL field store candidate count")
        found.append({
            "site":"0x%08x"%(address+4*i),
            "opcode":"0x%08x"%w,
            "base_register":"r%d"%item["base_register"],
            "value_register":"r%d"%item["data_register"],
            "preceding_words":[
                {"site":"0x%08x"%(address+4*j),
                 "opcode":"0x%08x"%words[j]}
                for j in range(max(0,i-7),i)
            ],
            "proven_tDscHal_plus8_write":False,
            "proven_hal_encoder_callback_value":False,
        })
    return found


def arm_argument_window(words:tuple[int,...],start:int,site:int)->dict:
    """Report actual native ARM instructions near one call, not argument proof."""
    if site<start or (site-start)%4:
        raise ValueError("Callsite not inside ARM function")
    index=(site-start)//4
    if index>=len(words):
        raise ValueError("Callsite exceeds bounded native body")
    lower=max(0,index-18)
    return {
        "native_callsite":"0x%08x"%site,
        "preceding_arm_words":[
            {"site":"0x%08x"%(start+4*i),
             "opcode":"0x%08x"%words[i]}
            for i in range(lower,index)
        ],
        "r3_candidates_before_call":[
            {"word_index":x["word_index"],
             "opcode":x["opcode"],
             "kind":x["kind"],
             "source_register":x["source_register"],
             "source_byte_offset":x["source_byte_offset"]}
            for x in sif.register_writer_candidates(list(words),index,3)
        ],
        "fourth_argument_r3_value_determined":False,
        "hal_table_lifetime_proven":False,
    }


def elf_arm_word(image:bytes,segs:list[tuple[int,int,int]],vaddr:int)->int:
    if vaddr&3:
        raise ValueError("Unaligned ARM literal or GOT read")
    off=elf.file_range_for_vaddr(segs,vaddr,4)
    if off+4>len(image):
        raise ValueError("Read outside same-version ELF data")
    return struct.unpack_from("<I",image,off)[0]


def decode_pic_r4(
    image:bytes,segments:list[tuple[int,int,int]],
    words:tuple[int,...],function_vaddr:int,first_pointer_load:int
)->dict:
    """Determine ARM PIC r4 GOT base from actual LDR literal; ADD pc,r4."""
    found=[]
    for i in range(first_pointer_load):
        w=words[i]
        # ARM ADD r4, pc, r4, register operand with no shifts.
        if not (
            (w>>28)==14 and ((w>>26)&3)==0 and ((w>>25)&1)==0
            and ((w>>21)&15)==4 and ((w>>20)&1)==0
            and ((w>>16)&15)==15 and ((w>>12)&15)==4
            and ((w>>4)&255)==0 and (w&15)==4
        ):
            continue
        possible=[]
        for j in range(i):
            src=arg.decode_mem_word(words[j])
            if (src and src["kind"]=="LDR" and
                src["data_register"]==4 and src["base_register"]==15):
                possible.append((j,src))
        if not possible:
            continue
        site,load=possible[-1]
        literal_addr=function_vaddr+4*site+8+load["offset"]
        relative_offset=elf_arm_word(image,segments,literal_addr)
        base=(relative_offset+function_vaddr+4*i+8)&0xffffffff
        found.append({
            "got_pic_base":"0x%08x"%base,
            "ldr_r4_literal_site":"0x%08x"%(function_vaddr+4*site),
            "ldr_r4_literal_vaddr":"0x%08x"%literal_addr,
            "add_r4_pc_site":"0x%08x"%(function_vaddr+4*i),
            "source_literal":"0x%08x"%relative_offset,
        })
    if len(found)!=1:
        raise ValueError("Missing or ambiguous ARM PIC r4 base initializer")
    return found[0]


def resolve_initializer_four_fields(
    image:bytes,segments:list[tuple[int,int,int]],
    words:tuple[int,...],start:int,
    relocations:dict[int,dict]
)->dict:
    """Prove exact four ARM GOT loads -> stack tDscHal slots -> r3 call arg.

    This is a byte-level version-local static proof, not execution evidence.
    The four stored values are symbol-address pointers loaded through
    R_ARM_GLOB_DAT relocations, NOT copies from the photo input buffer.
    """
    addresses=(0x00053fc8,0x00053fd4,0x00053fe0,0x00053fec)
    if start!=0x00053f80:
        raise ValueError("Unrecognized original FW114 JPEG Instance entry")
    pic=decode_pic_r4(image,segments,words,start,(addresses[0]-start)//4)
    got_base=int(pic["got_pic_base"],16)
    fields=[]
    for ix,addr in enumerate(addresses):
        j=(addr-start)//4
        if j+2>=len(words):
            raise ValueError("Truncated tDscHal construction")
        load=arg.decode_mem_word(words[j])
        if not load or (
            load["kind"],load["base_register"],load["data_register"],
            load["condition"]
        )!=("LDR",15,3,14):
            raise ValueError("Missing native PC-relative callback GOT index")
        if words[j+1]!=0xe7943003: # LDR r3,[r4,r3]
            raise ValueError("Missing PIC GOT slot load into r3")
        store=arg.decode_mem_word(words[j+2])
        if not store or (
            store["kind"],store["base_register"],store["data_register"],
            store["offset"],store["condition"]
        )!=("STR",11,3,-28+4*ix,14):
            raise ValueError("Missing exact callback pointer store to fp-local table")
        literal_site=addr+8+load["offset"]
        index=elf_arm_word(image,segments,literal_site)
        got_addr=(got_base+index)&0xffffffff
        reloc=relocations.get(got_addr)
        if reloc is None or reloc["relocation_type"]!="R_ARM_GLOB_DAT":
            raise ValueError("Unresolved ARM GOT dynamic symbol in tDscHal constructor")
        fields.append({
            "tDscHal_field_offset":4*ix,
            "stack_slot":"fp%+d"%(-28+4*ix),
            "got_slot":"0x%08x"%got_addr,
            "got_index_literal":"0x%08x"%literal_site,
            "got_index":"0x%08x"%index,
            "dynamic_relocation_type":reloc["relocation_type"],
            "mangled_native_symbol":reloc["mangled_symbol"],
            "native_symbol_value":reloc["symbol_value"],
            "load_at":"0x%08x"%addr,
            "store_at":"0x%08x"%(addr+8),
            "on_camera_pointer_initialized_observed":False,
        })
    # SUB r3, fp, #28 ; BL DscJPEG::Instance after setting r0/r1/r2
    if words[(0x00054004-start)//4]!=0xe24b301c:
        raise ValueError("Missing tDscHal pointer setup as fourth ARM argument")
    if not any(x["tDscHal_field_offset"]==8 and (
            x["mangled_native_symbol"].startswith("_ZN10DscJfifHal6Encode")
        ) and x["native_symbol_value"]=="0x00029830" for x in fields):
        raise ValueError("FW114 tDscHal +8 does not resolve to HAL Encode")
    return {
        "pic_base_evidence":pic,
        "stack_table_pointer_setup":"0x00054004",
        "instance_bl_callsite":"0x00054014",
        "fields":fields,
        "tDscHal_plus8_static_reloc_symbol_is_DscJfifHal_Encode":True,
        "tDscHal_pointer_runtime_lifetime_verified":False,
        "hardware_callback_invocation_observed":False,
        "safe_real_isp_buffer_hook_proven":False,
        "flash_allowed":False,
    }


def native_method(path:Path, image:bytes, segments:list[tuple[int,int,int]],
                  symbols:dict[str,dict],prefix:str,
                  defined:dict[int,str],relocs:dict[int,str]) -> dict:
    fn=sif.select(symbols,prefix,"FUNC")
    addr=fn["address"];size=fn["size"]
    if addr&3 or size&3 or not 8<=size<=MAX_METHOD:
        raise ValueError("Unexpected FW114 SIF method body: "+prefix)
    off=elf.file_range_for_vaddr(segments,addr,size)
    with path.open("rb") as stream:
        stream.seek(off);raw=stream.read(size)
    if len(raw)!=size:
        raise ValueError("SIF ARM body truncated")
    words=struct.unpack("<"+"I"*(size//4),raw)
    edges=graph.collect_edges(image,segments,addr,size,
                              defined,relocs)
    # PLT stubs and GOT relocations require the complete version-local ELF.
    target_windows=[
        arm_argument_window(words,addr,int(x["callsite"],16))
        for x in edges["identified_callsite_evidence"]
        if "_ZN7DscJPEG8InstanceEmibP7tDscHal" in x["target_symbol"]
    ]
    return {
        "native_symbol":fn["name"],
        "hal_instance_call_argument_windows":target_windows,
        "function_address":"0x%08x"%addr,
        "size":size,
        "sha256":hashlib.sha256(raw).hexdigest(),
        "direct_bl_candidates":edges["arm_direct_bl_candidate_count"],
        "identified_direct_calls":edges["identified_callsite_evidence"],
        "all_identified_calls_included":not edges["identified_calls_truncated"],
        "direct_plus8_store_candidates":candidate_mem_store_sites(words,addr),
        "complete_native_control_flow_verified":False,
    }


def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or (
        not 1024<=path.stat().st_size<=MAX_SOURCE
    ):
        raise ValueError("Require private bounded native FW libsif.so")
    data=path.read_bytes()
    segments=elf.program_headers(path)
    symbols=sif.symbol_index(sif.arm.offline_tool(
        ["readelf","-Ws",str(path)]))
    defined=graph.defined_symbols(path)
    reltext=sif.arm.offline_tool(["readelf","-Wr",str(path)])
    relocs=jpeg.relocations(reltext)
    reloc_targets=sif.relocation_symbol_targets(reltext)
    hal_symbol=sif.select(symbols,HAL_SYMBOL,"FUNC")
    hal_got=[
        {"got_address":"0x%08x"%location,**item}
        for location,item in reloc_targets.items()
        if item["symbol_value"]=="0x%08x"%hal_symbol["address"] and
           item["relocation_type"] in ("R_ARM_GLOB_DAT","R_ARM_JUMP_SLOT")
    ]
    if not hal_got or len(hal_got)>4:
        raise ValueError("Missing or ambiguous HAL Encode relocated symbol witness")
    focus={}
    for prefix in METHODS:
        focus[prefix]=native_method(path,data,segments,symbols,prefix,defined,relocs)
    image_fn=sif.select(symbols,"DscImage::DscJpegInstance(","FUNC")
    image_addr=image_fn["address"]
    image_len=image_fn["size"]
    if image_addr&3 or image_len&3 or not 80<=image_len<=1024:
        raise ValueError("Unexpected native DscImage Instance ARM body")
    image_off=elf.file_range_for_vaddr(segments,image_addr,image_len)
    arm_words=struct.unpack_from(
        "<"+"I"*(image_len//4),data,image_off
    )
    table=resolve_initializer_four_fields(
        data,segments,arm_words,image_addr,reloc_targets
    )
    ctor=focus["DscJPEG::DscJPEG(unsigned long"]
    instance=focus["DscJPEG::Instance("]
    image_producer=focus["DscImage::DscJpegInstance("]
    def evidence(data:dict)->list[dict]:
        return [x for x in data["identified_direct_calls"] if
                "HalRegister" in x["target_symbol"] or
                "DscJfif" in x["target_symbol"] or
                "DscJPEG" in x["target_symbol"]]
    return {
        "source":"UNOFFICIAL_MIRROR_STATIC_ARM32_SIF",
        "libsif_sha256":hashlib.sha256(data).hexdigest(),
        "method_evidence":focus,
        "jpeg_constructor_relevant_direct_calls":evidence(ctor),
        "jpeg_instance_relevant_direct_calls":evidence(instance),
        "dscimage_jpeg_instance_relevant_calls":evidence(image_producer),
        "dscimage_jpeg_instance_plus8_writes":
            image_producer["direct_plus8_store_candidates"],
        "hal_encoder_symbol":"DscJfifHal::Encode",
        "hal_encoder_native_address":"0x%08x"%hal_symbol["address"],
        "hal_encoder_static_got_relocations":hal_got,
        "static_hal_initializer_four_fields":table,
        "tDscHal_plus8_static_symbol_relocation_verified":
            table["tDscHal_plus8_static_reloc_symbol_is_DscJfifHal_Encode"],
        "jpeghal_table_plus8_actual_initialization_proven":False,
        "same_tDscHal_table_instance_proven":False,
        "callback_runtime_target_proven":False,
        "real_dma_ycc_buffer_ownership_proven":False,
        "firmware_install_or_flash_permitted":False,
    }


def compare_versions(fw114:Path,fw115:Path)->dict:
    a=inspect(fw114)
    b=inspect(fw115)
    return {
        "fw114":a,"fw115":b,
        "third_party_firmware_authenticated_by_samsung":False,
        "hal_callback_exact_runtime_address_proven":False,
        "camera_flash_permitted":False,
    }
