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
- Ten synthetic tests validate normal origins, ambiguous multiple
  stores, missing writers, mutated known instructions and rejection
  of conditional/shifted register claims.

## Verified FW1.14 + FW1.15 direct writer sites

The native ELF runner independently reported **three direct stack writes
for each field** in both versions. Each direct write has an adjacent
unconditional ARM MOV immediate; this was observed in the real, extracted
FW1.14/1.15 byte stream and is now pinned in CI.

| Encoder argument | Direct STR at ARM PC | Immediately preceding MOV |
|---|---|---|
| eImgYCCType | 0x34be4 | MOV r3,#0 |
| eImgYCCType | 0x34c10 | MOV r3,#0 |
| eImgYCCType | 0x34c40 | MOV r3,#1 |
| eImgYCCPackType | 0x34c48 | MOV r3,#0 |
| eImgYCCPackType | 0x34c74 | MOV r3,#1 |
| eImgYCCPackType | 0x34ca4 | MOV r3,#0 |

These are **direct writer candidates**, NOT the single runtime-selected
value. The choice depends on branches and on the complete provenance
of the fields and pointers. A direct-write inventory does not exclude
indirect aliases, nor does numeric enum 0/1 identify the C plane's
physical packing without verifying enum definitions and live pixels.

## Verified direct zero-test branches

The FW1.14/1.15 native A32 encoder contains four source-backed local
test-and-skip sequences. Each sequence has adjacent instructions:
UXTB r3,r3 -> CMP r3,#0 -> BEQ immediate.
The taken BEQ target is calculated from the signed 24-bit ARM
relative branch operand, not guessed from the source label.

| Field | BEQ site | BEQ taken target | Direct store bypassed | Nearby store immediate |
|---|---|---|---|---|
| eImgYCCType | 0x34c08 | 0x34c18 | 0x34c10 | 0 |
| eImgYCCType | 0x34c38 | 0x34c44 | 0x34c40 | 1 |
| eImgYCCPackType | 0x34c6c | 0x34c7c | 0x34c74 | 1 |
| eImgYCCPackType | 0x34c9c | 0x34ca8 | 0x34ca4 | 0 |

The first direct writer of each field, 0x34be4 and 0x34c48,
does not have one of these *locally pinned* BEQ bypasses. It is not
correct to claim these writers are unconditional or that a given
encoder call always selects a particular 0/1 tuple.

The analysis confirms that **if** execution reaches each local BEQ
with the zero flag set by the adjacent comparison, the branch skips its
nearby direct writer. It does not prove the input origin of r3,
complete reaching definitions, preceding jumps into the block,
indirect stack alias writes, or the actual observed execution path.
UXTB extracts an 8-bit register value; it is not evidence of a
camera chroma-plane memory layout.

Native CI pins all four A32 sequences in both extracted versions.
It fails if the expected UXTB, CMP, BEQ, target, or adjacent
writer changes. Additional synthetic tests check modified branches,
wrong comparisons and signed immediate decoding.

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
