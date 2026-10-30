# NEW NX300M — Film Simulator research

Experimental image-processing source for investigating **Samsung NX300M** film-look processing. **This is not installable camera firmware** and must not be flashed onto a camera.

## Features

- **13 fixed look selections:** Samsung Original passthrough, 7 experimental Fujifilm-style and 5 Leica-style looks. Brand names describe visual research targets; no manufacturer endorsement or affiliation.
- High-bit-depth unpacked Bayer16 demosaicing, white-balance/exposure/highlight mapping before RGB8 conversion.
- Row-stream processing instead of a full-frame RGB16/RGB8 intermediate, with transactional `begin → write_row → commit / abort` sink.
- Host-only standalone baseline **JPEG 4:4:4 and 4:2:0** encoder for synthetic test images, **not** the NX300M's original JPEG codec.
- Host-only Y/C 4:2:0 staging model with explicit **experimental** CbCr / CrCb order. This does **not** establish the physical camera memory layout.
- Regression tests for RAW byte preservation, Samsung Original no-op, pixel equality, JPEG container validity and failure rollback.

## Host build

Requires: C11 GCC-compatible compiler, `make`, Python 3. No vendor SDK, firmware blobs or original camera libraries required.

```sh
make test
make bench
```

`make test` compiles and executes 12 independent sanitizer-tested C suites, five JPEG SOF parser tests, five Y/C probe CLI tests, and six ARM ELF ABI audit tests. `make bench` exercises full-resolution **synthetic** images, which are not representative of camera hardware performance.

JPEG test encoder verification includes **odd 33×25 dimensions**, end-to-end decode of the 4:2:0 sample, independent SOF sampling readback, unchanged RAW bytes, original-preset bypass, EXIF APP1 byte-copy, and refusal to overwrite existing images. Both JPEG modes use row scratch, not a full RGB8 image buffer. For an offline 20 MP JPEG 4:2:0 benchmark, compile the host JPEG benchmark or run `.build/bench_jpeg 420` after `make bench`.

**Important:** Producing a standard 4:2:0 JPEG bitstream does *not* establish compatibility with Samsung's proprietary 4:2:0 capture-memory format, DMA ownership, original JPEG encoder, or EXIF/MakerNotes. There is no on-camera integration yet.

## Important limitations

The source-backed analysis was performed using an NX300M **MFW 1.1 research firmware**; compatibility with an actual device running **firmware 1.14 is unverified**. There is no validated ARM firmware hook, no native camera SRAM/DMA adapter, no supported full-brick recovery, and no verified preservation of Samsung EXIF/MakerNotes on physical camera output. The Y/C byte layout, colorspace and stride need to be measured on an actual camera before any hardware bridge could be built.

The public source tree intentionally excludes firmware images, extracted proprietary shared libraries, original RAW photographs, private configuration, third-party binaries and generated image/binary artifacts.

## Layout

- `research/nx300m_bayer_prejpeg.[ch]` — experimental Bayer16-to-film pipeline
- `research/nx300m_linear_prejpeg.[ch]` — high-bit-depth exposure/WB/shoulder
- `research/nx300m_film_menu.[ch]` — saved fixed 13-look selector
- `research/nx300m_host_jpeg_sink.[ch]` — offline scanline-to-JPEG writer with atomic create-only publication
- `research/nx300m_host_native420_bridge.[ch]` — offline two-region Y/C type-1 geometry study
- `research/test_*.c` and `research/bench_*.c` — tests and synthetic benchmarks

## License status

This code is published for inspection. **No open-source license has been selected.** Public availability does not by itself grant permission to copy, modify or redistribute; a license can be chosen separately by the repository owner. Original brand names, proprietary firmware and vendor intellectual property remain their owners' property.

## NX300M 1.14 integration gate and read-only Y/C probe

See [native integration gates](docs/NX300M_114_INTEGRATION_GATES.md).

Build with `make probe` to inspect *previously copied* same-stage Y/C and RGB888 data:

```sh
./.build/ycc420_probe WIDTH HEIGHT Y_STRIDE C_STRIDE RGB_STRIDE copied_y.bin copied_c.bin matching_rgb888.bin
```

The probe only compares two full-range BT.601 interleaved chroma hypotheses. It does not know the camera's original Y/C layout and will return `INCONCLUSIVE` if the evidence is inadequate. A normal JPEG or SRW does not provide the same-stage Y/C memory dump. No camera firmware is modified or executed.

## NX300M Tizen Camera Platform

NX300M uses the Linux-based **Tizen Camera Platform** (DRIMeIV); userland ARM ELF software and Samsung's proprietary image-processing/ISP/JPEG pipeline are distinct. See [Tizen architecture and safe preflight](docs/NX300M_TIZEN_ARCHITECTURE.md).

The new read-only offline tools are `research/nx300m_tizen_elf_audit.py` for checking ARM EABI5 and whether two versions' individual ELF libraries are byte-identical, and `scripts/nx300m_tizen_readonly_probe.sh` for reporting generic OS/library presence **only from an already authorized device shell**. Neither tool modifies firmware or provides a way to bypass camera access.

Community NX300M modified firmware documents restoring `autoexec.sh` with **1.15** after update. Its safety or reversibility on a camera currently running **1.14** is not established. Do not flash or substitute ARM function offsets between firmware versions without verification.
