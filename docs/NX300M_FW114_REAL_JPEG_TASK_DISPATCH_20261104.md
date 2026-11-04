# Samsung NX300M FW1.14 — real JPEG task dispatch investigation (2026-11-04)

**Read-only ARM static evidence from version-checked, UNOFFICIAL firmware mirror only. Camera install remains NO-GO.**

This is a new forensic result, **not** a repeat of host JPEG/LUT tests. The analysis reads the real extracted `libsif.so` of independently SLP-header/JAMCRC-verified mirror FW1.14 and FW1.15 inside ephemeral CI. No proprietary ELF is uploaded, loaded or modified. Source is not manufacturer-authenticated.

## Actual native callsites (FW1.14)

```text
  libmm-photo.so CMmDeviceDriver::EncodeYcc
                     |
       ARM BL -> PLT -> R_ARM_JUMP_SLOT
                     v
  libsif.so DscImage::EncodeYCC @ 0x0005c358
               |  two indirect BLX r3
               |   0x0005c550, 0x0005c628
               v
     [runtime dispatch NOT established]
               : 
               :
   libsif.so DscJPEG::TaskMain @ 0x0002ab9c
      | BL 0x2acbc -> PLT JpegParse
      | BL 0x2ad04 -> PLT JpegDecode
      + BL 0x2ad5c -> PLT JpegEncode
                           |
                           v
      DscJfif::JpegEncode @ 0x00028a88
                           |
         LDR r6,[r3,#0x0c] @ 0x00028b1c
         BLX r6            @ 0x00028c18
                           |
                [r6 target NOT VERIFIED]
                           :
        SIF R_ARM_GLOB_DAT @ 0x0006ce98
        DscJfifHal::Encode @ 0x00029830
           | jpeg_open / jpeg_init / jpeg_encoder / jpeg_deInit / jpeg_close
           v
        [native JPEG codec imported]
```

**Important:** Dotted lines are *unproven runtime transitions*. The callsite `TaskMain -> JpegEncode` is verified by ARM direct BL -> exact PLT -> GOT/JUMP_SLOT relocation symbol. A separate `GLOB_DAT` points to `DscJfifHal::Encode`. These two static facts **do not prove** that `BLX r6` invokes that HAL function or that `EncodeYCC` always reaches TaskMain.

### Exact new static FW1.14 witnesses

| Object | Symbol/address | Machine-code or ELF evidence |
|---|---|---|
| Encoder frontend | `DscImage::EncodeYCC 0x0005c358` | Indirect `BLX r3` at `0x0005c550`, `0x0005c628` |
| JPEG task | `DscJPEG::TaskMain 0x0002ab9c` | 16 indirect `BLX` candidates; additionally 72 direct BL candidates |
| Task dispatch | `0x0002ad5c` | Verified direct BL -> PLT import `DscJfif::JpegEncode(sJpegOp&,bool)` |
| JPEG function | `DscJfif::JpegEncode 0x00028a88` | `LDR r6,[r3,#12]` at `0x00028b1c`; `BLX r6` at `0x00028c18` |
| HAL function import | `GOT 0x0006ce98` | `R_ARM_GLOB_DAT DscJfifHal::Encode` → symbol `0x00029830` |
| JPEG task entry | `0x0006c1e8` | `R_ARM_ABS32 DscJPEG::TaskMain` → `0x0002ab9c` |
| JPEG function PLT | `0x0006c934` | `R_ARM_JUMP_SLOT DscJfif::JpegEncode` → `0x00028a88` |

### Critical disproved hypothesis

The actual `DscJfif` vtable at `0x0006c1b8` is only 16 bytes:

- `+0`: zero offset-to-top value
- `+4`: `R_ARM_ABS32` typeinfo for DscJfif
- `+8`: `R_ARM_ABS32` destructor variant at `0x2870c`
- `+12`: `R_ARM_ABS32` destructor variant at `0x28780`

The vtable **does not** contain a direct JpegEncode pointer. The earlier hypothesis that `DscJfif` virtual table slot controls JPEG encoding is unsupported and eliminated. ELF REL vtable slots have zero stored values before loader relocation; reading these zero bytes as pointers would have been misleading.

### Version contrast

Actual FW1.14 and FW1.15 `libsif.so` differ in byte-level implementation. `DscImage::EncodeYCC` is `0x5c358` in 1.14 but `0x5c250` in 1.15. The task and JpegEncode native addresses `0x2ab9c` and `0x28a88` match in these two mirror builds, as do the specific TaskMain direct BL callsites checked in CI. **This cannot authorize wholesale FW1.15 address or code reuse.**

## Source files and verification

- `research/nx300m_fw114_sif_virtual_dispatch.py`: read-only ELF32 symbol, vtable, R_ARM_ABS32/GLOB_DAT/JUMP_SLOT, direct/indirect ARM callsite, register-source candidate scanner.
- `research/test_nx300m_fw114_sif_virtual_dispatch.py`: synthetic ARM instruction, bounded ELF metadata, ambiguities and relocation decoding tests (never uses private firmwares).
- `research/nx300m_fw114_native_elf_diff.py`: invokes the new analysis on **actual** extracted 1.14 and 1.15 SIF binaries, retains only metadata for reports.
- `.github/workflows/nx300m-fw114-native-elf-diff.yml`: real CI requires independently checked version-specific TaskMain `BL->PLT` targets (JpegParse/Decode/Encode), JpegEncode `LDR r6` candidate, actual HAL GOT relocation and still reports NO-GO.
- `Makefile`: synthetic regression included in existing test suite.

## Remaining blocking items

1. Prove the runtime target of `DscJfif::JpegEncode`'s `BLX r6`, ideally show that struct field `+0x0c` carries `DscJfifHal::Encode` with exact producer/writer control flow. **A matching GOT relocation in the same library does not prove this assignment.**
2. Prove that frontend `EncodeYCC` dispatches to TaskMain in the actual still-capture flow and identify exact Y0/Y1/C0/C1 buffer ownership and safe copy time.
3. Independently authenticate vendor-original NX300M FW1.14; verify current on-device ABI, real JPEG/EXIF/MakerNotes, RAW unaffected, memory/latency, full-brick recovery, calibration preservation.
4. Only then evaluate a separately reviewed **reversible** camera integration. No firmware patch or flash is currently produced.

**Status: offline native static call graph is more complete. On-camera Film Simulator is NOT implemented or validated.**
