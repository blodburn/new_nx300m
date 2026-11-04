# NX300M 1.14/1.15 REAL SIF JPEG/EXIF static call graph — 2026-11-04

**SOURCE:** two externally obtained, UNOFFICIAL firmware ZIP images. Each was checked for the NX300M model, internal SLP FW1.14/FW1.15, five JAMCRC regions and ephemeral UBI extraction. They are **not** Samsung-authenticated factory firmware. No proprietary binary was committed. No actual camera was accessed.

## New execution (not a host JPEG re-test)

`research/nx300m_fw114_sif_callgraph.py` now reads actual 32-bit ARM `libsif.so` function bodies from the FW1.14 and FW1.15 source ELFs. For each known JPEG/EXIF function it uses:

1. The version's own `readelf -Ws` symbol/start/size and ARM PT_LOAD file range.
2. Exact ARM-state direct `BL` word decoding within function boundaries.
3. Matching imported ARM `PLT` three-opcode stubs -> GOT -> `R_ARM_JUMP_SLOT` to resolve imported symbols. Local direct BL addresses are resolved only against exact defined native function starts. No imported symbol names are guessed from an unrelated ELF.
4. Per-version function bytes SHA-256 and symbolic call comparisons.
5. Strict explicit `NO CAMERA ABI` and `NO FLASH` flags. Indirect/vtable/BLX calls are **not** analyzed.

Actual CI static analysis passed on the two extracted firmware images (initial graph run 41824728242). In each row below, *the immediate BL candidate count includes calls to imported stubs, not proof of a camera shutter firing*.

| SIF symbol | FW1.14 address | FW1.15 address | FW1.14 BL candidates | Function bytes identical? | Bounded resolved symbolic calls equal? |
|---|---|---|---:|---|---|
| `DscImage::EncodeYCC` | `0x0005c358` | `0x0005c250` | 13 | **NO** | YES |
| `DscImage::SaveExifImage` | `0x0005b9b4` | `0x0005b8ac` | 19 | **NO** | YES |
| `DscImage::CopyExifInfo` | `0x00059900` | `0x000597f8` | 3 | **NO** | YES |
| `DscImage::GetExifImageInfo` | `0x00057320` | `0x00057218` | 4 | **NO** | YES |
| `DscJfif::JpegEncode` | `0x00028a88` | `0x00028a88` | 2 | **NO** | YES |
| `DscJfifHal::Encode` | `0x00029830` | `0x00029830` | 14 | **NO** | YES |
| `DscJfifHal::Parse` | `0x00029084` | `0x00029084` | 30 | **NO** | YES |

## Actual direct imports from FW1.14 SIF function bodies

```text
 libmm-photo.so: CMmDeviceDriver::EncodeYcc(CYcc&, unsigned)
                        |
        PLT import DscImage::EncodeYCC (SIF)
                        |
                libsif.so FW1.14
                0x0005c358
                        |
    direct BL: DscImage::DscJpegInstance()
    direct BL: DscUtils::AllocBuffer(...)
    direct BL: DscUtils::FreeBuffer(...)
                        |
              [dynamic dispatch?]
      NO direct static proof of reaching JpegEncode
                        |
      DscJfifHal::Encode 0x00029830
          |        |        |
       bma_open  jpeg_open  jpeg_init
                             |
                         jpeg_encoder
                             |
                       jpeg_deInit / jpeg_close

  EXIF separate function:
    DscImage::SaveExifImage 0x0005b9b4
      -> DscImage::DscJpegInstance()
      -> DscMemoryManager::GetAddress(...)
      -> DscJPEG::Notify(...)
```

The diagram groups **observed function/import witnesses**, not a proven continuous runtime invocation chain. Crucially, the static `DscImage::EncodeYCC` BL list does **not establish** a direct edge to `DscJfifHal::Encode`; the actual runtime call may use an object, indirect branch or virtual dispatch. A single stable callback slot or safe modifiable buffer is **NOT identified**.

This is the reason earlier host-only LUT/JPEG work must not be mistaken for an actual camera integration. The old 1.15 MFW `libsif.so` code bodies cannot be copied into 1.14.

## CI / code

- `research/nx300m_fw114_sif_callgraph.py`: version-specific read-only ARM BL/PLT/GOT graph.
- `research/test_nx300m_fw114_sif_callgraph.py`: six synthetic ARM instruction/PLT/absent-relocation tests; no proprietary code.
- `research/nx300m_fw114_native_elf_diff.py`: integrates graph into the actual ephemeral FW1.14/1.15 ZIP→UBI→ELF pipeline.
- `.github/workflows/nx300m-fw114-native-elf-diff.yml`: checks 7 separate symbols and version-local source; additionally requires the actual 1.14/1.15 direct-PLT imports of `bma_open`, `jpeg_open`, `jpeg_init`, `jpeg_encoder`, `jpeg_deInit`, and `jpeg_close`. Requires SIF `DscJpegInstance` and EXIF memory-address imports. It never produces a flashable binary.
- `Makefile`: host-only disassembly regression runs as part of `make test`.

## Next **uncompleted** requirements

1. Confirm actual 1.14 native **indirect function/virtual dispatch** from `DscImage::EncodeYCC` into a JPEG handler, including argument and buffer ownership. Static ARM BL evidence alone cannot do so.
2. Prove that the real still-camera callback forwards **copy-owned** Y/C instead of DMA/live ISP pointers, preserves RAW, and reaches an acceptable native JPEG file save path with unchanged EXIF/MakerNotes.
3. Authenticate true original Samsung 1.14 firmware, ensure calibration backups and full-brick recovery, then benchmark real free memory/thermal latency.

**NO firmware flashing, no camera-side binary patch, no on-camera LUT injection performed.**
