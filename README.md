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

`make test` compiles and executes 14 independent sanitizer-tested C suites plus one GUI callback runtime C suite, five JPEG SOF parser tests, five Y/C probe CLI tests, six ARM ELF ABI audit tests, and an EFL syntax-only check. `make bench` exercises full-resolution **synthetic** images, which are not representative of camera hardware performance.

JPEG test encoder verification includes **odd 33×25 dimensions**, end-to-end decode of the 4:2:0 sample, independent SOF sampling readback, unchanged RAW bytes, original-preset bypass, EXIF APP1 byte-copy, and refusal to overwrite existing images. Both JPEG modes use row scratch, not a full RGB8 image buffer. For an offline 20 MP JPEG 4:2:0 benchmark, compile the host JPEG benchmark or run `.build/bench_jpeg 420` after `make bench`.

**Important:** Producing a standard 4:2:0 JPEG bitstream does *not* establish compatibility with Samsung's proprietary 4:2:0 capture-memory format, DMA ownership, original JPEG encoder, or EXIF/MakerNotes. There is no on-camera integration yet.

## Picture Wizard symbols found in an offline capture library

An offline, read-only ELF metadata scan of a *partial research extraction* found four Picture Wizard-related dynamic symbol names in `libcapture-fw-slpcam-nx300.so`, including `CProcessParameter::GetPictureWizardMode()` and `GetPictureWizardParameter(...)`. It also found `convertUserData_DIALMODE(...)`, which is **not evidence of a hardware dial EFL callback**. Nine capture libraries were inspected, with 13 dependency references resolving within the small research sample and 84 missing from the sample. These counts do not imply missing libraries in full firmware. **Firmware 1.14 identity, physical device behavior, and safe UI/ISP calls are unverified.** See [the evidence and next verification gates](docs/NX300M_PICTURE_WIZARD_SYMBOL_EVIDENCE.md).

`research/nx300m_capture_elf_surface_audit.py` scans only ELF dynamic metadata with `readelf` and `c++filt`. Seven fixture unit tests were added to `make test` (**15 C regression executables and 23 Python tests**); no proprietary ELF or firmware is distributed.

## 1.14 Picture Wizard function-body comparison gate

