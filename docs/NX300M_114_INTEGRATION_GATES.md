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

## Passive FW1.14 runtime metadata and ARM32 GNU toolchain smoke test (2026-11-03)

The new `scripts/nx300m_fw114_runtime_metadata_probe.sh` extends the
existing informational environment probe. It needs an **already available,
user-authorized device shell**, uses no root or privileged operation, and
never writes a file, touches firmware/DMA/camera APIs, or triggers a capture.
It emits ONLY whitelisted and sanitized metadata:

```text
NX300M_FW114_RUNTIME_METADATA_V1
kernel_machine=<armv7l / ... / unknown>
mem_total_kib=<integer / unknown>
mem_available_kib=<integer / unknown>
mem_free_kib=<integer / unknown>
camera_process=<observed / not_observed>
camera_maps_readable=<observed / not_observed>
camera_libmm_photo_loaded=<observed / not_observed>
camera_libsif_loaded=<observed / not_observed>
camera_libcapture_fw_loaded=<observed / not_observed>
firmware_114_independently_authenticated=no
live_capture_callback_verified=no
live_ycc420_layout_verified=no
native_buffer_ownership_verified=no
calibration_recovery_verified=no
firmware_flash_permitted=no
firmware_write_performed=no
```

**Observed process or loaded library is NOT proof a shutter callback was
invoked or a given version/native ABI actually drove a camera capture.**
No raw PIDs, process command-line arguments, serial numbers, MAC addresses,
memory addresses, user directories, device identifiers or capture pixels are
logged. The process name is matched to a coarse camera filter only.

On an **already authorized, manually established** shell:

```sh
sh scripts/nx300m_fw114_runtime_metadata_probe.sh
```

Copy the plain output text to an external host only if authorized. No
automatic upload is implemented. On the external host:

```sh
python3 research/nx300m_fw114_runtime_metadata_gate.py --report /private/probe.txt
```

The host gate rejects unexpected/duplicate output, inconsistent memory,
symlinks, false assertions of camera readiness and library claims without
observed process maps. It **never** upgrades a machine/process match to
camera-origin or live Y/C pixel-format proof.

An additional CI builds the host synthetic **Y/C420 → 65³ LUT → JPEG** test
as **ARM32 GNU EABI** and runs it under `qemu-arm`. This checks C source
portability and synthetic parity ONLY. A GNU/Linux glibc ARM emulator is **not
Samsung's Tizen runtime**; there is no camera, firmware install, ISP buffer,
Tizen loader integration, EXIF proof or physical memory measurement.

Action: `.github/workflows/nx300m-arm32-passive-probe.yml`.

Next physical gates: manual verified stock 1.14 and safe restore/recovery;
validated same-stage Y/C+RGB capture copies with proper consent; memory and
hot-path latency measurement **on camera**; RAW/JPEG behavior with EXIF and
MakerNotes. Until then, camera patch and flash remain NO-GO.

## ARM EABI / floating-point calling convention and loader review

Added `research/nx300m_fw114_arm_loader_abi.py` to examine the **actual
private FW1.14/1.15 extracted** camera native `libsif.so`,
`libmm-photo.so` and `libcapture-fw-slpcam-nx300.so` files.
The tool reads ARM ELF32 EABI header flags, `readelf -A` CPU and VFP
calling-convention attributes, `readelf -d` dependency SONAMEs and
`readelf -l` executable interpreter, then compares static metadata.

It independently measures the ARM32 GNU EABI QEMU test executable too.
A matching EABI version is **not** proof that a GNU/Linux binary uses the
camera's Tizen-era libc, dynamic loader, EFL, graphics, lens or native
camera API. A `PT_INTERP` in a GNU/Linux test binary is only its own
loader requirement. Camera plugin loadability is intentionally **false**
in all machine-readable records. No binary is flashed or copied to camera.

CI: `.github/workflows/nx300m-fw114-native-elf-diff.yml` compares actual
camera ELF records; `.github/workflows/nx300m-arm32-passive-probe.yml`
checks the separately GNU-cross-built ARM32 simulation binary.

**Remaining device gates:** authentically attested installed FW1.14,
read-only runtime loader/ABI evidence from an already authorized shell,
frame/plane ownership and chroma format, actual camera RAM and latency,
MakerNotes/RAW parity, and a tested full-brick recovery method.

## Measured actual FW1.14/1.15 ABI (isolated real-archive CI 41622267227)

These are properties of **actual mirror-downloaded and SLP-verified** NX300M
libraries, not observations from the user's physical camera. All data were
read from private ephemeral extracted UBIFS files.

