# NX300M FW1.14 / FW1.15: CYcc getters and one constructor

Verification date: 2026-11-12. Source: privately extracted
third-party mirrored libmm-type.so, unauthenticated firmware archive.
Read-only offline ARM32 analysis; NO live camera hook.

## Confirmed Getter ARM32 field reads

Both extracted FW1.14 and FW1.15 methods have 40-byte identical
10-word ARM bodies, with no BL or indirect branch.

| Method | Entry | Exact field-read ARM instruction | Object field |
| --- | --- | --- | --- |
| CYcc::GetScanMode() | 0x000031b0 | 0x000031c4: LDR r3,[r3,#28] | +28 (0x1c) |
| CYcc::GetType() | 0x000031d8 | 0x000031ec: LDR r3,[r3,#32] | +32 (0x20) |

Both read the incoming 'this' receiver (r0) from their own stack
frame, load the field via r3, and copy r3 back to return register r0.
The entire 10-word body is pinned; changes cause hard CI failure.
The read location is a struct/object offset. It is NOT an identified
image plane or an NV12/NV21 byte order.

## Confirmed single-overload constructor writes

The extracted native method
CYcc::CYcc(sImgSize, unsigned long) at 0x000020b8, size 544 bytes,
contains the following exact bounded ARM32 initializer witnesses:

  0x20cc: STR r0,[fp,-16]          ; save this
  0x2290: LDR r3,[fp,-16]          ; retrieve this
  0x2294: MOV r2,#1
  0x2298: STR r2,[r3,#28]          ; local scan_mode initializer = 1
  0x229c: LDR r3,[fp,-16]          ; retrieve this
  0x22a0: MOV r2,#0
  0x22a4: STR r2,[r3,#32]          ; local type initializer = 0

The independent CI verifies the exact instruction sites and byte
values in both FW1.14 and FW1.15 and asserts that the constructor
offsets equal the two getter offsets.

This is **one of several constructor overloads**. It does NOT prove
that every CYcc object on a physical camera was built by this
overload; that both initialized fields stay constant; that the
constructor initializer runs on all program paths; or that native
getter calls always refer to this specific object instance.

## Evidence chain

  EncodeYcc incoming CYcc& (r1) → local slot fp-100
    → four getter receiver r0 loads from fp-100
    → libmm-type.so CYcc::GetType() reads this+0x20
    → libmm-type.so CYcc::GetScanMode() reads this+0x1c
    → local Boolean checks → eImgYCCType / eImgYCCPackType
    → native DscImage::EncodeYCC

Source-backed local ARM32 instruction and imported-symbol evidence
supports each listed static step. It does NOT provide a full
all-path reaching-definitions proof or actual observed runtime data.

## Blocked physical camera gates

- Device-installed FW1.14 identity and firmware authenticity
- The meaning of ImageYCCType / scan-mode enum values, and chroma
  plane packing / width / stride
- Physical camera Y/C bytes and pointer provenance
- Buffer lifetime, DMA synchronization, cache coherency and isolation
- Authorized device setup, failure recovery, and shutter callback hook

Firmware flash or camera installation: NO-GO.
