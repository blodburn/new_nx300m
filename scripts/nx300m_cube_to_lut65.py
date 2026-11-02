#!/usr/bin/env python3
"""Host-only offline .cube to 65^3 (or 33^3) 12-bit linear RGB LUT.

Runs strict empirical resampling QA against the supplied .cube before writing.
No SpektraFilm code, film profiles or derivative LUTs ship with this script.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import independent host bridge")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
bridge=load_module("nx_cube_bridge",ROOT/"scripts/nx300m_cube_to_lut18.py")
diag=load_module("nx_grid_diag",ROOT/"research/nx300m_lut_grid_diagnostics.py")
MAGIC="NX_LUT_RGB12_GRID_V1"

def convert(source:Path,output:Path,qa:Path,n:int=65,
            count:int=2048,peak_limit:float=12,mean_limit:float=2,
            source_name:str="external authorized .cube",
            license_id:str="UNVERIFIED_TEST_ONLY"):
    if n not in (33,65) or count<128 or count>20000:
        raise ValueError("Only grid 33/65, 128..20000 QA samples supported")
    if not math.isfinite(peak_limit) or not math.isfinite(mean_limit) or peak_limit<0 or mean_limit<0:
        raise ValueError("Invalid QA threshold")
    if source==output or source==qa or output==qa:
        raise ValueError("Paths must be distinct")
    if any(p.exists() or p.is_symlink() for p in (output,qa)):
        raise ValueError("Existing output/QA files may not be overwritten")
    if not output.parent.is_dir() or not qa.parent.is_dir():
        raise ValueError("Output folder does not exist")
    input_n,original,source_sha=bridge.parse_cube(source)
    measurements=diag.diagnostics(source,(n,),count)
    m=measurements["results"][0]
    if m["peak_8bit"]>peak_limit or m["mean_8bit"]>mean_limit:
        raise ValueError("Numerical resampling QA rejected: "+str(m))
    values=diag.build_grid(input_n,original,n)
    report={
        "schema":MAGIC,"status":"PASS_NUMERICAL_ONLY",
        "source_sha256":source_sha,"source_grid":input_n,
        "input_output_color_encoding":"sRGB/sRGB",
        "nx_nodes_color_encoding":"linear RGB12",
        "nx_grid":n,"nodes":len(values),
        "table_bytes":len(values)*8,
        "samples":count,"metrics":m,
        "qa_peak_limit_rgb8":peak_limit,"qa_mean_limit_rgb8":mean_limit,
        "source_name":source_name,"declared_license_id":license_id,
        "firmware_114_verified":False,"camera_installable":False,
        "copyright":"Preserve SpektraFilm attribution/CC BY-SA 4.0 if source LUT is a derivative. No third-party data in this repository.",
    }
    created_output=False
    created_qa=False
    sha=hashlib.sha256()
    def put(f,txt):
        encoded=txt.encode("ascii")
        f.write(encoded)
        sha.update(encoded)
    try:
        with output.open("xb") as f:
            created_output=True
            put(f,MAGIC+"\n")
            put(f,f"grid={n}\n")
            for r,g,b in values:
                put(f,f"{r} {g} {b}\n")
        report["lut_text_sha256"]=sha.hexdigest()
        with qa.open("x",encoding="utf-8") as f:
            created_qa=True
            json.dump(report,f,indent=2)
            f.write("\n")
    except BaseException:
        if created_output:output.unlink(missing_ok=True)
        if created_qa:qa.unlink(missing_ok=True)
        raise
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--qa",type=Path,required=True)
    parser.add_argument("--grid",type=int,choices=(33,65),default=65)
    parser.add_argument("--samples",type=int,default=2048)
    parser.add_argument("--max-error-8bit",type=float,default=12)
    parser.add_argument("--mean-error-8bit",type=float,default=2)
    parser.add_argument("--source-name",default="external authorized .cube")
    parser.add_argument("--license-id",default="UNVERIFIED_TEST_ONLY")
    opts=parser.parse_args(argv)
    try:
        r=convert(opts.input,opts.output,opts.qa,opts.grid,opts.samples,
                  opts.max_error_8bit,opts.mean_error_8bit,
                  opts.source_name,opts.license_id)
        print(json.dumps(r,indent=2))
        return 0
    except (ValueError,OSError) as e:
        print("NX_RGB12_GRID_CONVERSION_REJECTED: "+str(e),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
