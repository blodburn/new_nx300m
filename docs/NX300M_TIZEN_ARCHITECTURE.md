# NX300M uses Tizen Camera Platform — architecture and safe development route

## Source-backed clarification

The Samsung NX300M is a DRIMeIV Linux-based **Tizen Camera Platform** device, not an Android camera or a bare-metal-only microcontroller. Samsung's 2013 Tizen presentation explicitly identified the NX300M. The community NX firmware archives group DRIMeIV cameras under the Tizen 1.0 generation.

This **does not mean** an unmodified NX300M running **firmware 1.14** can launch an arbitrary shell script, receive an arbitrary Tizen application package, or expose a public camera plug-in API. The community [NX300M-MFW](https://github.com/fritzchentastig/NX300M-MFW) project describes an altered firmware with `autoexec.sh` restored, and explicitly describes **1.15** after its update. It is not a verified reversible method for the user's installed **1.14**. **Do not flash it, downgrade, or change boot services as part of this project without a proven device-specific full-brick recovery.**

## Architecture: two separate layers

1. **Tizen/Linux userspace:** 32-bit ARM ELF EABI5 executable/library environment. User interface can potentially use Samsung-era EFL/Elementary, but exact camera 1.14 sysroot, graphics compositor and screen-integration contracts remain unverified. The existing `research/nx300m_film_menu_efl.c` is a standalone research prototype, **not** a working Picture Wizard replacement.
2. **Capture/ISP/JPEG subsystem:** Proprietary Samsung image processing, DRIMeIV B2Y, `CYcc` metadata and original JPEG encoder. Linux userspace access to a camera process does **not** automatically authorize changing its DMA buffer or ensure 16-bit RAW processing compatibility. A safe interface, buffer lifetime, cache ownership and EXIF persistence must be proved separately.

### Proposed order of work

- **Offline ELF ABI inventory first:** run `python3 research/nx300m_tizen_elf_audit.py --root /path/to/previously-extracted-readonly-root --summary`. It checks ELF32, little-endian ARM, EABI5 candidates. ARM EABI5 alone is **not proof** of Tizen; the script reports only the supporting evidence available.
- **Binary identity before version-specific offsets:** if separately authenticated and legitimately extracted 1.14 original files become available, use `--compare-to /path/to/verified-114-extraction` to identify whether any *individual* ELF paths are identical. Even matching individual files does **not** prove full-firmware ABI compatibility or permit offset reuse; the output explicitly says so.
- **Read-only device environment information only if an authorized shell already exists:** `sh scripts/nx300m_tizen_readonly_probe.sh`. The script reports kernel machine/release and only the existence of generic runtime libraries. It does **not** probe credentials, serial numbers, memory, firmware storage or networking. It does **not** create shell access or activate `autoexec.sh`.
- **Cross-build using exact sysroot:** choose target ARM EABI5 compiler, 1.14 userland loader/C library and EFL headers only after verifying runtime. Begin with a harmless standalone preset selector, no capture hooks. A binary built for desktop Linux or current Tizen TV/phone is not guaranteed to load.
- **Camera-native capture integration last:** require native 1.14 image plane evidence, available recovery, one-JPEG-per-shutter/RAW isolation, MakerNotes integrity and original fallback before altering capture flow.

## Read-only tool commands

```sh
python3 research/nx300m_tizen_elf_audit.py \
  --root /path/to/verified-offline-elf-extraction --summary
# Only when a separate, legitimately extracted target is available:
python3 research/nx300m_tizen_elf_audit.py \
  --root /path/to/offline-1.1-reference \
  --compare-to /path/to/authentic-offline-1.14 \
  --summary

# Not a flash instruction. Only inside an already authorized shell:
sh scripts/nx300m_tizen_readonly_probe.sh
```

**Limitations:** No original 1.14 image, physical camera, native DMA sample or full-brick recovery mechanism is provided with this repo. The public repository intentionally contains **no Samsung firmware, extracted proprietary ELF, proprietary calibration or private RAW captures**.
