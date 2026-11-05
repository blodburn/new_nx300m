#!/usr/bin/env python3
"""Find CYcc and memory-pool implementation providers in private FW UBI.

Only reads local extracted ELF symbol tables and function byte digests.
No native execution, camera access, root privileges or firmware modification.
The UBI files come from unauthenticated third-party mirror firmware.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import stat

import nx300m_fw114_sif_virtual_dispatch as symbols
import nx300m_fw114_function_proofs as elf
import nx300m_fw114_photo_buffer_lifetime as lifetime
import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_fw114_jfif_r6_arg_provenance as mem
import struct

MAX_FILES=60000
MAX_ELF=16*1024*1024
NAMES=("libmm-type.so","libmm-photo.so","libcapture-fw-slpcam.so",
       "libcapture-fw-slpcam-nx300.so")
NEEDLES=(
    "CYcc::~CYcc()",
    "CYcc::GetType()",
    "CYcc::GetY0()",
    "CMemoryPool::GetAddr(",
    "CMemoryPool::GetInstance()",
    "CYcc::CYcc(sImgSize, unsigned long)",
    "CYcc::CYcc(sImgSize, sYccAddr",
)


def safe_sources(root:Path)->dict[str,Path]:
    """Realpaths must remain under the already extracted private root."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Expected real private firmware tree")
    resolved_root=root.resolve(strict=True)
    found:dict[str,dict[str,Path]]={}
    count=0
    for item in root.rglob("*"):
        count+=1
        if count>MAX_FILES:
            raise ValueError("Unbounded firmware tree")
        if item.name not in NAMES:
            continue
        try:
            resolved=item.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError,ValueError,RuntimeError) as exc:
            raise ValueError("Library alias escapes private firmware root") from exc
        if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
            raise ValueError("Not a real library file")
        if not 52<=resolved.stat().st_size<=MAX_ELF:
            raise ValueError("Unsupported provider ELF bytes")
        found.setdefault(item.name,{})[str(resolved)]=resolved
    output={}
    for name,locations in found.items():
        if len(locations)!=1:
            raise ValueError("Ambiguous library realpath: "+name)
        output[name]=next(iter(locations.values()))
    return output


CODE_TARGETS=(
    "CYcc::~CYcc()",
    "CYcc::CYcc(sImgSize, unsigned long)",
    "CMemoryPool::GetAddr(",
    "CMemoryPool::GetInstance()",
    "CYcc::GetType()",
)
MAX_ARM_WORDS=170


