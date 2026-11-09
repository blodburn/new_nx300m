# NX300M FW 1.14/1.15 JPEG Y/C type and packing arguments

Date: 2026-11-10. OFFLINE static ARM32 analysis. Physical camera: NO-GO.

## Observed connection

FW1.14/1.15 third-party mirrored libmm-photo.so includes
CMmDeviceDriver::EncodeYcc at 0x00034b18, with
DscImage::EncodeYCC invoked at 0x00034d78.

The existing exact-opcode audit confirms JPEG stack arguments:

  stack[sp+28] eImgYCCType     <- r3 loaded from [fp,-40] at 0x34d48
  stack[sp+32] eImgYCCPackType <- r3 loaded from [fp,-44] at 0x34d50

A bytewise pre-JPEG renderer must know more than a Y/C 4:2:0 image label:
the buffer packing and its lifetime matter, and the values of these two
per-frame fields were previously untraced.

## New audit

- research/nx300m_fw114_encoder_format_pack_origins.py checks the exact
  register/stack arguments against the original ABI validator.
- It scans the entire 644-byte ARM32 encoder body for direct, immediate
  STR instructions to [fp,-40] and [fp,-44] before the JPEG arguments.
- Every candidate includes exact PC, ARM opcode, source register,
  condition, prior six ARM words, and a conservative adjacent MOV
  candidate (if present). It does not silently select one possible
  writer when branches or repeated stores exist.
- Native FW1.14 and FW1.15 audit report store-candidate counts
  separately. The offline CI rejects missing/altered ABI instructions.
- Six synthetic tests validate normal origins, ambiguous multiple
  stores, missing writers, mutated known instructions and rejection
  of conditional/shifted register claims.

## Interpretation

A local stack writer is not proof of a runtime enum value.
The record can have indirect stack alias writers or nonlocal control
flow. A candidate MOV immediate does not prove the value on all
possible execution paths. Even a candidate numeric value would not
prove byte order, plane layout, stride or DMA/cache coherency.

This source does NOT include or execute Samsung native binaries.
The actual firmware data is processed only in an isolated,
temporary GitHub Actions runner; the source ZIPs are from an
unauthenticated third-party mirror and the analysis does not imply
manufacturer signature verification.

The code is a preparatory static evidence step. No camera was
accessed, no user files modified, no firmware installed, and no
flash/readiness gate is promoted by the report.

Device firmware installation: NO-GO.
