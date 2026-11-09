# NX300M host shutter: acquire Y/C420 before RAW callback

Date: 2026-11-09. OFFLINE HOST implementation only. Device firmware NO-GO.

## Previous host save sequence

Committed film LUT18 -> RAW writer callback -> validate/copy Y/C420
-> film JPEG. A malformed Y/C descriptor or invalid transfer decode table
could fail after the RAW callback already saved data. In addition,
caller-owned Y/C could be reused by that RAW callback before film JPEG
had a chance to capture the frame.

## Updated sequence

1. Resolve exact committed Film Simulator ID (never a pending preview ID).
2. Build the fixed LUT18 from that ID.
3. Validate and deep-copy host Y, chroma, LUT, decode and encode tables.
4. If snapshot acquisition fails, return before any RAW output.
5. Invoke the user-selected opaque RAW writer (if requested).
6. Produce host JPEG from the independently owned earlier snapshot.
7. Release the snapshot on RAW error or after JPEG completion.

The host regression proves:
- RAW+JPEG with a deliberately short Y plane writes no RAW or JPEG.
- RAW+JPEG with an out-of-range decode entry writes no RAW or JPEG.
- RAW callback that overwrites its source Y/C does not alter JPEG bytes:
  a JPEG_ONLY baseline and a RAW+JPEG output are byte-identical.
- Original JPEG still bypasses the film engine; RAW_ONLY bypasses film.
- Unconfirmed wheel previews cannot change the committed shutter preset.
- 12 film looks still match their independently built LUT18 JPEG outputs.

This reduces avoidable partial RAW saves; it does NOT provide a complete
RAW+JPEG two-file transaction. A JPEG disk error, file collision or codec
failure AFTER RAW success still leaves RAW saved, with raw_saved=1 and
jpeg_saved=0. The caller must detect partial success from result flags.

This new acquisition happens only on synthetic, stable, host-owned memory.
It does not provide actual Samsung capture pointer provenance, native
cache/DMA coherency, Y/C420 physical layout, firmware injection, on-camera
JPEG encoding, camera tests, or full-brick recovery. Device installation
remains NO-GO.
