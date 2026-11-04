# NX300M FW1.14 — actual photo Y/C → JPEG input ABI and copy/resize boundary

**Scope:** read-only ARM32 static analysis of actual, separately extracted *unofficial-mirror* FW1.14 and FW1.15 `libmm-photo.so`, rechecked in ephemeral CI. No physical camera, firmware patch, access to DMA buffers, or camera installation. This report concerns **buffer argument wiring**, not a film profile simulation.

## New native code findings

```text
FW1.14 libmm-photo.so
    CMmDeviceDriver::EncodeYcc(CYcc&, unsigned) @ 0x34b18
       |
       +-- CYcc::GetType             @ 0x34b34; 0x34bec; 0x34c1c
       +-- CYcc::GetSize             @ 0x34b60
       +-- CMemoryPool::GetInstance  @ 0x34b64
       +-- CMemoryPool::GetAddr      @ 0x34b74
       +-- CYcc constructor         @ 0x34b8c
       +-- CMmDeviceDriver::ResizeImage @ 0x34bac [branch, NOT all-path proof]
               +-- ipcs_several_resize @ 0x33660
               +-- ipcs_one_resize     @ 0x33670
       |
       +-- DscImage::GetInstance     @ 0x34ca8
       +-- CYcc::GetY0               @ 0x34cb8 -> r6 -> JPEG r1
       +-- CYcc::GetY1               @ 0x34cc8 -> r5 -> JPEG r2
       +-- CYcc::GetC0               @ 0x34cd8 -> r4 -> JPEG r3
       +-- CYcc::GetC1               @ 0x34ce8 -> r9 -> JPEG [sp+0]
       +-- CYcc::GetWidth            @ 0x34cf8 -> r10
       +-- CYcc::GetHeight           @ 0x34d08 -> r8
       +-- CYcc::GetStride           @ 0x34d18
       |
       +-- DscImage::EncodeYCC       @ 0x34d78
                    |
                    v
          independently proven FW1.14 native
          DscJPEG::TaskMain → DscJfif::JpegEncode
          → tDscHal[+8] → DscJfifHal::Encode

    SEPARATE native BlockCopy methods:
      CMmDeviceDriver::BlockCopy(CYcc&,sYccAddr) @ 0x34480
           -> ep_bblt_ycc_copy @ 0x3450c
      CMmDeviceDriver::BlockCopy(CYcc&,CYcc&) @ 0x34570
           -> ep_bblt_ycc_copy @ 0x345e8

    EncodeYcc DOES NOT DIRECTLY BL either BlockCopy overload.
    Named ResizeImage direct BL @ 0x34bac exists, but proving
    whether and when that branch executes requires more work.
```

## Verified ARM ABI

The original 644-byte `EncodeYcc` body retains getter returns in `r6=Y0`, `r5=Y1`, `r4=C0`, `r9=C1`, `r10=Width`, `r8=Height`. At native `DscImage::EncodeYCC` callsite `0x34d78`, exact ARM `MOV` instructions establish:

| Native register | Value | Source ARM opcode site |
|---|---|---|
| `r0` | `DscImage` instance | `0x34d68 MOV r0,r7` |
| `r1` | `Y0` | `0x34d6c MOV r1,r6` |
| `r2` | `Y1` | `0x34d70 MOV r2,r5` |
| `r3` | `C0` | `0x34d74 MOV r3,r4` |

The following eleven AAPCS stack slots are passed into `DscImage::EncodeYCC` at the same callsite.

| SP byte offset | Native input | Static ARM producer |
|---:|---|---|
| 0 | C1 | `r9` |
| 4 | auxiliary uint #5 | `0` |
| 8 | auxiliary uint #6 | `0` |
| 12 | auxiliary uint #7 | `[fp-104]` |
| 16 | Width | `r10` |
| 20 | Height | `r8` |
| 24 | Stride | `r3` (GetStride return) |
| 28 | `eImgYCCType` | `[fp-40]` |
| 32 | `eImgYCCPackType` | `[fp-44]` |
| 36 | `eImgQuality` | literal `2` |
| 40 | last integer | literal `2000` |

These are static instruction-to-ABI observations. The meaning of the auxiliary arguments, actual `Y/C` memory layout, CbCr vs CrCb, DMA/cache coherency, free/ownership time and real sensor format are **not** proven. `Y0/Y1/C0/C1` are addresses or getter return words, not film pixel measurements.

## Implementation and evidence

- `research/nx300m_fw114_photo_ycc_copy_boundary.py`: the real FW1.14 and FW1.15 symbol-body, imported method edges, getter instruction sequence, ARM register and full JPEG stack ABI, separate copy and resize method call graph. No binary artifacts exported.
- `research/test_nx300m_fw114_photo_ycc_copy_boundary.py`: synthetic ARM call window, register swap and incorrect stack offsets fail-closed regression tests.
- `research/nx300m_fw114_native_elf_diff.py`: adds version-local comparison using previously private-extracted ELF paths.
- `.github/workflows/nx300m-fw114-native-elf-diff.yml`: requires exactly verified Y0/Y1/C0/C1 and stack mappings on real mirror FW1.14 and FW1.15, recognizes both native `ep_bblt_ycc_copy` functions and both `ipcs_*_resize` functions. It **rejects** claims that host evidence proves safe DMA ownership.

## What this changes for the independent Film Simulator

The JPEG input ABI is now much more concrete: it identifies what native function accepts Y/C descriptors and how dimensions, stride, type, packing and quality reach it. This supports designing a **read-only on-device probe** and future owned-copy adapter; it does not make a camera patch safe or permit writing to firmware.

Remaining requirements are **actual physical still-capture callback and buffer lifetime**, source/stride/color range/chroma order on device, safe owned-copy timing and reuse limits, Samsung-native JPEG/EXIF/RAW, OEM firmware provenance and full-brick recovery.

**Install / flash: NO-GO. Film Simulator is NOT integrated with an actual NX300M yet.**
