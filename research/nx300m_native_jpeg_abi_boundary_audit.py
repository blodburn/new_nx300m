#!/usr/bin/env python3
"""Offline NX300M old-research JPEG ABI cross-ELF proof, never camera code.

Strictly checks modified-MFW 1.1 Samsung SLP 1.15 libmm-photo.so and libsif.so.
The exact ARM BL -> PLT stub -> R_ARM_JUMP_SLOT relocation is resolved.
This does NOT prove original NX300M 1.14 compatibility or physical JPEG DMA.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm

ENCODER="CMmDeviceDriver::EncodeYcc("
PARSER="DscJfifHal::Parse("
EDGES=[
 (0x34cb8,"CYcc::GetY0()"),
 (0x34cc8,"CYcc::GetY1()"),
 (0x34cd8,"CYcc::GetC0()"),
 (0x34ce8,"CYcc::GetC1()"),
 (0x34cf8,"CYcc::GetWidth()"),
 (0x34d08,"CYcc::GetHeight()"),
 (0x34d18,"CYcc::GetStride()"),
 (0x34d78,"DscImage::EncodeYCC("),
]
SOF={
 0x294a8:0xe55b301b,0x294ac:0xe3530021,0x294b0:0x1a000003,
 0x294b4:0xe51b3044,0x294b8:0xe3a02000,0x294bc:0xe5832000,
 0x294c4:0xe55b301b,0x294c8:0xe3530022,0x294cc:0x1a000003,
 0x294d0:0xe51b3044,0x294d4:0xe3a02001,0x294d8:0xe5832000,
}

def word(blob:bytes,segs:list[tuple[int,int,int]],address:int)->int:
    for base,size,off in segs:
        if base<=address and address+4<=base+size:
            return struct.unpack_from("<I",blob,off+address-base)[0]
    raise ValueError("ARM address outside executable file-backed load")

def ror32(value:int,bits:int)->int:
    bits%=32
    return ((value>>bits)|(value<<(32-bits)))&0xffffffff if bits else value

def immediate(word_value:int)->int:
    return ror32(word_value&255,2*((word_value>>8)&15))

def plt_got(blob:bytes,segs:list[tuple[int,int,int]],target:int)->int:
    """Decode the three-instruction ARM PLT entry, do not guess PLT index."""
    a=word(blob,segs,target)
    b=word(blob,segs,target+4)
    c=word(blob,segs,target+8)
    # ADD ip,pc,#imm ; ADD ip,ip,#imm ; LDR pc,[ip,#imm]!
    if ((a&0xfffff000)!=0xe28fc000 or
        (b&0xfffff000)!=0xe28cc000 or
        (c&0xfffff000)!=0xe5bcf000):
        raise ValueError("Unknown ARM PLT stub, cannot resolve symbol")
    return (target+8+immediate(a)+immediate(b)+(c&0xfff))&0xffffffff

def relocations(text:str)->dict[int,str]:
    active=False
    got={}
    for line in text.splitlines():
        if line.startswith("Relocation section '"):
            active=line.startswith("Relocation section '.rel.plt'")
            continue
        if not active:continue
        m=re.match(r"^\s*([0-9a-fA-F]+)\s+\S+\s+R_ARM_JUMP_SLOT"
                   r"\s+\S+\s+(\S+)",line)
        if not m:continue
        address=int(m.group(1),16)
        symbol=m.group(2).split("@")[0]
        if address in got and got[address]!=symbol:
            raise ValueError("Relocation GOT address reused")
        got[address]=symbol
    if not got:raise ValueError("Missing ARM .rel.plt JUMP_SLOT relocations")
    return got

def named_functions(path:Path)->dict[str,tuple[int,int]]:
    functions=arm.parse_functions(arm.offline_tool(["readelf","-Ws",str(path)]))
    keys=list(functions)
    names=arm.offline_tool(["c++filt"],"\n".join(raw for _,raw in keys)+"\n").splitlines()
    if len(keys)!=len(names):raise ValueError("Incomplete ELF symbol demangling")
    return {name:(addr,functions[addr,raw]) for (addr,raw),name in zip(keys,names)}

def resolved_calls(blob:bytes,segs,funcs:dict[str,tuple[int,int]],
                   got_to_symbol:dict[int,str])->list[dict]:
    fn=[(address,size) for name,(address,size) in funcs.items()
        if name.startswith(ENCODER)]
    if len(fn)!=1:raise ValueError("Missing unique old-reference encoder")
    start,size=fn[0]
    found=[]
    for site,expected in EDGES:
        if not(start<=site<start+size):
            raise ValueError("Expected ARM BL outside encoder symbol")
        opcode=word(blob,segs,site)
        target=arm.decode_arm_bl(opcode,site)
        if target is None:
            raise ValueError("Missing direct ARM BL at expected encoder callsite")
        got=plt_got(blob,segs,target)
        symbol=got_to_symbol.get(got)
        if not symbol:raise ValueError("PLT got address absent in relocations")
        decoded=arm.offline_tool(["c++filt"],symbol+"\n").strip()
        if not decoded.startswith(expected):
            raise ValueError("Encoder callsite targets wrong imported native method")
        found.append({"callsite":hex(site),"symbol":decoded,
                      "plt_target":hex(target),"relocation_got":hex(got)})
    return found

def validate_sof_switch(blob:bytes,segs,
                        funcs:dict[str,tuple[int,int]])->dict:
    fn=[(address,length) for name,(address,length) in funcs.items()
        if name.startswith(PARSER)]
    if len(fn)!=1:raise ValueError("Missing unique old-reference JPEG parser")
    start,length=fn[0]
    for pc,opcode in SOF.items():
        if not start<=pc<start+length or word(blob,segs,pc)!=opcode:
            raise ValueError("JPEG SOF YCC type branch changed")
    return {"SOF_component_sampling_0x21":"YCC type 0 (4:2:2)",
            "SOF_component_sampling_0x22":"YCC type 1 (4:2:0)",
            "decoder_known_current_camera_114":False}

def inspect(capture:Path,sif:Path)->dict:
    for path in (capture,sif):
        if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
            raise ValueError("Required local bounded research ELF, not camera")
    enc=capture.read_bytes();other=sif.read_bytes()
    enc_segs=arm.validate_header(enc)
    sif_segs=arm.validate_header(other)
    enc_funcs=named_functions(capture)
    sif_funcs=named_functions(sif)
    got=relocations(arm.offline_tool(["readelf","-Wr",str(capture)]))
    calls=resolved_calls(enc,enc_segs,enc_funcs,got)
    fmt=validate_sof_switch(other,sif_segs,sif_funcs)
    return {
      "scope":"modified MFW 1.1; embedded Samsung SLP 1.15 reference ONLY",
      "encoder":"CMmDeviceDriver::EncodeYcc(CYcc&, unsigned int)",
      "callsite_to_plt_to_relocation_evidence":calls,
      "expected_native_getter_and_encoder_calls":len(EDGES),
      "native_jpeg_parser_sof_sampling_type_evidence":fmt,
      "codec_actual_pixel_layout_420_proven":False,
      "encoder_call_executed_for_film_pixels_proven":False,
      "picture_wizard_only_is_sufficient":False,
      "original_firmware_114_binary_or_abi_verified":False,
      "device_flash_patch_permitted":False,
    }

def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mm-photo",type=Path,required=True)
    ap.add_argument("--sif",type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        print(json.dumps(inspect(args.mm_photo,args.sif),indent=2,ensure_ascii=False))
        return 0
    except (ValueError,OSError,struct.error) as exc:
        print("NATIVE_JPEG_ABI_REJECTED: "+str(exc),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
