# NX300M Film Simulator — host-only non-destructive RGB copy integration

**Status:** OFFLINE RGB888 code only. NX300M firmware 1.14 ABI, physical dial, Picture Wizard IPC, on-camera capture and full-brick recovery are unverified. Do not flash or patch anything.

## Purpose

The earlier `nx_capture_apply_saved_look()` host-only legacy research API performs an in-place RGB transformation, and its signature has no explicit source/destination byte lengths. It therefore cannot assert non-overlap, independent ownership or a complete input buffer. The new `nx_host_capture_apply_copy()` offers a stricter **separate-buffers-only** host path and integrates the existing fail-closed Picture Wizard routing guard.

## Data flow

```text
Saved Film Simulator configuration
             |
   Host-only route guard
             |
  +----------+------------------------------+
  |                                         |
Original/unknown config                  Experimental look
  |                                         |
PASS THROUGH; no output writes      Host-only copied RGB888?
                                            |
                                 NO / Camera / RAW-only
                                            |
                                          REFUSE
                                            |
                                   YES (validated RGB)
                                            |
                                 Check lengths/stride
                                 Check memory overlap
                                 Cap allocation 128MiB
                                            |
                                 Allocate private scratch
                                 Copy input -> scratch
                                 Apply complete image look
                                            |
                                 PASS? -> publish full
                                 stride*height to separate
                                 caller output buffer
```

## Invariants

- The source buffer is **never written**. The destination is **not modified** on an Original bypass, missing or corrupt configuration, any route refusal, bad input, insufficient spans, partial overlap, allocation failure, or image-filter failure.
- Experimental looks are only permitted on explicitly validated **host-copied RGB888** data for JPEG-only or RAW+JPEG simulations. This code does NOT write JPEG, RAW, native Samsung `CYcc`, MakerNotes, or Picture Wizard parameters.
- Original ID `0` **never maps** to a Samsung native Picture Wizard ID. It preserves the currently active Samsung configuration without attempting to read or change that state.
- The returned applied result means a host-owned RGB888 output buffer is available, **not** that the physical NX300M has created or saved a JPEG file.
- Caller gives both `src_bytes` and `dst_bytes`; `stride*height` must fit safely, remain under a 128MiB scratch threshold, and not overlap either buffer. Padding bytes are copied without reinterpretation.
- The existing in-place API is left intact for backward-compatible research tests. **Do not call it with physical camera buffers.** Prefer the copy adapter for new offline integration tests.

## Test and usage

```sh
make test
```

`research/test_nx300m_host_capture_copy_adapter.c` runs all **13 look IDs**, tests original passthrough, experimental output and preserved RGB source and padding, missing/corrupt settings, a camera-source refusal, RAW-only refusal, invalid dimensions, lengths and strides, oversized allocations, and partial/exact buffer overlaps. The suite is compiled with GCC warning-as-errors plus ASAN/UBSAN.

## Required for real NX300M 1.14 integration

1. Acquire and authenticate the 1.14 firmware, matching sysroot, original Picture Wizard IPC and tested full-brick recovery.
2. Demonstrate the acquisition and ownership of a separately copied, already-decoded RGB888 image. Do not treat this host buffer as a Samsung DMA Y/C buffer.
3. Validate native JPEG/Exif output, RAW preservation and one-file-per-shutter behavior with a reversible bench experiment; keep live camera experimental routes disabled until all proofs exist.
