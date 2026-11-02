#!/usr/bin/env python3
"""Offline diagnostic of LUT grid density, using input .cube only in ephemeral RAM.

No film profiles, node arrays, re-baked LUTs, or source colors are written.
Only aggregate numerical error statistics and input SHA-256 appear on stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

BRIDGE = Path(__file__).resolve().parents[1] / "scripts" / "nx300m_cube_to_lut18.py"
spec = importlib.util.spec_from_file_location("nx_lut_bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def build_grid(source_n, source, target_n):
    rows = []
    for b in range(target_n):
        for g in range(target_n):
            for r in range(target_n):
                s = tuple(bridge.encode_srgb(v / (target_n - 1))
                          for v in (r, g, b))
                out = bridge.sample_cube(source, source_n, s)
                rows.append(tuple(bridge.quant12(bridge.decode_srgb(v)) for v in out))
    return rows

def sample_fixed(nodes, target_n, linear):
    axes = []
    for c in linear:
        val = bridge.quant12(c)
        scaled = val * (target_n - 1)
        low, rem = divmod(scaled, 4095)
        high = min(target_n-1, low+1)
        factor = (rem * 65536 + 2047) // 4095
        axes.append((low, high, factor))
    (r0,r1,tr),(g0,g1,tg),(b0,b1,tb)=axes
    def at(r,g,b,c):return nodes[(b*target_n+g)*target_n+r][c]
    ans=[]
    for ch in range(3):
        p00=bridge.lerp_fixed(at(r0,g0,b0,ch),at(r1,g0,b0,ch),tr)
        p10=bridge.lerp_fixed(at(r0,g1,b0,ch),at(r1,g1,b0,ch),tr)
        p01=bridge.lerp_fixed(at(r0,g0,b1,ch),at(r1,g0,b1,ch),tr)
        p11=bridge.lerp_fixed(at(r0,g1,b1,ch),at(r1,g1,b1,ch),tr)
        a=bridge.lerp_fixed(p00,p10,tg)
        b=bridge.lerp_fixed(p01,p11,tg)
        ans.append(bridge.encode_srgb(bridge.lerp_fixed(a,b,tb)/4095))
    return tuple(ans)

def diagnostics(path:Path, grids:tuple[int,...]=(18,33,65),count:int=2048):
    if count<128 or count>20000 or len(grids)>5 or any(n<2 or n>65 for n in grids):
        raise ValueError("Invalid grid/count")
    n,source,sha=bridge.parse_cube(path)
    samples=[]
    for i in range(1,count+1):
        v=(bridge.halton(i,2),bridge.halton(i,3),bridge.halton(i,5))
        expected=bridge.sample_cube(source,n,tuple(bridge.encode_srgb(x) for x in v))
        samples.append((v,expected))
    results=[]
    for target in grids:
        packed=build_grid(n,source,target)
        errors=[]
        max_pos=None
        for v,expected in samples:
            got=sample_fixed(packed,target,v)
            err=max(abs(g-r)*255 for g,r in zip(got,expected))
            errors.append(err)
            if max_pos is None or err>max_pos[0]:
                max_pos=(err,v)
        errors.sort()
        def pct(q):return round(errors[min(count-1,math.ceil(q*count)-1)],5)
        results.append({
          "grid":target,"nodes":target**3,"rgb12_table_bytes":target**3*8,
          "peak_8bit":round(errors[-1],5),
          "mean_8bit":round(sum(errors)/count,5),
          "p95_8bit":pct(.95),"p99_8bit":pct(.99),
          "above_12":sum(v>12 for v in errors),
          "above_4":sum(v>4 for v in errors),
          "worst_input_linear_rgb":[round(x,5) for x in max_pos[1]],
          "below_original_nx18_peak_guard":errors[-1]<=12,
          "below_original_nx18_mean_guard":sum(errors)/count<=2
        })
    return {"input_sha256":sha,"source_cube_grid":n,"samples":count,
            "max_8bit_guard":12,"mean_8bit_guard":2,
            "results":results,"firmware_tested":False,
            "no_derivative_lut_output":True,
            "warning":"Host spectral model numerical resampling only, not camera quality or deployment permission"}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--samples",type=int,default=2048)
    p.add_argument("--grids",type=int,nargs="+",default=[18,33,65])
    p.add_argument("--github-summary",type=Path)
    opts=p.parse_args(argv)
    try:
        r=diagnostics(opts.input,tuple(opts.grids),opts.samples)
        print(json.dumps(r,indent=2,ensure_ascii=False))
        if opts.github_summary:
            with opts.github_summary.open("a",encoding="utf-8") as f:
                f.write("\n### NX300M LUT resampling grid analysis\n")
                f.write("\n| Grid | Nodes | Host table KiB | Peak RGB8 | Mean RGB8 | P99 RGB8 | >12 cases |\n")
                f.write("|---|---:|---:|---:|---:|---:|---:|\n")
                for item in r["results"]:
                    f.write(f'| {item["grid"]}³ | {item["nodes"]} | {item["rgb12_table_bytes"]/1024:.1f} | {item["peak_8bit"]} | {item["mean_8bit"]} | {item["p99_8bit"]} | {item["above_12"]} |\n')
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print("NX_LUT_GRID_DIAG_REJECTED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
