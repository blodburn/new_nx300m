#!/usr/bin/env python3
"""Read-only JPEG SOF sampling probe for a *real* NX300M captured JPEG.

Standard JPEG chroma output 4:2:0/4:2:2/4:4:4 can be confirmed from SOF
components; this does NOT prove upstream native DMA CbCr byte ordering.
No files modified, no image decoding/OCR or network required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys

SOF_MARKERS={0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}
MARKER_LABEL={0xC0:"Baseline DCT",0xC2:"Progressive DCT"}
class JPEGHeaderError(ValueError): pass

def probe_bytes(data:bytes)->dict:
    if len(data)<4 or data[:2]!=b"\xff\xd8":
        raise JPEGHeaderError("Not a JPEG SOI stream")
    ptr=2
    while ptr<len(data):
        if data[ptr]!=0xff:
            raise JPEGHeaderError("Invalid marker boundary before SOF")
        while ptr<len(data) and data[ptr]==0xff:ptr+=1
        if ptr>=len(data):break
        marker=data[ptr];ptr+=1
        if marker==0xD9:break
        if marker in (0xD8,0x01) or 0xD0<=marker<=0xD7:continue
        if ptr+2>len(data):raise JPEGHeaderError("Truncated marker length")
        length=int.from_bytes(data[ptr:ptr+2],"big")
        if length<2 or ptr+length>len(data):
            raise JPEGHeaderError("Truncated marker segment")
        seg=data[ptr+2:ptr+length]
        ptr+=length
        if marker==0xDA:break
        if marker not in SOF_MARKERS:continue
        if len(seg)<6:raise JPEGHeaderError("Incomplete SOF")
        depth=seg[0]
        height=int.from_bytes(seg[1:3],"big")
        width=int.from_bytes(seg[3:5],"big")
        n=seg[5]
        if not height or not width or n<1 or len(seg)!=6+3*n:
            raise JPEGHeaderError("Malformed SOF dimensions/components")
        comps=[]
        for i in range(n):
            ident,hv,quant=seg[6+i*3:9+i*3]
            h,v=hv>>4,hv&0x0f
            if not h or not v:raise JPEGHeaderError("Invalid sampling factor")
            comps.append({"id":ident,"h":h,"v":v,"qt":quant})
        subsampling="Unknown/nonstandard"
        if n==1:subsampling="Grayscale"
        elif n==3 and comps[1]["h"]==comps[1]["v"]==1 and comps[2]["h"]==comps[2]["v"]==1:
            h,v=comps[0]["h"],comps[0]["v"]
            subsampling={(2,2):"4:2:0",(2,1):"4:2:2",(1,1):"4:4:4",(1,2):"4:4:0"}.get((h,v),subsampling)
        return {
            "width":width,"height":height,"bit_depth":depth,
            "sof_marker":f"FF{marker:02X}",
            "jpeg_encoding":MARKER_LABEL.get(marker,"SOF JPEG family"),
            "components":comps,
            "chroma_subsampling":subsampling,
            "native_dma_cbcr_byte_order":"Not inferable from JPEG SOF",
        }
    raise JPEGHeaderError("No SOF frame header found")

def main(argv=None):
    p=argparse.ArgumentParser(description="Inspect actual JPEG SOF sampling only, never modifies files")
    p.add_argument("jpeg",nargs="+",type=pathlib.Path)
    args=p.parse_args(argv)
    report=[]
    for jpeg in args.jpeg:
        raw=jpeg.read_bytes()
        result=probe_bytes(raw)
        report.append({"file":str(jpeg),"size_bytes":len(raw),
                       "sha256":hashlib.sha256(raw).hexdigest(),**result})
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
