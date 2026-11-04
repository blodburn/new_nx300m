#!/usr/bin/env python3
"""READ-ONLY candidate ARM BL call graph from real FW1.14/1.15 libsif.so.

Uses separately extracted, hash-checked unofficial mirror ELF files.
No firmware execution, native loading, write, patch, camera access or flash.
Only ARM-state direct BL opcodes are examined; indirect BLX / vtables and
dynamic loader state are NOT inferred. Exact symbol-start/PLT import linkage
is stronger than a guessed call graph, but does not prove runtime invocation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import nx300m_fw114_function_proofs as focus
import nx300m_native_jpeg_abi_boundary_audit as jpeg
import nx300m_pw_ui_bl_call_audit as arm

TARGET_PREFIXES=(
    "DscImage::EncodeYCC(",
    "DscImage::SaveExifImage(",
    "DscImage::CopyExifInfo(",
    "DscImage::GetExifImageInfo(",
    "DscJfif::JpegEncode(",
    "DscJfifHal::Encode(",
    "DscJfifHal::Parse(",
)
MAX_FILE=2*1024*1024
MAX_FUNCTION=65536
MAX_CALLS=2000
MAX_IDENTIFIED=120

def refuse(reason: str):
    raise ValueError(reason)

def defined_symbols(path:Path)->dict[int,str]:
    """A unique defined ARM function start -> demangled symbol."""
    text=arm.offline_tool(["readelf","-Ws",str(path)])
    raw=arm.parse_functions(text)
    keys=sorted(raw)
    if len(keys)>10000:refuse("Too many ELF symbol definitions")
    names=arm.offline_tool(["c++filt"],"\n".join(
        mangled for _,mangled in keys)+"\n").splitlines()
    if len(names)!=len(keys):
        refuse("Missing symbol demangling output")
    found={}
    duplicates=set()
    for (address,_),name in zip(keys,names):
        if address in found and found[address]!=name:
            duplicates.add(address)
        else:
            found[address]=name
    for address in duplicates:
        del found[address]  # ambiguous alias: no guessed callee
    return found

def select_targets(symbols: dict[int,str])->dict[str,tuple[int,str]]:
    result={}
    for prefix in TARGET_PREFIXES:
        chosen=[(a,s) for a,s in symbols.items() if s.startswith(prefix)]
        if len(chosen)!=1:
            refuse("Missing/overloaded target symbol "+prefix)
        result[prefix]=chosen[0]
    return result

def _arm_call_words(data:bytes,segments:list[tuple[int,int,int]],
                    address:int,length:int)->list[tuple[int,int]]:
    if address&3 or length<4 or length>MAX_FUNCTION:
        refuse("Non-ARM or oversized function body")
    return arm.scan_direct_calls(data,address,length,segments)

def collect_edges(
    data:bytes,
    segments:list[tuple[int,int,int]],
    address:int,length:int,
    defined:dict[int,str],
    relocations:dict[int,str],
)->dict:
    """Precisely identify direct calls to exact symbols or ARM PLT imports."""
    calls=_arm_call_words(data,segments,address,length)
    if len(calls)>MAX_CALLS:
        refuse("Too many branch instructions in one function")
    linked=[]
    unresolved=0
    imported=0
    local=0
    for site,target in calls:
        kind="local"
        name=defined.get(target)
        if name is None:
            kind="import"
            try:
                got=jpeg.plt_got(data,segments,target)
                mangled=relocations.get(got)
                if mangled:
                    kind="import"
                    name=mangled  # export raw symbol, demangle later
            except ValueError:
                pass
        if name is None:
            unresolved+=1
            continue
        if len(linked)<MAX_IDENTIFIED:
            linked.append({"callsite":"0x%08x"%site,
                           "target_symbol":name[:220],
                           "target_kind":kind})
        if kind=="import":imported+=1
        else:local+=1
    return {
        "arm_direct_bl_candidate_count":len(calls),
        "identified_local_bl_count":local,
        "identified_plt_import_bl_count":imported,
        "unresolved_or_unnamed_target_count":unresolved,
        "identified_calls_truncated":local+imported>len(linked),
        "identified_callsite_evidence":linked,
        "thumb_blx_indirect_or_virtual_dispatch_resolved":False,
    }

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not 1024<=path.stat().st_size<=MAX_FILE:
        refuse("Require a bounded regular private libsif.so ELF")
    data=path.read_bytes()
    loads=focus.program_headers(path)
    symbols=defined_symbols(path)
    targets=select_targets(symbols)
    raw_relocations=arm.offline_tool(["readelf","-Wr",str(path)])
    relocs=jpeg.relocations(raw_relocations)
    out={}
    for prefix,(address,display) in targets.items():
        # Exact length from same file's actual ELF symbol table.
        binary_symbols=arm.parse_functions(arm.offline_tool(
            ["readelf","-Ws",str(path)]))
        length_options=[n for (v,raw),n in binary_symbols.items()
                        if v==address]
        if len(set(length_options))!=1:
            refuse("Ambiguous native function size "+prefix)
        length=length_options[0]
        start=focus.file_range_for_vaddr(loads,address,length)
        body=data[start:start+length]
        if len(body)!=length:
            refuse("Truncated function read")
        out[prefix]={
            "native_address":"0x%08x"%address,
            "function_bytes":length,
            "actual_function_sha256":hashlib.sha256(body).hexdigest(),
            "name":display,
            **collect_edges(data,loads,address,length,symbols,relocs)
        }
    return {
        "scope":"UNOFFICIAL_MIRROR_LIBSIF_READ_ONLY_ARM32",
        "libsif_sha256":hashlib.sha256(data).hexdigest(),
        "target_function_count":len(out),
        "functions":out,
        "on_camera_execution_observed":False,
        "correct_dma_ownership_proven":False,
        "native_jpeg_makernotes_runtime_safe":False,
        "firmware_flash_permitted":False,
    }

def compare_versions(p114:Path,p115:Path)->dict:
    a=inspect(p114)
    b=inspect(p115)
    report=[]
    for key in TARGET_PREFIXES:
        x,y=a["functions"][key],b["functions"][key]
        # Compare symbolic links *without pretending address stability*.
        def caller_names(entry):
            return sorted((e["target_kind"],e["target_symbol"])
                          for e in entry["identified_callsite_evidence"])
        report.append({
            "function":key,
            "fw114_address":x["native_address"],
            "fw115_address":y["native_address"],
            "body_sha256_equal":x["actual_function_sha256"]==y["actual_function_sha256"],
            "fw114_direct_bl_candidates":x["arm_direct_bl_candidate_count"],
            "fw115_direct_bl_candidates":y["arm_direct_bl_candidate_count"],
            "fw114_identified_local_bl":x["identified_local_bl_count"],
            "fw115_identified_local_bl":y["identified_local_bl_count"],
            "fw114_identified_plt_bl":x["identified_plt_import_bl_count"],
            "fw115_identified_plt_bl":y["identified_plt_import_bl_count"],
            "symbolic_calls_equal_in_bounded_sample":caller_names(x)==caller_names(y),
            "fw114_resolved_calls":x["identified_callsite_evidence"],
            "fw115_resolved_calls":y["identified_callsite_evidence"],
            "raw_address_equivalence_assumed":False,
        })
    return {
        "source_class":"UNOFFICIAL_MIRROR_UNAUTHENTICATED",
        "firmware114_libsif_sha256":a["libsif_sha256"],
        "firmware115_libsif_sha256":b["libsif_sha256"],
        "inspected_version_specific_functions":len(report),
        "functions":report,
        "static_arm_bl_only":True,
        "fully_resolved_runtime_control_flow":False,
        "firmware114_encoder_and_exif_native_abi_verified":False,
        "real_picture_wizard_to_jpeg_hook_verified":False,
        "firmware_flash_permitted":False
    }
