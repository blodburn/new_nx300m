# NX300M FW1.14 — independent RGB-row to host JPEG acceptance

**STATUS: host synthetic proof ONLY — not an on-camera Film Simulator build. Firmware modification / flash is NO-GO.**

## Processing schematic

```text
INDEPENDENT HOST COPIES of Y plane + interleaved 4:2:0 C plane
                 |
                 v
[Freestanding ARMv7 arithmetic DSO; 0 GLIBC imports]
 BT.601 full-range CbCr or CrCb HYPOTHESIS
 -> sRGB decoding -> RGB12 LUT 2/18/65 -> sRGB encoding
                 |
            1 x width x 3 B
                 |
                 v
[HOST ONLY: dlopen() + JPEG 4:2:0 writer + EXIF APP1 passthrough]
 row 0 -> row 1 -> ... -> final partial 16-row JPEG MCU
                 |
                 v
     create-only transactional synthetic.jpg
                 |
                 X
    NO Samsung NX300M camera decoder / ISP / JPEG / EXIF ABI
```

## New host API

`research/nx300m_host_freestanding420_jpeg.h`

`nx_host_freestanding420_jpeg_copy(module_path, copied_input, original_bypass, new_jpeg_path, original_exif_app1, exif_bytes)`

- The host wrapper links only to the test-host libc/POSIX environment; it is **NOT included** in the freestanding DSO and is not built as a Samsung Tizen plugin.
- Loads the tested freestanding module on the host, resolves only `nx_film_core_render_owned420_rows_hypothesis`, owns one packed RGB row buffer, then streams every row to the existing host JPEG 4:2:0 sink.
- The caller must provide independent host-owned planes, LUT nodes, gamma tables and explicit hypothetical color ordering. The copied job's original RGB fields are unused; the wrapper does not modify caller metadata.
- Validates the full input before starting a JPEG transaction. Failures abort the transaction and remove temporary staging files.
- `Original` returns `1` without loading the module, changing a pixel or writing a file.
- A new output returns `0` only after create-only commit; invalid inputs, invalid EXIF and existing destination return `-1`. Existing JPEGs are never overwritten.
- EXIF APP1 is preserved byte-for-byte only if supplied. EXIF/MakerNotes are not generated or reconstructed by the wrapper. The source of an APP1 payload must be explicitly authorized and verified.

## Tests

Run `make freestanding-test` or `make test`. New independent host regression covers:

1. Synthetic 34×22 off-MCU-boundary geometry with Y and chroma row padding and both packed CbCr/CrCb hypotheses.
2. LUT grids 2, 18 and 65; **byte-identical** JPEG output compared with the pre-existing host Y/C420 LUT -> JPEG oracle (six cases).
3. EXIF APP1 passthrough (LUT65) and no EXIF case (LUT2/18).
4. Immutable copied Y/C and LUT, no overwrite of the destination, missing DSO, bad metadata and forged EXIF fail-closed.
5. The prior ARMv7/QEMU ELF CI still checks three no-libc exported symbols and zero linked GLIBC dependencies for the arithmetic DSO; the host JPEG wrapper is intentionally excluded.

## Explicit physical NO-GO

This test does not establish firmware authenticity beyond previously documented unofficial mirror checks, direct physical camera memory access, Y/C format, DMA ownership/cache synchronization, Samsung native JPEG ABI, MakerNotes preservation, RAW+JPEG behavior, Tizen loader compatibility, film menu integration, latency/RAM measurements or a tested full-brick restoration path.

**Do not install, flash, copy a DSO to NX300M, or claim a camera-encoded 20.6MP photograph based on this test.**
