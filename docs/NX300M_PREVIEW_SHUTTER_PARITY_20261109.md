# NX300M Film Simulator: Preview / Shutter Pixel Parity

2026-11-09. OFFLINE HOST-ONLY IMPLEMENTATION. Physical camera: NO-GO.

The menu controller has two selections:

- UI open: use the active PREVIEW selection for a host RGB preview frame.
- UI closed: use the COMMITTED selection for host RGB preview.
- Shutter: always use COMMITTED, even if a new look is visible in the UI.

The new research/nx300m_host_preview420.c module:

1. Reads the menu controller's active selection.
2. Leaves Samsung Original unchanged, with no access to any film module.
3. Generates the same fixed 18x18x18 film LUT as the host shutter route.
4. Takes an independent copy of host Y/C420, LUT and transfer tables.
5. Runs the exact same no-libc Y/C420-to-RGB12-to-RGB888 kernel used
   before host JPEG 4:2:0 encoding.
6. Computes all pixels in private host memory, then publishes to an
   explicitly provided host RGB888 buffer. Invalid inputs do not modify it.
7. Preserves RGB row padding and limits private RGB stage to 64 MiB.

The host shutter test now checks all 12 non-Original looks: every
preview pixel matches the no-libc pre-JPEG renderer with the corresponding
fixed menu LUT. Separately, each JPEG byte stream is checked against an
independent fixed-LUT JPEG reference. The GUI can preview Film 101 while
shutter still saves committed Film 100. Cancel restores the committed preview.

This does not mean JPEG-decoded RGB is byte-identical to pre-JPEG RGB:
JPEG is lossy. This is a parity check of LUT selection and pre-encode
pixel transform, not a decoder-output equality claim.

No physical NX300M has been connected. Y/C memory layout, chroma order,
BT.601 conversion, cache coherency and DMA synchronization are host
hypotheses. No native Tizen live-view hook, capture callback, Samsung
JPEG entrypoint, firmware patch, flashing, or recovery verification
exists in this module. Device installation remains NO-GO.
