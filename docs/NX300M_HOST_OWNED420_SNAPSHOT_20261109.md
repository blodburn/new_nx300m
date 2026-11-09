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

## Two-stage acquisition and alias guard (2026-11-09)

The host-only API now offers a separate acquisition/render boundary:

```text
HOST source buffers (stable only during take)
          |
          v
nx_host_owned420_snapshot_take()  -> owned Y/C + LUT + transfer tables
          |
          |  caller may release/change source buffers
          v
nx_host_freestanding420_jpeg_from_snapshot()
          |
          v
Independent JPEG 4:2:0 (create-only)
          |
          v
nx_host_owned420_snapshot_release()
```

The snapshot rejects overlap between its destination descriptor, the input
job descriptor, and all five source spans **before touching the destination**.
It rejects a second take on a live snapshot rather than leaking the first
allocation. Snapshot readiness checks structural pointer and geometry
consistency. Input decode entries are validated **after copying**.

Host regression creates a JPEG from this detached snapshot after overwriting
all original Y/C and LUT source allocations. The new JPEG must match the
normal host result byte-for-byte. Failed/stale snapshot inputs must not create
a JPEG. This tests host lifetime separation, **not** DMA coherency, actual
NX300M buffer format, or camera firmware compatibility.

### Explicit limitations

The snapshot cannot authenticate source pointer ownership or detect a
concurrent write during the initial memory copy. There is no physical
camera or firmware-side acquisition code. Device flash remains **NO-GO**.
