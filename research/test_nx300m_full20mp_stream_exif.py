#!/usr/bin/env python3
"""Synthetic 5546×3714 Y/C420 -> independent LUT65 -> JPEG + Exif proof."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from nx300m_jpeg_exif_provenance_gate import inspect_pair

ROOT=Path(__file__).resolve().parent.parent
WIDTH,HEIGHT=5546,3714
MAX_RSS_KIB=128*1024

def run():
    module=ROOT/".build/libnx300m_filmcore_nolibc.so"
    runner=ROOT/".build/test_nx300m_full20mp_stream_exif"
    if not module.is_file() or not runner.is_file():
        raise ValueError("Missing host executable or independent no-libc module")
    out=ROOT/"outputs"
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nx300m_full20_",dir=out) as directory:
        base=Path(directory)/"baseline.jpg"
        film=Path(directory)/"film.jpg"
        p=subprocess.run([str(runner.resolve()),str(module.resolve()),
                          str(base),str(film)],cwd=ROOT,capture_output=True,
                         text=True,timeout=240,check=False)
        if p.returncode:
            raise ValueError("20MP host stream failure: "+p.stderr[:1000])
        records=[s.partition(" ")[2] for s in p.stdout.splitlines()
                 if s.startswith("NX300M_FULL20MP_JSON ")]
        if len(records)!=1:
            raise ValueError("No unique host 20MP report")
        stats=json.loads(records[0])
        if (stats.get("width"),stats.get("height"),stats.get("pixel_count"))!=(
                WIDTH,HEIGHT,WIDTH*HEIGHT):
            raise ValueError("Wrong full resolution pixel count")
        for key,value in (("host_only",True),("firmware_flash_safe",False),
                          ("on_device_20mp_verified",False),
                          ("input_planes_and_lut_unchanged",True),
                          ("destination_overwrite_blocked",True),
                          ("exif_synthetic_only",True),("film_grid",65),
                          ("baseline_grid",2)):
            if stats.get(key)!=value:
                raise ValueError("Host test safety violation: "+key)
        rss=stats.get("peak_rss_kib")
        if type(rss) is not int or not 0<rss<=MAX_RSS_KIB:
            raise ValueError("RSS exceeded 128MiB host regression guard")
        for k in ("baseline_seconds","film_seconds"):
            val=stats.get(k)
            if not isinstance(val,(float,int)) or not 0<val<240:
                raise ValueError("Invalid test duration")
        chk=inspect_pair(base,film,True,WIDTH,HEIGHT)
        if (chk["original_sha256"]==chk["processed_sha256"] or
            chk["makernote_size"]!=8 or
            chk["app_markers_preserved"] is not True or
            chk["native_samsung_exif_abi_verified"] is not False or
            chk["firmware_flash_permitted"] is not False):
            raise ValueError("Host JPEG / EXIF integrity mismatch")
        result=dict(host_only=True,real_camera_20mp_verified=False,
                    firmware_flash_permitted=False,width=WIDTH,height=HEIGHT,
                    pixel_count=WIDTH*HEIGHT,
                    baseline_sha256=chk["original_sha256"],
                    film_sha256=chk["processed_sha256"],
                    exif_sha256=chk["exif_app1_sha256"],
                    synthetic_makernote_sha256=chk["makernote_sha256"],
                    host_peak_rss_kib=rss,host_rss_guard_kib=MAX_RSS_KIB,
                    baseline_seconds=stats["baseline_seconds"],
                    film_seconds=stats["film_seconds"],
                    independent_lut_grid=65,
                    rgb_staging_rows=1,
                    copy_inputs_unchanged=True,
                    no_overwrite=True,
                    all_test_jpegs_deleted_after_verification=True)
    return result

def main():
    try:
        print("NX300M_FULL20MP_PROOF_JSON "+json.dumps(run(),sort_keys=True))
        print("PASS full 20.6MP HOST-only streamed LUT65 JPEG + synthetic MakerNote parity")
        return 0
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print("REJECT full 20.6MP host test: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
