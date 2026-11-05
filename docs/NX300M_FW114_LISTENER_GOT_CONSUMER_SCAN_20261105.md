# NX300M FW1.14/1.15: native listener GOT-use scan (2026-11-05)

## Observed relocation anchors

Independent FW1.14 and FW1.15 native CI has already located the
following **actual** `R_ARM_GLOB_DAT` slots in `libmm-photo.so`:

| Listener function | Relocation slot |
|---|---|
| `AllocListener` | `0x0006868c` |
| `FreeListener` | `0x00068684` |

The first relocation-only scan showed **zero**
`R_ARM_RELATIVE` pointer-word witnesses to either function.
It showed one `R_ARM_GLOB_DAT` relocation for each listener in
each firmware version. These establish references in the ELF's
dynamic-linker data, **not** registration or execution.

## New, read-only ARM PIC/GOT code scan

`research/nx300m_fw114_listener_got_consumer_audit.py` scans bounded,
version-matched ARM-state methods and recognizes conservative,
straight-line patterns:

- `LDR Rx,[PC,#literal]` → literal word from a file-backed PT_LOAD.
- `ADD Ry,PC,Rx`, `MOV`, and immediate `ADD`.
- `LDR Rz,[Ry,#imm]` or `LDR Rz,[Ry,Rindex]` where the *calculated*
  effective address equals the symbol's **actual relocation slot**.
- It clears unproven register state on conditional instructions and
  branches and never treats a slot load as a call or callback install.

All matched locations are exported in
`fw114_pool_listener_got_consumers` with the function name, ARM
instruction address, GOT slot and narrow local address provenance.
Counts **must come from CI**, not from guessed code paths.

## Scope limits and next action

A GOT load is only a *candidate pointer consumer*. It does **not**
prove that the value is used to register a callback, its call frequency,
the lifetime of an allocated Y/C buffer, a safe offset, or DMA fencing.

A zero candidate count is also not proof of absence; the search does
not reconstruct complete control flow and does not cover unaligned or
Thumb code, arbitrary computed offsets, external libraries or other
dynamic registration mechanisms.

The next analysis must trace any candidate pointer into the native
listener registration API and its capture event ordering. If no
consumer is found, expand to the actual external-library caller
rather than repeat JPEG/LUT host benchmarks.

**Physical-camera Film Simulator integration and firmware flash:
NO-GO until lifetime, DMA, verified firmware and recovery are proven.**
