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
