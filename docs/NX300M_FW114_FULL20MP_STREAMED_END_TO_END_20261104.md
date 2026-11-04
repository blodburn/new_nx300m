# NX300M FW1.14 — 20.6MP no-libc row streaming → host JPEG/Exif proof (2026-11-04)

**Host-only development. No Samsung firmware, camera DMA, live sensor, proprietary encoder, or camera installation was used.**

## What has now been executed

```text
           5546 x 3714 = 20,597,844 synthetic pixels
                           |
      immutable separately allocated Y/C 4:2:0 copies
      Y stride 5562 B, C stride 5562 B
                           |
            no-libc independent LUT engine
                 BT.601 FULL hypothesis
                           |
                  +--------+--------+
                  |                 |
          2-grid neutral       65x65x65 study LUT
                  |                 |
            ONE RGB row          ONE RGB row
                  |                 |
             JPEG 4:2:0          JPEG 4:2:0
                  |                 |
          synthetic_baseline     synthetic_film
                  +--------+--------+
                           |
         complete JPEG SOI/SOF0/SOS/EOI and 4:2:0
         APP1 Exif exact byte equality
         synthetic TIFF MakerNote 0x927C exact hash
         different entire JPEG SHA-256 digests
         unchanged copied source planes and LUT
         create-only JPEG file publishing
         ephemeral images deleted on success/failure
                           |
                      HOST PASS
                           |
               Actual camera FW1.14: NO-GO
```

## CI results on Linux host

- Real full-size frame: **5546 × 3714 = 20,597,844 pixels**.
- Two JPEG passes: 2-grid neutral baseline **2.930 seconds**, independent 65-grid film study **3.094 seconds** (one sample each; not a p95 or a device benchmark).
- Host process peak RSS: **34,784 KiB ≈ 33.97 MiB**. The reproducible Linux guard is **128 MiB**. This does not show NX300M available RAM or thermal/capture delay.
- Full 65³ LUT: 274,625 nodes, 2,197,000 bytes. Source plane copies are retained and checked for mutation. No full-frame RGB888 temporary is allocated by the JPEG streaming adapter.
- Exact synthetic APP1/MakerNote preservation, one baseline JPEG and one film JPEG, different file SHA-256 hashes, no-overwrite, all temporary outputs deleted.
- The neutral 2-grid baseline is a newly encoded **synthetic host JPEG**, not the untouched Samsung Original JPEG. The 65-grid film study is an independent invented LUT; no Fuji/Leica original secret curve/calibration is asserted.

## Reproduce

```sh
make full20mp-test
```

This builds a no-libc computation shared library, a host-only JPEG adapter, runs the full 20.6MP harness, checks Exif/APP1 and TIFF MakerNote via a read-only parser, enforces the process RSS engineering guard and removes temporary test files. The dedicated GitHub Actions workflow is `.github/workflows/nx300m-full20mp-host-proof.yml`.

## Remaining physical verification

- Authenticate a vendor-original Samsung NX300M FW **1.14** image and compare real `libmm-photo`/`libsif`/`libcapture` against version-matched symbols. Prior modified MFW research embeds FW **1.15** and must not be treated as 1.14.
- Observe real same-stage Y/C420 and RGB copies, frame ownership/lifetime, matrix/range and byte order, cache/DMA coherency, while leaving the camera unmodified.
- Validate native encoder ABI, original Exif and proprietary MakerNotes, exact output JPEG quality, actual on-device 20.6MP RAM/latency and coexistence with RAW.
- Establish independent backup and full-brick recovery with device-specific calibration preservation before any firmware install.

**The host proof cannot authorize device modification, patching or flashing.**
