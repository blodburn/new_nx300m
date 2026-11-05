# NX300M FW1.14/FW1.15 — Reverse ARM listener registration callsites

**Date:** 2026-11-05

## Scope

Version-matched read-only ARM32 `libmm-photo.so` extracted only inside
an ephemeral GitHub Actions runner from *unauthenticated third-party
firmware mirrors*. Actual firmware is not edited, shared, installed or run.

## Established static registration edge

```text
RegisterMemoryMapListner() @ 0x350d8
  ├─ AllocListener GOT @ 0x6868c -> AAPCS r1
  ├─ FreeListener  GOT @ 0x68684 -> AAPCS r2
  └─ BL sysmmap_client_callback_register @ 0x35110
```

## New direct-caller scan

`research/nx300m_fw114_listener_registration_callers.py` identifies
the bounded ARM32 direct `BL` callsites whose resolved **local target**
is precisely `RegisterMemoryMapListner()`. For each match, it records
the parent symbol, callsite and bounded nearby opcodes. It scans both
FW1.14 and FW1.15 ELF files and rejects incompatible target symbols.

The relevant CI output is:

```text
FW114_LISTENER_REGISTER_DIRECT_CALLERS fw114 ...
FW114_LISTENER_REGISTER_DIRECT_CALLERS fw115 ...
```

Do not infer the number or names of parent functions before CI has
executed. If there are no direct callers in this ELF, the next step is
to inspect indirect call sites and external library registration paths.
A zero direct-caller count is not proof that registration is never used.

## Verification and restrictions

- Synthetic tests cover missing call graph, truncated inventory,
  near-name matches and bounded ARM windows.
- Actual ARM native CI must compare both versions and reject
  fabricated callback timing or camera DMA safety claims.
- A static call graph does **not** verify registration at a given
  shutter event, allocation lifespan, synchronization, live buffer
  extent or sensor pixel format.
- Firmware patching and camera flash remain **NO-GO**.

## Next technical question

Which device initialization path invokes the callback registration
function, and does its allocation arena remain valid across JPEG
encoding? Resolve with read-only program analysis first; live capture
and DMA measurements require separate recovery and device safeguards.
