# NX300M FW 1.14 — installed library identity gate

Date: 2026-11-09. **READ-ONLY. DEVICE FIRMWARE: NO-GO.**

## Missing evidence

The FW 1.14/1.15 offline ARM call graph uses third-party mirrored
firmware. This is not automatically the same binary installed on the
owner's real camera. The existing runtime metadata probe only reports
process/library presence, not exact ELF byte identity.

This work introduces a fixed-name read-only SHA-256 shell probe, a
PC-side hash comparison against actual operator-selected ARM32 ELF
files, and synthetic negative/positive regression tests.

## Owner-controlled evidence procedure

Only run in an **already authorized local camera shell**. This
repository does not provide remote access, root escalation, an
autoexec payload, telnet, camera capture, DMA access or an installer.

The library directory must contain all four files:
- libmm-photo.so
- libsif.so
- libcapture-fw-slpcam-nx300.so
- libsys-mmap-manager.so

They must be readable ordinary files, not symbolic links. If the camera
places them in different directories or uses symlinks, the script
reports INCOMPLETE. It never recursively searches the device or logs
paths, process IDs, serials, addresses or other personal information.

Camera shell command (manual, if already authorized):

    sh nx300m_fw114_installed_elf_fingerprint.sh /absolute/library/directory

Capture the displayed report through the existing host terminal; the
probe itself writes no file. On a PC holding the previously extracted
private FW1.14 mirror ELF files in one directory:

    python3 research/nx300m_fw114_installed_elf_identity_gate.py \
        --report /private/device-probe.txt \
        --reference-libdir /private/unofficial-fw114-reference-libs

Exit code 0: all four installed hashes/bytes match this local reference.
Exit code 3: DIFFERENT_BYTES or INCOMPLETE.
Exit code 2: rejected input.

The report also compares the offline SYSMMAP reference with prior study
SHA-256 118a0d77927bfca7576458d86284889143ece1c13578edc96a480911faa5bea9.
This is only a fingerprint of a third-party mirror, NOT a vendor signature.

## Limits

A hash match does not authenticate the device that produced the text.
It is not proof that Linux loaded those bytes or that the live capture
callback, DMA, native Y/C420 layout, cache coherency, camera JPEG/EXIF,
recovery or safe installation works. None of those gates can be promoted
to PASS by this procedure.

The new scripts were exercised only with synthetic local ARM32 ELF
test files. No physical NX300M was accessed or modified. Physical
firmware installation remains NO-GO.
