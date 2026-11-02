# NX300M FW1.14 — memory / ISP / JPEG integration gates

**Release status: NO-GO for camera. Host-only evidence and new RGB888 -> JPEG adapter.**

## Firmware identity: do not promote old modified evidence

- Required: exact NX300M original **Samsung FW 1.14** binary plus verified SHA-256 / original acquisition. Not supplied here.
- Existing private MFW 1.1 research image has Samsung **SLP FW 1.15** internal header; not proof for 1.14.
- Static older reference shows 36-byte CYcc descriptor with Y0/Y1/C0/C1 accessors, type-1 Y/C 4:2:0, and legacy native `CMmDeviceDriver::EncodeYcc` calls. Nothing proves exact original FW1.14 ABI, safe buffer lifetime or actual physical pixel order.
- No verified restoration/full-brick recovery or backup of serial-specific lens/sensor calibration; flash prohibited.

## HOST JPEG pathway added

1. Source: externally supplied, **already copied host RGB888**; no camera pointer, no DMA or ISP hook.
2. Convert sRGB bytes to linear RGB12 (existing `nx_preview_processor` tables).
3. Apply externally supplied 18/33/65 RGB12 LUT using `nx_lut_grid_host_apply` to each pixel. No Picture Wizard changes.
4. Encode result with existing separate host ISO/JFIF 4:2:0 JPEG encoder, one row at a time. Optional caller-supplied original Exif APP1 is copied, never invented.
5. Create-only destination. On failure, abort staging and do not overwrite an existing JPEG. Original bypass means no output and no re-encode.
6. Host regression checks source immutability, 18/65 identity/nonidentity output, JPEG bytes, EXIF APP1 exact preservation, overwrite and invalid input refusal.

This **does not** prove that Samsung native MakerNotes, image date, SRW or lens metadata can be copied intact, nor that a host JPEG path runs on ARM firmware.

## Host memory lower-bound illustration (not camera RAM measurement)

| Item | Computation | Bytes |
|---|---:|---:|
| 20.60 MP copied RGB888 input | 5546×3714×3 | 61,793,532 |
| One 65³ RGB12 LUT | 65³×8 | 2,197,000 |
| One temporary RGB row | 5546×3 | 16,638 |
| Minimum JPEG 4:2:0 16-row scanline staging | 5546×3×16 | 266,208 |
| Known subtotal | Sum above | 64,273,378 (~61.30 MiB) |

Other allocations, encoder data structures, OS, image acquisition, ownership/coherency, stack, fragmentation and native ISP buffers are **not counted**. The source RGB copy is already owned by caller, and the new adapter allocates just a row, preview lookup tables and JPEG writer buffers. The known subtotal is NOT a safe camera memory budget or measured RSS. 65³ LUT alone is **2,197,000 B (~2.10 MiB)** vs 18³ **46,656 B (~45.6 KiB)**, about 47.1×.

## Required before camera installation

1. Authenticate actual original Samsung NX300M FW1.14 image and compare relevant ELF symbols against source firmware metadata; do not reuse FW1.15 offsets.
2. Demonstrate full-brick recovery and safe preservation of camera-specific calibration, identifiers and firmware backups.
3. Obtain read-only SAME-STAGE Y/C and RGB captures with validated bytes, plane strides, crop, color matrix, color range, chroma order, actual buffer lifetime, and cache/DMA coherency.
4. Benchmark real camera free RAM and capture-to-save latency under 65³, including frame ownership and thermal impact.
5. Verify native JFIF/Exif/MakerNotes, RAW/JPEG partial-save semantics and unmodified Samsung Original for all save modes.
6. Only then consider a separate, reversible ARM/Tizen implementation review. No flash performed.

## Source / tests

- `research/nx300m_host_lutgrid_jpeg.[ch]`: independent PC-only copy RGB888 -> LUT 18..65 -> JPEG 420.
- `research/test_nx300m_host_lutgrid_jpeg.c`: identity and invert 18/65 synthetic JPEG oracle; file safety; APP1 preservation.
- `.github/workflows/spektrafilm-profile-check.yml`: ephemeral real PROVIA100F+Crystal Archive LUT65 -> C RGB888 JPEG; derivative LUT/JPEG not uploaded.
- `docs/NX300M_114_INTEGRATION_GATES.md`: prior firmware authenticity and physical memory constraints.

## Full-resolution host performance / memory reproducibility

The 65³ LUT + independent JPEG adapter is now exercised on deterministic
**5546×3714 = 20,597,844-pixel** synthetic RGB888 with the actual ephemeral
SpektraFilm PROVIA100F LUT. A separate small 1024×768 workload repeats 5
passes for p95, and the full 20.6MP workload runs once. The host benchmark
reports elapsed time, process high-water RSS (Linux ru_maxrss), encoded JPEG
bytes, and original-input/LUT checksum stability. It verifies the exact EXIF
APP1 payload is preserved and refuses destination overwrite. Each output
JPEG is deleted after verification; neither derivative LUT nor JPEG is
uploaded. One full-size timing is **not** a statistical p95 latency estimate.

CI enforces a host-runner RSS guard of 256MiB (this is an engineering
regression threshold, NOT proven NX300M available RAM). Optional reproduction:

    make bench-lut65 LUT65_PATH=/private/authorized_profile.nx65.txt

Recheck original FW1.14 identity, actual ISP output, native ABI and recovery
before ANY camera target integration. Old modified MFW1.1 = embedded 1.15.
