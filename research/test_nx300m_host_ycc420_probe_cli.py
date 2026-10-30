#!/usr/bin/env python3
"""Synthetic file-to-file test of OFFLINE read-only color-order hypothesis CLI.
No camera, firmware, private RAW images or real sensor data are read.
"""
from __future__ import annotations
import pathlib
import subprocess
import tempfile
import unittest

W, H, YSTRIDE, CSTRIDE, RSTRIDE = 24, 16, 32, 32, 24*3+5
COLORS = [(240,32,16),(20,60,245),(20,220,38),
          (245,160,12),(175,18,225),(35,212,220)]
TOOL=pathlib.Path(".build/ycc420_probe").resolve()

def sat(n:int)->int:
    return min(255,max(0,n))

def channel(p:tuple[int,int,int])->tuple[int,int,int]:
    r,g,b=p
    return (sat((19595*r+38470*g+7471*b+32768)>>16),
            sat(128+((-11059*r-21709*g+32768*b+32768)>>16)),
            sat(128+((32768*r-27439*g-5329*b+32768)>>16)))

def fixture(order:int,neutral:bool=False)->tuple[bytes,bytes,bytes]:
    pixels=[[((128,128,128) if neutral else
              COLORS[(x//2+(y//2)*3)%len(COLORS)])
             for x in range(W)]for y in range(H)]
    yr=bytearray(YSTRIDE*H)
    c=bytearray(CSTRIDE*(H//2))
    rgb=bytearray(RSTRIDE*H)
    for y in range(H):
        for x in range(W):
            p=pixels[y][x]
            rgb[y*RSTRIDE+x*3:y*RSTRIDE+x*3+3]=bytes(p)
            yr[y*YSTRIDE+x]=channel(p)[0]
    for y in range(0,H,2):
        for x in range(0,W,2):
            cb=sum(channel(pixels[y+dy][x+dx])[1] for dy in range(2) for dx in range(2))
            cr=sum(channel(pixels[y+dy][x+dx])[2] for dy in range(2) for dx in range(2))
            first,second=( (cb+2)//4,(cr+2)//4 )
            if order==2:first,second=second,first
            c[(y//2)*CSTRIDE+x]=first
            c[(y//2)*CSTRIDE+x+1]=second
    return bytes(yr),bytes(c),bytes(rgb)

def run_case(files:tuple[bytes,bytes,bytes])->subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="nx300m-readonly-ycc-") as tmp:
        paths=[pathlib.Path(tmp)/x for x in ("Y.bin","C.bin","ref.rgb")]
        for p,d in zip(paths,files):
            p.write_bytes(d)
        return subprocess.run([str(TOOL),str(W),str(H),
                               str(YSTRIDE),str(CSTRIDE),str(RSTRIDE),
                               *(str(p) for p in paths)],
                              text=True,capture_output=True,check=False)

class HostProbeCLITest(unittest.TestCase):
    def test_cbcr(self)->None:
        p=run_case(fixture(1))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("result=CBCR_UNDER_BT601_HYPOTHESIS",p.stdout)
        self.assertIn("y_mae=0.000",p.stdout)
    def test_crcb(self)->None:
        p=run_case(fixture(2))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("result=CRCB_UNDER_BT601_HYPOTHESIS",p.stdout)
    def test_neutral_is_inconclusive(self)->None:
        p=run_case(fixture(1,neutral=True))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("result=INCONCLUSIVE",p.stdout)
    def test_wrong_stage_is_inconclusive(self)->None:
        y,c,r=fixture(1)
        p=run_case((bytes([255])*len(y),c,r))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("result=INCONCLUSIVE",p.stdout)
    def test_truncated_chroma_rejected(self)->None:
        y,c,r=fixture(1)
        p=run_case((y,c[:(H//2-1)*CSTRIDE+W-1],r))
        self.assertEqual(p.returncode,2)
        self.assertIn("REJECT",p.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
