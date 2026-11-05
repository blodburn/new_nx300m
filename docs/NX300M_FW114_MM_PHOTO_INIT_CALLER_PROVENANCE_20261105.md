# NX300M FW1.14/1.15 — mm_photo_init() caller provenance

Date: 2026-11-05.

## Confirmed before this change

Static ARM32 evidence from unofficial, offline FW1.14 / FW1.15
`libmm-photo.so` images:

```text
mm_photo_init() 0x00055114
   BL @ 0x0005511c
   -> PLT _Z24RegisterMemoryMapListnerv (R_ARM_JUMP_SLOT @0x67648)
   -> RegisterMemoryMapListner() @ 0x350d8
   -> sysmmap_client_callback_register @ 0x35110
      r1 = AllocListener / r2 = FreeListener
```

The callback registration chain has a **static code path** but no live
camera or per-shutter execution proof.

## New analysis

`research/nx300m_fw114_mm_photo_init_cross_elf.py` scans selected
camera ELF files in the already checked, private UBI extraction roots
for the exact C++ mangled symbol `_Z13mm_photo_initv`
(demangled: `mm_photo_init()`).

It reports real symbol definitions/imports, ARM relocation targets,
and bounded direct ARM `BL` callsites separately for local and PLT
import targets, per firmware version. The scan avoids arbitrary
substring matches, rejects truncated callgraphs, and never executes
firmware bytes. A potential external import cannot be treated as
resolved live linker state.

The CI logs (once run) will contain:

```text
FW114_MM_PHOTO_INIT_CALLER_MODULE fw114 ...
FW114_MM_PHOTO_INIT_CALLER_MODULE fw115 ...
FW114_MM_PHOTO_INIT_MODULE_SUMMARY fw114 ...
FW114_MM_PHOTO_INIT_MODULE_SUMMARY fw115 ...
```

The actual upstream modules and callsites must come from these logs;
do not assume that the camera app is the caller before checking.

## Native CI result — confirmed two camera-app entry paths

The actual FW1.14 / FW1.15 native CI (not a host mock) resolves
`mm_photo_init()` as an imported `_Z13mm_photo_initv` symbol in
`di-camera-app`. The same target is defined in `libmm-photo.so`.

| Native module / direct ARM BL | FW1.14 | FW1.15 |
|---|---|---|
| `di-camera-app` `R_ARM_JUMP_SLOT` | `0x002a01f0` | `0x00298880` |
| `UI_Operate_Camera_HW_init(bool)` | `0x001f38c0` | `0x001aca80` |
| `UI_Manage_App_Relaunch(eUI_STATE, bool)` | `0x00185bc0` | `0x001cd128` |
| `di-camera-app` scanned ARM functions | 3,659 | 3,660 |
| `libmm-photo.so` scanned ARM functions | 1,233 | 1,233 |

Both UI functions have a direct ARM `BL` edge through the imported
`mm_photo_init()` PLT. These are distinct **code paths** for hardware
initialization and app relaunch; actual camera boot/relaunch event order,
number of invocations and success codes remain **unobserved**.

The CI now rejects an unexpected change in symbol ownership, PLT slot,
caller identity, caller address, or edge classification. The firmware
archives are unauthenticated third-party sources: do not assume the
same addresses apply to a different build.

## Safety and remaining verification

- The firmware mirrors are unofficial and not manufacturer authenticated.
- Only a restricted set of ELF modules and ARM-state direct BLs is
  scanned. Indirect/Thumb/dlsym or unselected modules can be missed.
- Actual boot sequence, callback return status, memory pool size,
  per-frame allocation/free order, DMA coherency and buffer ownership
  are all **unverified**.
- No firmware write, patch, flash, mount, native execution or pixel
  extraction is performed. **Physical camera integration remains NO-GO.**

Next task: if a parent function is identified, trace its registration
callsite arguments and initialization event source. If no caller is
found, expand the search carefully to indirect/dynamic symbol lookup
without asserting absence.
