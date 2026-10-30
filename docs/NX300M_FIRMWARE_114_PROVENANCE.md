# NX300M firmware 1.14: provenance and non-flashing verification

**No authenticated 1.14 original firmware binary, embedded 1.14 sysroot, device hardware, or proven complete-recovery process is available in this public project.** The device owner's reported installed version is 1.14.

## Public release history (sources, not a firmware authenticity certificate)

- October 13, 2014: third-party [Softpedia 1.14 package listing](https://drivers.softpedia.com/get/SCANNER-Digital-CAMERA-WEBCAM/Samsung/Samsung-NX300M-Camera-Firmware-114.shtml) gives `NX300M_FW_v1.14.zip`, approx. 233.7 MB, and attributes the release to Samsung. This page does **not** provide an independently established manufacturer SHA-256 digest or a recovery protocol.
- The current [Samsung NX300M support page](https://www.samsung.com/uk/support/model.EV-NX300MBSVTR/) lists Samsung's **1.15** firmware package, dated December 15, 2014. Listing 1.15 does **not** prove 1.14 source, binary ABI compatibility or that downgrade/recovery is safe.
- The community [NX300M-MFW](https://github.com/fritzchentastig/NX300M-MFW) adds `autoexec.sh` support by modifying firmware and says **1.15** after update. This is a community modification, not the unmodified 1.14 image and not demonstrated full-brick recovery.

## Evidence gates before treating a file as the original 1.14

1. Acquire the original unchanged firmware package only from a source whose chain of custody can be assessed. Record its source URI, acquisition date, exact filename, file size and SHA-256; do not distribute the binary in this public repository.
2. Check archive members read-only and identify a model-specific firmware manifest and version using file signatures and metadata, not merely the ZIP filename. Do not execute the package or initiate an update.
3. Compare all extracted ELF headers and individual object SHA-256 values against the existing 1.1 research extraction using `research/nx300m_tizen_elf_audit.py`. **Identical individual files do not prove identical full firmware, camera ABI, or memory offsets.**
4. Identify exact 1.14 dynamic loader, libc, EFL/Elementary APIs, and target link dependencies. Build a harmless, standalone userspace binary only with a verified matching sysroot.
5. Keep firmware installation blocked until actual device-specific calibration preservation and a independently tested full-brick recovery mechanism are demonstrated.

## Status

| Gate | Status |
|---|---|
| Release listing for v1.14 | Found, third-party, not authenticated |
| Local original v1.14 binary | Not obtained |
| Vendor checksum for 1.14 | Not independently verified |
| ARM32 EABI5 in 1.1 research extraction | 12 existing ELF candidates inspected |
| 1.14 EFL and loader compatibility | Unknown |
| Full-brick recovery | Unknown |
| On-device EFL/Film Simulator execution | Not attempted |

**Do not flash** or replace the installed 1.14 firmware on the basis of these host-side observations.
