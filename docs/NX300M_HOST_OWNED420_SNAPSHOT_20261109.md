# NX300M Film Simulator — independent Y/C420 snapshot boundary

**2026-11-09. Host-only C implementation. Camera firmware: NO-GO.**

Before this change, the host JPEG adapter accepted caller-declared "copied"
Y/C planes and tables. During JPEG output it could continue reading those
external allocations even if the caller subsequently changed them.

The new `nx_host_owned420_snapshot_take` copies the minimum accessed spans of
Y, interleaved chroma, LUT, 256-entry sRGB decoder and 4096-entry encoder.
It validates dimensions, even 4:2:0 geometry, strides, supported hypothesis,
LUT count, source span separation, decode entry range, source bounds and the
**128 MiB aggregate host-copy budget** before output is created.

The existing host streaming JPEG adapter now performs:

```text
caller-provided HOST buffers (not camera DMA)
        |
        v
strict bounds / alias / budget preflight
        |
        v
own Y + chroma + LUT + transfer tables
        |
        v
no-libc RGB888 row transform
        |
        v
host-only transactional JPEG 4:2:0 + optional original APP1
```

The snapshot uses copies of only the bytes read by the renderer, including
row-stride gaps. It does not make a full-frame RGB buffer. The host JPEG
adapter holds the snapshot until row streaming completes, then frees it on
both success and failure. Invalid input does not create an output JPEG.

A source pointer can still be dishonest, unmapped, short-lived, or concurrently
written during the *initial copy*. This is not a camera buffer acquisition
primitive, a runtime ownership proof, a cache flush, DMA synchronization,
or a firmware callback. No device filesystem or vendor API is used.

**Next real hardware gates:** authorized camera FW identity, recovery proof,
actual capture pool extents, buffer ownership and sync evidence, Y/C packing,
camera JPEG/Exif ownership, native ABI and hardware-regression tests.