| Native camera shared library | EABI | CPU tag | FP instruction tag | ELF float calling convention |
|---|---|---|---|---|
| `libcapture-fw-slpcam-nx300.so` | 5 | ARMv7 | VFPv2 | not declared by ELF flags or VFP-args attribute |
| `libmm-photo.so` | 5 | ARMv7 | VFPv2 | not declared by ELF flags or VFP-args attribute |
| `libsif.so` | 5 | ARMv7 | VFPv2 | not declared by ELF flags or VFP-args attribute |

For all three, `e_flags=0x05000002`, and the known static ABI attributes,
required SONAME names and ELF PT_INTERP metadata are identical between
mirror FW1.14 and FW1.15. These are shared libraries, so PT_INTERP was
absent. The exact procedure/camera-application loader and target ABI calling
convention must be independently verified before linking a new module.

**Original QEMU GNU test binary** (run 41622267537): ARM EABI5,
`Tag_CPU_arch=v5T`, no declared VFP arch, ELF soft-float flag
`e_flags=0x05000200`, program interpreter `/lib/ld-linux.so.3`,
GNU libc6 and libm6 dependencies. This is NOT a verified Samsung Tizen
target build.

The next QEMU regression explicitly adds
`-march=armv7-a -mfpu=vfpv2 -mfloat-abi=softfp` to build the same synthetic
film-to-JPEG algorithm for the **observed ISA**. This is a closer CPU/FP
instruction model, not proven Tizen loader compatibility. No manufacturer
authenticity or physical-camera runtime behavior is established.

## Actual FW1.14 C runtime / dynamic linker and GNU executable contrast

Tool: research/nx300m_fw114_runtime_linkage_audit.py.
It analyzes actual mirrored, internally SLP-verified FW1.14 and FW1.15
platform.img -> UBIFS contents **without executing target ELF files**.
From the private firmware filesystem, locate libc.so.6, libm.so.6,
libpthread.so.0, libstdc++.so.6, ld-linux.so.3 and/or
ld-linux-armhf.so.3. Follow only symlinks resolving *inside* extracted
root; record readelf metadata and SHA-256 without exporting binary files.
Inspect three source-proved camera libraries' NEEDED names and optional
di-camera-app PT_INTERP static property.

GLIBC versions *defined* by target libc are distinct from GLIBC versions
*required* by a GNU-built executable. The CI records both; an ARM EABI5
match does not guarantee a compatible loader or C runtime.

Static library file presence does NOT prove full dependency closure,
symbol-by-symbol linking or safe on-camera execution. No live camera,
firmware writes, RAM reads, proprietary binary uploads or full-brick
recovery were attempted. **Firmware installation remains NO-GO.**

## Actual source-backed GLIBC compatibility blocker (2026-11-03)

GitHub Actions **real extracted FW1.14/1.15 UBIFS** result:
https://github.com/blodburn/new_nx300m/actions/runs/41634023305

- Firmware 1.14 app di-camera-app: static interpreter /lib/ld-linux.so.3.
- Firmware 1.14 libc.so.6: maximum defined version tag **GLIBC_2.13**.
- Firmware 1.15 libc.so.6: maximum defined version tag **GLIBC_2.13**.
- The 1.14/1.15 libc, ld-linux.so.3, libm, libpthread and libstdc++
  source ELF copies were byte-identical in this offline comparison.
- ld-linux-armhf.so.3 was not found in the selected extracted runtime.
- The camera application's observed dependencies include
  libappcore-efl.so.1, libelementary.so.1, libevas.so.1, libmm-photo.so,
  libc.so.6, libstdc++.so.6 and many Samsung-specific libraries.

GitHub Actions **actual ARMv7 VFPv2 GNU test executable** result:
https://github.com/blodburn/new_nx300m/actions/runs/41634023171

- Executable dynamic linker path: /lib/ld-linux.so.3.
- Executable's maximum required version tag: **GLIBC_2.34**.
- Target CPU/FP tags ARMv7 and VFPv2 matched static firmware metadata.
- However, **GLIBC_2.34 is not available in the actual extracted
  stock-candidate 1.14 libc**, whose maximum is GLIBC_2.13.
- Therefore the existing GNU QEMU executable cannot be used as-is
  against the firmware libc. Matching the loader filename and ARM EABI5
  are insufficient. Compilation against a verified *older target libc
  and camera userland* is necessary before any physical experiment.
- No direct camera loading, correct Samsung native ABI, ISP buffer
  access, original MakerNotes, secure recovery or flash has been proven.

This evidence is from an **unofficial firmware mirror** with internal
SLP checksums but no independently authenticated Samsung signature.
