# NX300M Independent Film Simulator — HOST 4:2:0 capture-boundary adapter

**Scope: static HOST proof only, not a camera integration.**

The Film Simulator must not be implemented as changes to Samsung Picture Wizard tuning registers. Picture Wizard, if reused, selects a look only. The independent engine must transform pixel values and write one actual JPEG for the selected look.

## New complete host-stage route

\`\`\`text
HOST COPY of hypothetical 4:2:0 Y and interleaved C planes
    |
    +-- validate dimensions, planes, strides, explicit CbCr or CrCb order
    |   (source is immutable; any ambiguity = refuse)
    |
    v
HOST full-range BT.601 YCbCr -> packed owned RGB888
    |
    v
nx_still_filter_enhanced_inplace(film_id, RGB888)
    |- Independent 18^3 profile LUT / tone
    |- Conservative RGB enhancement
    |- Fuji/Leica-study profile shoulder, chrome, clarity, grain
    |
    v
nx_host_jpeg_writer_sink (baseline JPEG, 4:2:0)
    |- create-only temporary file, ordered scanlines
    |- original APP1 Exif if explicitly provided and valid
    +- single atomic publication; rollback on any failure
    |
    v
One distinct film-processed JPEG file

Original preset -> bypass (no second JPEG)
RAW / input Y/C / Samsung DMA -> never mutated
\`\`\`

### Source

- \`research/nx300m_host_420_film_jpeg.h\`
- \`research/nx300m_host_420_film_jpeg.c\`
- \`research/test_nx300m_host_420_film_jpeg.c\`

The exported entry point \`nx_host420_film_to_jpeg\` is deliberately **host-only**. It takes pointer+byte-length+stride for each already-host-owned Y/C plane, validates dimensions and last accessible pixels, requires explicit chroma byte order, limits RGB staging to 64 MiB, and never interprets ARM camera addresses.

### Regression proof

The test generates 28 × 20 synthetic RGB values, converts them into two hypothetical Y/C 4:2:0 layouts using the existing host packer, and renders two different study looks through the independent pixel engine:

| Test | Expected |
|---|---|
| CbCr and CrCb (explicit ordering), same source/look | Same JPEG hash |
| Fuji Velvia Study ID 101 vs Leica Mono HC Study ID 204 | Different JPEG hashes |
| Before/after Y/C plane bytes | Exactly identical |
| Optional original Exif APP1 | Exact bytes present |
| Second write to existing destination | Reject, existing bytes unchanged |
| Truncated Y/C planes, wrong stride/order, odd width, unknown film ID | Reject |
| Samsung Original (ID 0) | Bypass; no duplicate JPEG |

Run \`make test\` for the complete sanitizer-enabled suite (19 C programs, 118 Python cases) or compile the host test through \`make test\`. No camera firmware is executed or flashed.

## Critical limits — not stock NX300M 1.14 support

The host 420 model assumes **two explicit planes**, an 8-bit full-range **BT.601** matrix, and either **CbCr** or **CrCb** interleaving. Those are **test assumptions, not proven native Samsung DRIMeIV CYcc type1 mode7 image-memory semantics**.

Do **not** pass a physical/virtual camera DMA address or install this C function into the firmware. Before camera integration, verify all of the following independently from authenticated original **1.14** files and a non-destructive capture:

- DMA buffer byte order, strides, exact chroma siting, image bounds and lifetime
- Sensor/ISP color matrix, transfer range and camera calibration
- Safe ownership of copied frame memory; no overwrite of native encoder or RAW buffers
- Actual native JPEG encoder ABI / EXIF MakerNotes integrity
- Complete unbrick/recovery route without calibration loss

**Status:** Independent per-pixel host processing and actual JPEG creation **PASS**; real NX300M 1.14 capture/ISP/encoder path **NOT VERIFIED**.
