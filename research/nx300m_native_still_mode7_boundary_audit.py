#!/usr/bin/env python3
"""Read-only still-main address-mode-7 trace from old modified NX300M 1.15.

Verifies exact ARM instructions and PLT relocation symbols, not guessed C ABI.
This *does not* identify actual planar/interleaved Y/C packing or stock 1.14,
nor grant runtime camera/DMA access or firmware patch permission.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
import nx300m_pw_ui_bl_call_audit as arm
import nx300m_native_jpeg_abi_boundary_audit as abi

RECIPE="CRecipeStillSetting::GetMainImage("
ADDR="GetAddrFromCapImage("
# Strong semantic proof: setters get exact immediate enums, destination
# by exact ARM BL -> .plt -> R_ARM_JUMP_SLOT symbol.
RECIPE_CALLS=[
 (0x20b68c,0xe3a01002,0x20b690,"CCapImage::setImageFormat("),
 (0x20b698,0xe3a01001,0x20b69c,"CCapImage::setYccFormat("),
 (0x20b6a4,0xe3a01000,0x20b6a8,"CCapImage::setYccPackType("),
 (0x20b6bc,0xe3a01007,0x20b6c0,"CCapBuffer::setAddrType("),
]
OTHER_CALLS=[
 (0x20b6b0,"CCapImage::getBuffer("),
 (0x156ee0,"CCapImage::getBuffer("),
 (0x156eec,"CCapBuffer::getAddressType("),
 (0x157094,"CCapImage::getYccFormat("),
 (0x157274,"CCapImage::getYccFormat("),
]
# Control-flow witness: mode=7 is last in a guarded 8-way ARM branch
# table; the actual mode-7 body starts at 0x15714c.
DISPATCH={
 0x156ef4:0xe3530007, # cmp r3,#7
 0x156ef8:0x908ff103, # addls pc,pc,r3,lsl#2
 0x156f00:0xea000118, # mode 0 branch; exact old signature
 0x156f1c:0xea00008a, # mode 7 branch
 0x15714c:0xe51b202c, # mode7 Y0 (local value)
 0x157150:0xe51b3034,
 0x157154:0xe5832000,
 0x157160:0xe59b3008,
 0x157164:0xe5933000,
 0x157168:0xe0822003, # Y1=Y0+stride
 0x15716c:0xe51b3038,
 0x157170:0xe5832000,
 0x157174:0xe51b2024,
 0x157178:0xe51b303c,
 0x15717c:0xe5832000, # C0 set from local
 0x157180:0xe51b303c,
 0x157184:0xe5932000,
 0x157188:0xe59b3008,
 0x15718c:0xe5933000,
 0x157190:0xe0822003,
 0x157194:0xe59b3004,
 0x157198:0xe5832000, # C1=C0+stride
 0x15719c:0xe51b3038,
 0x1571a0:0xe5933000,
 0x1571a4:0xe3530000,
 0x1571a8:0x1a000006, # conditional fallback when Y1 input null
 0x1571c8:0xe51b303c,
 0x1571cc:0xe5933000,
 0x1571d0:0xe3530000,
 0x1571d4:0x1a00000a, # conditional C fallback
}
# JPEG sampling type 1 observed elsewhere does not imply byte order.
NO_HARDWARE_PROOF={
 "native_114_firmware_present_or_abi_verified":False,
 "live_mode7_activated_proven":False,
 "live_y0_y1_c0_c1_descriptors_observed":False,
 "native_ycc420_byte_order_and_siting_verified":False,
 "safe_owned_image_copy_proven":False,
 "native_encoder_receives_film_pixels_proven":False,
 "physical_camera_patch_or_flash_permitted":False,
}

def branch_to(opcode:int,pc:int)->int:
    if (opcode>>28)!=14 or ((opcode>>24)&15)!=10:
        raise ValueError("Expected unconditional ARM branch")
    disp=(opcode&0xffffff)<<2
    if disp&0x2000000:disp-=0x4000000
    return (pc+8+disp)&0xffffffff

def verify_mode7_bytes(blob:bytes,segs:list[tuple[int,int,int]])->dict:
    for pc,expected in DISPATCH.items():
        if abi.word(blob,segs,pc)!=expected:
            raise ValueError("Changed still-main mode7 address-dispatch instruction")
    if branch_to(abi.word(blob,segs,0x156f1c),0x156f1c)!=0x15714c:
        raise ValueError("Mode7 branch does not target expected block")
    return {
      "reference_last_mode":7,
      "computed_pc_switch_guard_0_through_7":True,
      "mode7_target_block_checked":True,
      "mode7_y1_stride_add_opcode_checked":True,
      "mode7_c1_stride_add_opcode_checked":True,
      "two_conditional_null_fallback_branches_checked":True,
      "opaque_pointer_arithmetic_not_pixel_format":True,
    }

def verify_recipe(blob:bytes,segs,functions:dict,relocs:dict[int,str])->dict:
    a=[(address,size) for name,(address,size) in functions.items() if name.startswith(RECIPE)]
    b=[(address,size) for name,(address,size) in functions.items() if name.startswith(ADDR)]
    if len(a)!=1 or len(b)!=1:
        raise ValueError("Missing unique capture recipe/address resolver symbols")
    recipe,recipe_size=a[0]
    addr,addr_size=b[0]
    result=[]
    def expect(site:int,prefix:str,base:int,size:int)->str:
        if not(base<=site<base+size):
            raise ValueError("Expected call outside matching function")
        target=arm.decode_arm_bl(abi.word(blob,segs,site),site)
        if target is None:raise ValueError("Expected direct ARM BL")
        got=abi.plt_got(blob,segs,target)
        mangled=relocs.get(got)
        if not mangled:raise ValueError("No PLT/GOT relocation for native call")
        name=arm.offline_tool(["c++filt"],mangled+"\n").strip()
        if not name.startswith(prefix):
            raise ValueError("Native setter/getter symbol identity changed")
        return name
    for constant_site,instruction,callsite,callee in RECIPE_CALLS:
        if abi.word(blob,segs,constant_site)!=instruction:
            raise ValueError("Still recipe native enum immediate changed")
        result.append({"enum_word_at":hex(constant_site),
                       "callsite":hex(callsite),
                       "native_method":expect(callsite,callee,recipe,recipe_size)})
    for site,callee in OTHER_CALLS:
        base,size=(recipe,recipe_size) if site==0x20b6b0 else (addr,addr_size)
        result.append({"callsite":hex(site),
                       "native_method":expect(site,callee,base,size)})
    return {"checked_recipe_and_mode7_getter_calls":len(result),
            "source_backed_callsite_identities":result,
            "main_image_image_format":2,
            "main_image_ycc_format":1,
            "main_image_ycc_pack":0,
            "main_image_address_mode":7}

def inspect(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>arm.MAX_BYTES:
        raise ValueError("Expected private, bounded research ELF")
    blob=path.read_bytes()
    segs=arm.validate_header(blob)
    functions=abi.named_functions(path)
    reloc=abi.relocations(arm.offline_tool(["readelf","-Wr",str(path)]))
    return {
        "scope":"older modified MFW 1.1 / Samsung SLP 1.15 ONLY",
        "native_main_still_configuration":verify_recipe(blob,segs,functions,reloc),
        "native_mode7_code":verify_mode7_bytes(blob,segs),
        "limits":NO_HARDWARE_PROOF.copy(),
    }

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture-lib",type=Path,required=True)
    p.add_argument("--summary",action="store_true")
    args=p.parse_args(argv)
    try:
        result=inspect(args.capture_lib)
        if args.summary:
            result["native_main_still_configuration"].pop("source_backed_callsite_identities")
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,struct.error,OSError) as exc:
        print("NATIVE_MODE7_REJECTED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
