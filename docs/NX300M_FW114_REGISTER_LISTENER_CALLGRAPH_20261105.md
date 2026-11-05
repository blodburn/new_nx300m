# NX300M FW1.14 native RegisterMemoryMapListner() caller trace — 2026-11-05

## Exact source facts from earlier native CI

The original, unmodified third-party-mirror FW1.14 and FW1.15
`libmm-photo.so` have a defined method named
`RegisterMemoryMapListner()` (the spelling `Listner` is native).
This method contains static ARM indexed GOT reads:

- `0x000350fc` (`0xe7943003`), resolving the `AllocListener`
  `R_ARM_GLOB_DAT` slot `0x0006868c`.
- `0x00035108` (`0xe7943003`), resolving the `FreeListener`
  `R_ARM_GLOB_DAT` slot `0x00068684`.

Both firmware builds produced these same witnesses.

## New source-based analysis

The independent native-ELF CI now collects direct ARM BL/import callsite
targets for `RegisterMemoryMapListner()`, alongside bounded opcode
windows around the verified GOT reads. This enables a subsequent
register-argument check for any native listener registration call.
It does not rely on host JPEG/LUT simulation.

**Run the native CI to obtain actual call targets and opcode windows.**
Do not guess a target library, function, listener-argument mapping
or live execution frequency from the method's name.

## Restrictions

- All firmware archives are unofficial, unauthenticated source mirrors.
- The analysis is read-only on temporary extracted ARM ELF32 binaries.
- A static GOT load and direct BL does not establish callback execution,
  allocation capacity, DMA cache synchronization or buffer lifetime.
- No picture, raw buffer, device calibration, firmware bytes or physical
  camera is modified.
- Physical-camera Film Simulator integration / flash is **NO-GO**.
