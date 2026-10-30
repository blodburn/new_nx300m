# NX300M 1.14 native integration gates — NO FLASH

> **Firmware version correction (2026-10-31):** The private research file named `nx300m_mfw_1.1.bin` has an internal SLP header identifying the underlying Samsung firmware as **NX300M 1.15**. `MFW 1.1` denotes the modified firmware release, not Samsung-native firmware 1.1. This does not establish a match to target stock 1.14.


**Current release status: host-only research.** No deployable camera firmware, ARM patch, native capture hook, or tested recovery mechanism has been produced.

## Verified in the research environment

- Original NX300M **MFW 1.1** executable analysis provides a 36-byte `CYcc` descriptor layout with `Y0/Y1/C0/C1` pointer metadata; the original main-still processing appears configured for type-1 4:2:0 Y/C. These are observations of 1.1 research firmware, **not** established binary matches to installed **1.14**.
- HOST image algorithms can process unpacked Bayer16 high-bit values and stream RGB8 rows to an independent JPEG encoder (standard 4:4:4 or 4:2:0).
- Two hypothetical interleaved chroma layouts have been modeled and tested in copies of host-owned memory. The physical camera order and exact matrix/range remain unknown.
- A **read-only probe** reports hypothesis errors from COPIED Y/C planes and a corresponding RGB888 reference. It refuses to choose a chroma byte order for ambiguous or mismatched data.

## Required BEFORE a camera-side implementation

1. Obtain and authenticate the **exact original 1.14** binary used by the target NX300M. Verify original-file hashes and architecture/version. **Never substitute an offset from the MFW 1.1 image into 1.14 without proving identity.**
2. Establish **reversible, full-brick recovery** and a reliable method to preserve device-unique calibration data. Without it, modified firmware installation remains out of scope.
3. Obtain trustworthy **read-only, same-stage** captures of the processed still Y plane, chroma plane, descriptor, actual strides, crop offsets and pixel range. Prove their pointer ownership, alloc lifetime and any required DMA/cache coherency before considering writes.
4. Establish true native chroma byte order, Bayer black/white level, the ISP color matrices, and original JPEG encoder input contract. An ordinary exported JPEG/SRW **cannot** provide a same-stage DMA plane dump.
5. Prove native JPEG EXIF/MakerNotes and RAW+JPEG logic are preserved, one JPEG per shutter in JPEG-only mode, a single untouched SRW in RAW-only mode, with safe abort and Samsung Original bypass.
6. Complete an isolated host test reproducing the measured native buffers before a separately reviewed, reversible camera integration.

## Offline read-only color-order probe

```sh
make probe
./.build/ycc420_probe WIDTH HEIGHT Y_STRIDE C_STRIDE RGB_STRIDE copied_y.bin copied_c.bin matching_rgb888.bin
```

The input reference must have **identical stage, geometry and crop** to the copied Y/C planes. Results report mean absolute errors against a **full-range BT.601, interleaved C-plane hypothesis**, not a reliable determination of physical hardware layout. Inconclusive output is expected for low-color images or different ISP matrices/ranges. This program never dereferences a camera pointer, contacts the device, or modifies its inputs.

## Memory warning

The previous full-resolution 4:2:0 host JPEG encoder processes with roughly 42 MiB process RSS, because it does not stage a full RGB8 image. An alternative modeled Y/C two-region frame uses roughly 80.6 MiB host process RSS. The **real NX300M 1.14 ISP and hardware encoder have not been measured**; no on-camera memory savings, speed or image quality gain can be claimed.
