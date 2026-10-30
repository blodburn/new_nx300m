# NX300M Tizen Film Simulator — standalone EFL UI study

**Status: host syntax and controller validated only. Not installed on a camera.** No NX300M 1.14 ARM executable has been produced.

## UI contract

- Thirteen fixed presets (Samsung Original, seven Fuji-style studies and five Leica Q3-style studies).
- Rotary-like navigation previews a look; explicit Confirm saves, Cancel restores the previous selection.
- Right-side five-item preset list: two before, active, two after. No on-screen PREV/NEXT controls and no intensity slider.
- The EFL window is a **standalone research user interface**, not an overlay injected into Samsung Picture Wizard or live view.
- The existing physical NX300M dial event names are **unverified**. Do not assume generic keyboard arrow events are the real camera dial.
- Only an explicitly configured `NX_FILM_CONFIG` path enables persistence. Without this path, the application shows a preview and refuses to save.

## Generic key mapping (not hardware verified)

| Desktop EFL key | Action |
|---|---|
| `Right` / `Down` | Next preview |
| `Left` / `Up` | Previous preview |
| `Return` / `KP_Enter` / `space` | Confirm and atomically save selected ID |
| `Escape` / `BackSpace` | Cancel changes |
| Unknown key | Ignored |

## Host validation

```sh
make efl-check
make test
```

`make efl-check` uses `research/host_stub/Elementary.h` for C syntax verification **only**. It neither links nor runs actual EFL. `make test` runs the full C/Python suite and specifically checks dial wrap, 13 preset indices, preview-cancel, save errors, original value preservation, symlink rejection and atomic config file writes.

## Conditional cross build — only with verified firmware 1.14 ABI

```sh
make tizen-efl \
  TIZEN_CC=/path/to/verified-arm-eabi5-compiler \
  TIZEN_SYSROOT=/path/to/authentic-114-sysroot \
  TIZEN_PKG_CONFIG_LIBDIR=/path/to/authentic-114-sysroot/usr/lib/pkgconfig
```

The target **refuses to run** when these inputs are absent. It must use an authentic ARM EABI5/Tizen EFL sysroot and never the host stub directory. No matching compiler, EFL headers or sysroot is currently available in the development environment; thus a real ARM build has not been validated.

## Safety gates

An ARM ELF is not an installable firmware package. A matching ELF loader, legitimate userland execution method, nonintrusive input event observation, Picture Wizard overlay integration, and device-specific full-brick recovery must be demonstrated independently before actual on-camera use. The Samsung JPEG/ISP path, RAW isolation, EXIF/MakerNotes, and 16bit sensor processing remain outside this standalone UI.

Files: `research/nx300m_tizen_film_controller.[ch]`, `research/nx300m_tizen_filmsim_efl.c`, `research/test_nx300m_tizen_film_controller.c`, `research/host_stub/Elementary.h`.

## Explicit keyname confirmation before a real dial adapter

- Physical NX300M firmware 1.14 Evas keynames are unknown: input remains disabled unless `NX_FILM_KEY_CW`, `NX_FILM_KEY_CCW`, `NX_FILM_KEY_CONFIRM` and `NX_FILM_KEY_CANCEL` are all valid, distinct bounded names.
- `NX_FILM_DEMO_KEYS=1` enables only desktop demo keynames `Right`, `Left`, `Return`, `Escape`. This does not assert that NX300M physical dials emit these names.
- `NX_FILM_LOG_KEYS=1` enables opt-in stderr observation of at most 32 printable EFL keyname tokens, **only in an independently authorized userspace session**. No kernel input device, serial, credentials or camera memory is accessed. It cannot create a shell.
- Confirm or Cancel no longer silently reopens the menu; a subsequent rotation opens a fresh preview. Saving failures leave the previously selected preset unchanged.
- New sources: `research/nx300m_tizen_keymap.[ch]`, `research/test_nx300m_tizen_keymap.c`, and the updated EFL UI. `scripts/build_tizen_efl.sh` enforces explicit sysroot inputs and ARM ELF32 EABI5 output type.

## New host UI integration test

`make efl-runtime-test` invokes the real EFL screen callback and its state controller through an in-process, fake host Elementary/Evas event loop. Six scenarios check that unknown keys cannot change a saved mode, explicit mapping and demo mapping are separated, preview text updates, confirm writes the chosen mode, cancel restores the old mode, a missing path causes a safe error, and the observer stops after 32 valid keynames. This test does **not** emulate actual NX300M EFL runtime, DRM, display hardware, picture wizard overlay, or the physical rotary dial. Test source: `research/test_nx300m_tizen_efl_runtime.c`.
