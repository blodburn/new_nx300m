# NX300M — Picture Wizard 12 native modes vs 13 Film Simulator looks

> **Firmware version correction (2026-10-31):** The private research file named `nx300m_mfw_1.1.bin` has an internal SLP header identifying the underlying Samsung firmware as **NX300M 1.15**. `MFW 1.1` denotes the modified firmware release, not Samsung-native firmware 1.1. This does not establish a match to target stock 1.14.


Status: **HOST-ONLY safety policy. No firmware is installed, executed or patched.**

## Source evidence

Older NX300M MFW 1.1 Ghidra checkpoint `nx300m/analysis/picture_wizard_native_trace.json` reports 12 native Picture Wizard dispatch entries, `user_param_id=16`, and a `mode OR 0x100` path observed in `GetPictureWizardParameter()`. This is *not* a verified firmware 1.14 ABI. It does not establish any 1.14 mode writing or UI event protocol.

The Film Simulator is a different namespace: **13 total fixed looks**: Samsung Original = 0; seven Fuji-style studies = 100–106; five Leica Q3-style studies = 200–204 (legacy aliases 300–304 normalize to 200–204). No FilmSim ID may be substituted directly into the Samsung Picture Wizard setter. A camera being Linux-based Tizen does not eliminate the private Samsung capture/ISP boundary.

## Pure routing decision

```text
Saved Film Simulator look ID
    |
    +-- invalid / unsupported -> REFUSE (no writes)
    |
    +-- Samsung Original ID 0 -> ORIGINAL UNCHANGED
    |                              preserve current vendor PW mode
    |                              preserve RAW/JPEG/EXIF path
    |                              never send FilmSim ID to Samsung
    |
    +-- experimental ID 100-106 / 200-204
           |
           +-- live NX300M camera? -> REFUSE
           +-- RAW-only request? -> REFUSE
           +-- RGB888 ownership/validation missing? -> REFUSE
           +-- host-copied, verified RGB888 and JPEG/RAW+JPEG?
                   -> HOST RGB EFFECT PLAN only
                      independent JPEG output required
                      RAW remains untouched
                      no Samsung/ISP/DMA/EXIF control writes
```

A caller must inspect the returned plan and separately supply the independently owned, validated host RGB buffer and an independent file publication step. **Planning does not perform image processing, capture, writing or firmware installation.** RAW+JPEG mode means only a separate host-owned JPEG copy may be processed; it does not guarantee an actual SRW/JPEG pair on camera.

### Planned interface

- `nx_pw_plan_capture(request, plan)` returns `NX_PW_ROUTE_REFUSE`, `NX_PW_ROUTE_ORIGINAL_UNCHANGED`, or `NX_PW_ROUTE_HOST_RGB_EFFECT`.
- `source`: `NX_PW_SOURCE_HOST_COPIED_FRAME` or `NX_PW_SOURCE_CAMERA_DEVICE`.
- `mode`: JPEG-only / RAW-only / RAW+JPEG.
- `host_rgb888_validated`: explicit `1` required for any non-original host effect.
- The returned plan always sets `may_change_samsung_picture_wizard=0`, `may_write_native_ycc=0`, `may_write_raw=0`, and `original_vendor_mode_must_be_preserved=1`.

### Coverage

`research/test_nx300m_picture_wizard_route_guard.c` runs **156 combinations** of 13 looks × 2 source environments × 3 file modes × 2 RGB-validity states, plus invalid source/mode/preset values, legacy Leica ID normalization, error output invariants, and an unchanged synthetic RAW copy.

## Before a real device adapter

1. Obtain and authenticate the exact NX300M original firmware **1.14**; compare the four Picture Wizard ELF function bodies and call sites with the previous research baseline.
2. Identify user-facing UI process, event bridge, native parameter IPC and exact mode semantics, and distinguish the 12 native style IDs from the 13 experimental FilmSim look IDs.
3. Verify actual DRIMeIV capture-stage RGB/YCC descriptor ownership and live-view update ordering, including RAW and EXIF/MakerNotes handling.
4. Verify reversible full-brick recovery and preserve device calibration data **before any on-camera modification**.
5. Only then propose a separate device-specific adapter with its own permission and tests. **Do not modify this host-only guard to imply native capture is currently supported.**
