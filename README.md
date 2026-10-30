# NEW NX300M — Film Simulator research

Experimental image-processing source for investigating **Samsung NX300M** film-look processing. **This is not installable camera firmware** and must not be flashed onto a camera.

## Features

- **13 fixed look selections:** Samsung Original passthrough, 7 experimental Fujifilm-style and 5 Leica-style looks. Brand names describe visual research targets; no manufacturer endorsement or affiliation.
- High-bit-depth unpacked Bayer16 demosaicing, white-balance/exposure/highlight mapping before RGB8 conversion.
- Row-stream processing instead of a full-frame RGB16/RGB8 intermediate, with transactional `begin → write_row → commit / abort` sink.
- Host-only standalone baseline **JPEG 4:4:4** encoder for synthetic test images, **not** the NX300M's original JPEG codec.
- Host-only Y/C 4:2:0 staging model with explicit **experimental** CbCr / CrCb order. This does **not** establish the physical camera memory layout.
- Regression tests for RAW byte preservation, Samsung Original no-op, pixel equality, JPEG container validity and failure rollback.

## Host build

Requires: C11 GCC-compatible compiler, `make`, Python 3. No vendor SDK, firmware blobs or original camera libraries required.

```sh
make test
make bench
```

`make test` compiles and executes 11 independent sanitizer-tested C suites and one read-only JPEG SOF parser suite. `make bench` exercises full-resolution **synthetic** images, which are not representative of camera hardware performance.

## Important limitations

The source-backed analysis was performed using an NX300M **MFW 1.1 research firmware**; compatibility with an actual device running **firmware 1.14 is unverified**. There is no validated ARM firmware hook, no native camera SRAM/DMA adapter, no supported full-brick recovery, and no verified preservation of Samsung EXIF/MakerNotes on physical camera output. The Y/C byte layout, colorspace and stride need to be measured on an actual camera before any hardware bridge could be built.

The public source tree intentionally excludes firmware images, extracted proprietary shared libraries, original RAW photographs, private configuration, third-party binaries and generated image/binary artifacts.

## Layout

- `research/nx300m_bayer_prejpeg.[ch]` — experimental Bayer16-to-film pipeline
- `research/nx300m_linear_prejpeg.[ch]` — high-bit-depth exposure/WB/shoulder
- `research/nx300m_film_menu.[ch]` — saved fixed 13-look selector
- `research/nx300m_host_jpeg_sink.[ch]` — offline scanline-to-JPEG writer with atomic create-only publication
- `[REDACTED].[ch]` — offline two-region Y/C type-1 geometry study
- `research/test_*.c` and `research/bench_*.c` — tests and synthetic benchmarks

## License status

This code is published for inspection. **No open-source license has been selected.** Public availability does not by itself grant permission to copy, modify or redistribute; a license can be chosen separately by the repository owner. Original brand names, proprietary firmware and vendor intellectual property remain their owners' property.