An unofficial [Samsung NX300M firmware archive](https://nxfiles.nx.tc/files/NX300M/Firmware/) lists `NX300M_FW_v1.14.zip`, but the current development environment **could not download it without network approval**. No authenticated 1.14 firmware image or extracted 1.14 ELF has been inspected. The older research ARM ELF yielded four Picture Wizard function body lengths (96, 172, 1036, 924 bytes) and independent cryptographic fingerprints. New `research/nx300m_picture_wizard_abi_gate.py` compares read-only ELF-mapped function bodies and refuses to infer compatibility solely from matching symbols. Seven synthetic fixture tests detect modified/missing functions. **Neither identical function bytes nor these historical offsets authorize firmware 1.14 patching.** See [1.14 ABI comparison evidence](docs/NX300M_PW_114_ABI_COMPARISON.md).

## Fail-closed Picture Wizard 12-versus-13 routing guard

The older Ghidra research shows **12 original Samsung Picture Wizard dispatches**; Film Simulator uses **13 fixed looks** and its own unrelated IDs. The new host-only `research/nx300m_picture_wizard_route_guard.[ch]` never sends experimental IDs to native Samsung functions or changes raw buffers, camera Y/C, or the original native Picture Wizard mode. Samsung Original passes through unchanged. Experimental looks can be planned **only** for an explicitly validated independent **host-owned RGB888** frame in JPEG or RAW+JPEG simulations; all direct experimental camera routes and RAW-only modifications are rejected. `research/test_nx300m_picture_wizard_route_guard.c` verifies **156 state combinations**, malformed IDs, legacy Leica ID aliases, and the unchanged RAW buffer. See [safe native/Film Simulator separation](docs/NX300M_NATIVE_MODE_ROUTE_SAFETY.md). This is a routing policy, **not** a real 1.14 native firmware integration.

## Host-only non-destructive RGB copy integration

`research/nx300m_host_capture_copy_adapter.[ch]` connects saved Film Simulator settings with the **fail-closed Picture Wizard route guard** and the host RGB filter. Unlike the older in-place research API, it validates explicit source/destination byte lengths, stride and partial overlaps, caps scratch allocation at **128 MiB**, and processes the image in a private copy. A caller-owned destination is changed **only after successful full-frame processing**. Original mode, missing/corrupt configuration, RAW-only processing, unverified RGB input and any experimental camera-source request never modify it. Source and RAW bytes remain unchanged. This is an offline RGB output, **not** a real camera JPEG/ISP hook. The new C sanitizer suite checks all 13 looks, size/overlap errors, unchanged padding and output failure paths. See [host RGB copy integration](docs/NX300M_HOST_COPY_INTEGRATION.md).

## Verified SLP internal version and offline ZIP/BIN integrity

The existing private reference is named `nx300m_mfw_1.1.bin`, but its **internal Samsung SLP firmware version is 1.15**, not 1.1. MFW 1.1 is the modified-release label, not the underlying Samsung native version. All **five image JAMCRC checks plus the pcache JAMCRC** passed on its 333,237,352-byte binary. This does not prove the modified image is original Samsung firmware, and it is NOT a 1.14 comparison.

New read-only `research/nx300m_slp_firmware_integrity.py` reads an existing local BIN or ZIP (without extraction), rejects wrong camera models/versions and damaged/traversal archives, streams all six JAMCRC checks and SHA-256, and never modifies camera firmware. Nine synthetic tests verify corruption, bad metadata and ZIP handling; the full test suite has **17 C programs and 39 Python tests**. See [firmware SLP integrity evidence and version correction](docs/NX300M_SLP_PACKAGE_INTEGRITY.md). The original **1.14** binary remains unavailable for actual ABI comparison.

## Important limitations

The source-backed analysis used **MFW 1.1 (a modified release based on embedded Samsung NX300M 1.15)**; compatibility with an actual device running **firmware 1.14 is unverified**. There is no validated ARM firmware hook, no native camera SRAM/DMA adapter, no supported full-brick recovery, and no verified preservation of Samsung EXIF/MakerNotes on physical camera output. The Y/C byte layout, colorspace and stride need to be measured on an actual camera before any hardware bridge could be built.

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

## Tizen Film Simulator — standalone rotary UI

The new [Tizen EFL Film Simulator UI](docs/NX300M_TIZEN_FILM_MENU.md) provides a research-only right-side preset list and **rotate → preview → confirm/cancel** workflow across all 13 fixed looks. On-screen previous/next buttons and intensity controls are absent.

The host-tested controller saves only after confirmation to an explicit caller-provided path; cancel and failed persistence retain the previously selected look. The GUI source is syntax-checked against a **host stub**, not a verified NX300M 1.14 ARM/EFL sysroot. Hardware dial event names, Picture Wizard integration, image-processing hooks and flash safety remain unverified.

`make efl-check` performs host-only C syntax checking. `make tizen-efl` **refuses** to build without explicit compatible `TIZEN_CC`, `TIZEN_SYSROOT` and `TIZEN_PKG_CONFIG_LIBDIR`. No installable camera firmware or tested ARM executable is provided.

## Explicit physical-key evidence gate

Input actions are **disabled by default**. An explicit four-key mapping is required for clockwise, counterclockwise, confirm and cancel; otherwise all unrecognized EFL key events are ignored. Desktop-only mapping requires the separate `NX_FILM_DEMO_KEYS=1` opt-in. The bounded `NX_FILM_LOG_KEYS=1` diagnostic prints at most 32 printable event keynames in an already-authorized EFL session. These are observations, not evidence of any installed NX300M 1.14 dial mapping. See [Film UI documentation](docs/NX300M_TIZEN_FILM_MENU.md).

A guarded offline ARM cross-build script at `scripts/build_tizen_efl.sh` refuses to run without a verified original matching toolchain and sysroot; it also checks the emitted ELF class/machine/EABI before accepting any output. No device firmware is changed.

## EFL user-interface callback integration regression

New `make efl-runtime-test` builds and runs the **actual standalone EFL UI translation unit** with a host-only fake Elementary/Evas event loop. It validates **six complete GUI scenarios**, including disabled key mapping by default, opt-in keyboard demonstrations, explicit custom bindings, a refused incomplete keymap, missing settings path, atomic confirmation, cancel rollback, sidebar state and a bounded keyname log. `make test` includes it, with 15 total C regression executables and 16 Python tests. This is **not** the real NX300M firmware 1.14 UI runtime, physical camera dial, or an on-camera JPEG processing test.

Firmware source verification is tracked in [1.14 original image provenance](docs/NX300M_FIRMWARE_114_PROVENANCE.md). A historical third-party listing does **not** establish authenticity or a safe flashing/recovery path.
