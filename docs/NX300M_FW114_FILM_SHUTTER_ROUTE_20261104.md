# NX300M FW1.14 — committed Film Simulator selection → host JPEG/RAW routing

**Offline host simulation only. NO camera installation, native API binding or flash.**

## Host-only control flow

```text
          Film Simulator menu controller
          committed_id    preview_id
               |              |
               |         shown on screen only
               |              X (not used for capture)
               v
         SHUTTER ROUTER (host test)
               |
        +------+---------------+
        |                      |
      RAW_ONLY              JPEG requested
        |                      |
  opaque RAW callback          v
  no image LUT          [committed ID]
                               |
               +---------------+--------------+
               |                              |
           Original                         Film
               |                              |
    external untouched JPEG          MATCH preset ID
    callback exactly once            to caller-owned LUT
               |                              |
        no host re-encode            independent copied Y/C
                                              |
                                 freestanding no-libc LUT
                                              |
                               one RGB row at a time
                                              |
                               host JPEG 4:2:0 writer
                                              |
                       create-only JPEG + optional caller APP1
```

In RAW+JPEG mode, the RAW callback completes first. A later JPEG failure returns `-1` with `raw_saved=1`; the RAW side effect is **not rolled back**. No extra JPEG files are produced.

## Concrete new code

- `research/nx300m_host_shutter420.[ch]`: coordinator that only reads `controller->committed_id`, not the preview index; honors JPEG_ONLY, RAW_ONLY and RAW_AND_JPEG. The selected preset is taken from the independent Film Simulator menu and is not a Picture Wizard strength setting.
- A Film request must provide a `lut_preset_id` that matches the committed selection. It is only an association check; it cannot authenticate source LUT coefficients, color measurements or emulate Fuji/Leica proprietary rendering.
- An Original request calls an external existing-original-JPEG callback and never loads the independent film module or re-encodes original pixels.
- A RAW_ONLY request does not require any controller, copied Y/C data, film LUT or JPEG module. RAW content is treated as opaque.
- Success flags are set only after callbacks return success. Wrong LUT ID and absent required callbacks are rejected **before** saving RAW. A rendering/JPEG failure after RAW commit is reported as partial completion, not silently hidden.

## Executable proof

`make freestanding-test` executes `research/test_nx300m_host_shutter420.c` in addition to prior LUT and JPEG parity tests.

- Unconfirmed menu preview must not affect the committed shutter selection.
- Original JPEG callback once per shutter press; no host re-encode.
- RAW_ONLY: opaque bytes unchanged and no JPEG activity.
- Film JPEG_ONLY: one create-only synthetic JPEG; no extra RAW file.
- Film RAW_AND_JPEG: one RAW callback then one JPEG; duplicates reject, previous JPEG preserved and partial result reported.
- Wrong preset/LUT association rejected before callbacks; malformed copied Y/C rejected without publishing a JPEG.
- Y/C plane bytes and LUT nodes are unchanged.

## Safety and device readiness

No on-camera capture callback, physical sensor/DMA buffer, native JPEG/EXIF/MakerNotes interface, Camera/Elementary dial event, Tizen loader, manufacturer-authenticated FW1.14 image, real RAW+JPEG parity, measured 20.6MP device memory/latency, calibration backup or full-brick recovery is established.

**Firmware installation, camera-side DSO loading, patching and flashing remain NO-GO.**