def critical_arm_body(data:bytes,loads:list[tuple[int,int,int]],
                      address:int,size:int,
                      native_function_names:dict[int,str],
                      relocs:dict[int,dict])->dict:
    """Disassemble bounded source ELF ARM words without executing firmware."""
    if address&3 or size&3 or not 4<=size<=MAX_ARM_WORDS*4:
        raise ValueError("Unexpected bounded CYcc provider ARM body")
    pos=elf.file_range_for_vaddr(loads,address,size)
    words=struct.unpack_from("<"+"I"*(size//4),data,pos)
    direct_calls=[]
    indirect=[]
    for i,op in enumerate(words):
        pc=address+4*i
        target=symbols.arm.decode_arm_bl(op,pc)
        if target is not None:
            name=native_function_names.get(target)
            imported=None
            if name is None:
                try:
                    got=jpeg.plt_got(data,loads,target)
                    relocation=relocs.get(got)
                    if relocation and relocation["relocation_type"]=="R_ARM_JUMP_SLOT":
                        imported=relocation["mangled_symbol"]
                except ValueError:
                    pass
            direct_calls.append({
                "pc":"0x%08x"%pc,
                "branch_target":"0x%08x"%target,
                "local_native_function":name,
                "same_elf_import_mangled":imported,
            })
        elif mem.sif.decode_indirect(op):
            kind,r=mem.sif.decode_indirect(op)
            indirect.append({"pc":"0x%08x"%pc,"kind":kind,"register":r})
    return {
        "arm_word_count":len(words),
        "unconditional_arm_B_edges":[
            branch for branch in lifetime.branch_boundaries(words,address)
            if branch["condition"]==14
        ],
        "direct_ARM_BL_edges":direct_calls,
        "register_indirect_branches":indirect,
        "arm_instruction_words":[
            {"pc":"0x%08x"%(address+4*i),"opcode":"0x%08x"%op}
            for i,op in enumerate(words)
        ],
        "native_actual_pixel_release_verified":False,
        "no_hidden_or_indirect_release_proven":False,
    }


def proof_mode2_pool_and_trivial_cycc_destructor(
    provider_report:dict,lifetime_report:dict
)->dict:
    """Exact FW1.14 ARM byte witness; never infer a live DMA lock."""
    providers=provider_report["provider_elfs"]

    def get(name:str,prefix:str)->dict:
        lib=providers.get(name)
        if not lib or not lib["present"]:
            raise ValueError("Native pool/CYcc library not present")
        found=[x for x in lib["target_symbols"] if x["name"].startswith(prefix)]
        if len(found)!=1 or "offline_native_ARM_body" not in found[0]:
            raise ValueError("Missing or ambiguous original native ARM method")
        return found[0]

    destructor=get("libmm-type.so","CYcc::~CYcc()")
    pool=get("libmm-photo.so","CMemoryPool::GetAddr(")
    if destructor["address"]!="0x00002a00" or destructor["function_bytes"]!=36:
        raise ValueError("CYcc destructor body changed")
    if pool["address"]!="0x0003534c" or pool["function_bytes"]!=172:
        raise ValueError("Memory pool GetAddr body changed")

    def words(method:dict)->dict[str,str]:
        return {w["pc"]:w["opcode"] for w in method[
            "offline_native_ARM_body"]["arm_instruction_words"]}

    d=words(destructor)
    expected_destructor={
        "0x00002a00":"0xe52db004", # push frame pointer
        "0x00002a04":"0xe28db000",
        "0x00002a08":"0xe24dd00c",
        "0x00002a0c":"0xe50b0008", # store this on stack
        "0x00002a10":"0xe51b3008",
        "0x00002a14":"0xe1a00003",
        "0x00002a18":"0xe28bd000",
        "0x00002a1c":"0xe8bd0800",
        "0x00002a20":"0xe12fff1e", # BX LR
    }
    if d!=expected_destructor or destructor[
        "offline_native_ARM_body"]["direct_ARM_BL_edges"] or destructor[
        "offline_native_ARM_body"]["register_indirect_branches"]:
        raise ValueError("CYcc destructor is not verified trivial ARM function")

    expected_pool_words={
        "0x00035398":"0xe51b3014", # LDR r3,[fp,#-20] enum
        "0x0003539c":"0xe3530002", # CMP r3,#2
        "0x000353a0":"0x1a000002", # BNE error mode handling
        "0x000353a4":"0xe51b3010", # LDR r3,[fp,#-16] this
        "0x000353a8":"0xe5933008", # LDR r3,[r3,#8]
        "0x000353ac":"0xea00000a", # B to return
        "0x000353dc":"0xe1a00003", # MOV r0,r3
    }
    p=words(pool)
    if any(p.get(pc)!=code for pc,code in expected_pool_words.items()):
        raise ValueError("CMemoryPool::GetAddr mode 2 static return changed")

    first=lifetime_report["code_windows"][0]["arm_words"]
    caller={w["pc"]:w["arm_word"] for w in first}
    if caller.get("0x00034b70")!="0xe3a01002" or caller.get(
        "0x00034b74")!="0xebffd3bd" or caller.get(
        "0x00034b50")!="0x0a000022":
        raise ValueError("FW1.14 memory pool enum 2 or type guard changed")
    if not any(x["pc"]=="0x00034b50" and
               x["target"]=="0x00034be0" and
               x["condition"]==0
               for x in lifetime_report["internal_arm_branch_edges"]):
        raise ValueError("FW1.14 type 1 resize branch target changed")
    return {
        "method_provider":"FW114_LIBMM_TYPE_AND_LIBMM_PHOTO_NATIVE_ARM",
        "getter_type_1_conditional_memorypool_resize_branch":True,
        "memorypool_GetAddr_enum_2_reads_pool_object_offset8":True,
        "CYcc_destructor_has_no_direct_free_or_calls":True,
        "CYcc_destructor_writes_only_its_own_stack_frame":True,
        "pointer_held_in_pool_slot_has_ownership_or_refcount_proof":False,
        "pool_slot_overwrite_or_reuse_interval_verified":False,
        "pixel_YCC_input_DMA_coherency_or_lifetime_proven":False,
        "safe_film_engine_hook_permitted":False,
        "firmware_flash_permitted":False,
    }


def inspect(root:Path)->dict:
    providers=safe_sources(root)
    report={}
    for name in NAMES:
        path=providers.get(name)
        if path is None:
            report[name]={"present":False,"target_symbols":[]}
            continue
        loads=elf.program_headers(path)
        idx=symbols.symbol_index(symbols.arm.offline_tool(
            ["readelf","-Ws",str(path)]))
        image=path.read_bytes()
        relocation_text=symbols.arm.offline_tool(["readelf","-Wr",str(path)])
        relocs=symbols.relocation_symbol_targets(relocation_text)
        defined={
            item["address"]:key for key,item in idx.items()
            if item["kind"]=="FUNC" and item["size"]>0
        }
        matches=[]
        for title,entry in sorted(idx.items()):
            if entry["kind"]!="FUNC" or not any(
                title.startswith(want) for want in NEEDLES
            ):
                continue
            size=entry["size"];address=entry["address"]
            if size<4 or size>65536:
                continue
            off=elf.file_range_for_vaddr(loads,address,size)
            with path.open("rb") as stream:
                stream.seek(off)
                body=stream.read(size)
            if len(body)!=size:
                raise ValueError("Provider ARM method truncated")
            extra={}
            if any(title.startswith(prefix) for prefix in CODE_TARGETS):
                extra["offline_native_ARM_body"]=critical_arm_body(
                    image,loads,address,size,defined,relocs
                )
            matches.append({
                "name":title,
                "address":"0x%08x"%address,
                "function_bytes":size,
                "sha256":hashlib.sha256(body).hexdigest(),
                "actual_function_run_on_camera":False,
                **extra,
            })
        if len(matches)>96:
            raise ValueError("Too many native CYcc provider matches")
        report[name]={
            "present":True,
            "ELF_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "target_symbols":matches,
            "runtime_CYcc_buffer_destructor_behavior_verified":False,
            "memorypool_GetAddr_retained_by_caller_proven":False,
        }
    return {
        "scope":"UNOFFICIAL_PRIVATE_UBI_NATIVE_SYMBOLS_ONLY",
        "provider_elfs":report,
        "live_symbol_resolution_proven":False,
        "destructor_frees_CYcc_pixel_storage_proven":False,
        "destructor_does_not_free_CYcc_pixel_storage_proven":False,
        "real_camera_firmware_patch_permitted":False,
    }
