# NX300M FW1.14/1.15: listener relocation witness (2026-11-05)

## Goal

Trace **real ARM32 ELF registration candidates** for the memory-pool
`AllocListener` and `FreeListener` functions. This is a step toward
understanding callback lifetime in the capture-to-JPEG pipeline. It does
**not** replace camera-side runtime measurements.

## Source and method

The read-only native CI extracts version-specific `libmm-photo.so` from
separate, SLP/JAMCRC-checked but **unofficial and unauthenticated**
FW1.14/FW1.15 archives in a private ephemeral runner directory.

- Get defined `AllocListener` / `FreeListener` symbols from actual ARM ELF.
- Parse only genuine `R_ARM_RELATIVE` entries from `readelf -Wr`.
- Map each relocation site to file-backed PT_LOAD bytes.
- Accept a candidate only when its 32-bit raw addend **exactly equals**
  the corresponding listener function address. Skip unrelocated matches
  and non-file-backed addresses.
- Separately report explicit dynamic symbol relocations, if present.
- Compare FW1.14 and FW1.15 SHA-256 and report bounded candidates.

Expected native function addresses in the current matched builds:

| Function | Native address | Previously proven pool edge |
|---|---|---|
| `AllocListener` | `0x00034d9c` | `sysmmap_*_alloc` → `CreateInstance` |
| `FreeListener` | `0x00034fc8` | `GetAddr(0)` → `sysmmap_free` |

Actual pointer counts come from the CI JSON report
`fw114_pool_listener_relocation_witnesses`; **do not guess them**.

## Evidence boundary

A relocation entry can show that a binary stores a listener function
pointer. **It does not show** which native code reads that word, whether
it is installed as a callback, which thread executes it, how frequently
it runs, whether mapping is reused, or when image DMA is complete.

A zero candidate count also does not prove there is no registration:
code may compute or pass a function pointer without a dynamic
relocation, or store it in a different ELF.

## Implemented code

- `research/nx300m_fw114_listener_callback_registration.py`
  (existing scanner, newly connected to real-firmware analysis).
- `research/test_nx300m_fw114_listener_callback_registration.py`
  (new bounded synthetic negative/positive regression).
- `research/nx300m_fw114_native_elf_diff.py` now includes a
  per-version listener relocation report.
- Native Actions verifies function identity, matched firmware and
  fail-closed **NO-DEVICE/NO-FLASH** flags.

## Next firmware-specific investigation

1. Identify exact pointer-consuming functions / registration APIs
   from matching `libmm-photo.so` or associated capture libraries.
2. Check descriptor size provenance for `sysmmap_alloc`; the
   `base+40MiB` constructor field is only an **offset**, never proof
   of the mapped allocation capacity.
3. Determine callback order and concurrency in a read-only physical
   camera trace after memory/DMA and recovery safeguards are established.
4. Only then design a separately owned Y/C copy adapter for the
   independent Film Simulator path.

**Camera Film Simulator install / firmware patch / flash: NO-GO.**
