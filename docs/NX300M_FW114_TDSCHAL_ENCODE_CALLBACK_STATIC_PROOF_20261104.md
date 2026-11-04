# NX300M FW1.14 — JPEG HAL callback provenance proved in native ARM32 (2026-11-04)

**Milestone: Full static `tDscHal +8` → `DscJfifHal::Encode` pointer identity is proven for the inspected FW1.14 mirror binary. No new host JPEG engine or film LUT was implemented.**

## Evidence type and source

Only actual ARM32 machine instructions and same-version ELF dynamic relocation entries, obtained from independently extracted private FW1.14 / FW1.15 archives in GitHub Actions. Archive firmware model and SLP/JAMCRC regions were checked as a precondition; source remains a **third-party unauthenticated mirror**, not a Samsung-certified factory image. No camera or firmware patch was executed. No private binary was committed or uploaded.

## Exact chain, offline static only

```text
libsif.so FW1.14  DscImage::DscJpegInstance() 0x00053f80
  ARM PIC:
    LDR r4, [pc] at 0x53f8c -> literal word 0x00018538 at 0x54044
    ADD r4, pc, r4 at 0x53f90 -> GOT PIC base 0x0006c4d0
  four callback table slots stored into local stack:
    tDscHal[+0]  < GOT 0x0006ce3c Parse       (0x00029084)
    tDscHal[+4]  < GOT 0x0006ce78 Decode      (0x00029544)
    tDscHal[+8]  < GOT 0x0006ce98 Encode      (0x00029830)
    tDscHal[+12] < GOT 0x0006ce9c CompressRaw (0x0002a464)

  Exact Encode callback:
    LDR r3, [pc,#0x6c] @ 0x53fe0 -> literal index 0x000009c8 @ 0x54054
    LDR r3, [r4,r3]   @ 0x53fe4 -> GOT [0x6c4d0 + 0x9c8] = 0x6ce98
      ELF R_ARM_GLOB_DAT target _ZN10DscJfifHal6Encode... = 0x29830
    STR r3, [fp,#-20] @ 0x53fe8 -> local table tDscHal +8
    SUB r3, fp, #28  @ 0x54004 -> fourth argument is table start
    ARM BL→PLT DscJPEG::Instance @ 0x54014
                 |
                 v
    DscJPEG::Instance @ 0x2aaf4
    ARM BL→PLT constructor @ 0x2ab5c
                 |
                 v
    DscJPEG::DscJPEG(...,tDscHal*) @ 0x2a708
    ARM BL→PLT DscJfif::HalRegister @ 0x2a77c
                 |
                 v
    DscJfif::HalRegister @ 0x28828
    LDR tDscHal[+8]      @ 0x2886c
    STR DscJfif[+12]     @ 0x28874
                 |
                 v
    DscJPEG::TaskMain @ 0x2ab9c
    ARM BL→PLT JpegEncode @ 0x2ad5c
                 |
                 v
    DscJfif::JpegEncode @ 0x28a88
    LDR callback from this[+12] into r6 @ 0x28b1c
    BLX r6                       @ 0x28c18
                 |
             STATIC CALLBACK IDENTITY:
        DscJfifHal::Encode @ 0x29830
```

This chain is a **combined native static evidence graph**. Each edge is independently derived from same-version ARM words and ELF relocations. The task-dispatch edge is verified from a direct `BL→PLT` import. The HAL pointer identity is verified from actual PIC GOT indexing and native function relocation. **The graph does not prove the camera executes this path on a live shutter event**, or prove that no other code modifies the callback during runtime.

## CI assertions and negative tests

- `research/nx300m_fw114_hal_table_plus8_audit.py` reads only bounds-checked version-local `libsif.so` ELF32. It enumerates exact constructor/Instance calls and uses ARM PIC `LDR/ADD` to resolve the local 4-slot `tDscHal` table.
- Four `R_ARM_GLOB_DAT` targets must exactly match **Parse, Decode, Encode, CompressRaw** at the corresponding GOT slots. The Encode callback must use `tDscHal +8` and resolve to `0x29830`.
- `DscImage::DscJpegInstance` must pass its local table as the fourth argument to `DscJPEG::Instance` from `0x54014`.
- `research/test_nx300m_fw114_hal_table_plus8_audit.py` uses synthetic ARM PIC instructions and deliberately corrupts the GOT relocation, the +8 symbol and the pointer setup. The gate fails closed.
- `.github/workflows/nx300m-fw114-native-elf-diff.yml` re-extracts both firmware versions privately, verifies the same-version evidence, and reports exact four-slot provenance without exporting firmware bytes.

## Remaining hard blockers

1. **Live capture path**: confirm the actual firmware invokes this static route at the still shutter point and captures a safe owned Y/C buffer; determine DMA/cache ownership, stride, color matrix/range, chroma order, buffer lifetime and RAW coexistence.
2. **Camera integration**: identify a reversible runtime integration method for independent Film Simulator processing and Picture Wizard replacement, not a simple Picture Wizard color adjustment.
3. **Native JPEG/EXIF preservation**: confirm finished JPEG full 20.6MP, original EXIF/MakerNotes and native encoder ABI on actual hardware.
4. **Provenance and recovery**: authenticate original Samsung FW1.14 and establish verified full-brick recovery/calibration backup before any firmware modification.

**INSTALL/FLASH: NO-GO. Real camera integration is not complete.**
