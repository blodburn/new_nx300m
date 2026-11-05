# NX300M FW1.14/1.15 — Cross-ELF Memory-Map Listener References

Date: 2026-11-05

## Trigger

The previous real-firmware scan inspected **1,233 ARM32 functions per
version** in `libmm-photo.so` and found **zero local direct BL callers**
of `RegisterMemoryMapListner()`. This does not show that the function
is unused. An external ELF, indirect function pointer, or dynamic
symbol lookup can reach it.

## New read-only analysis

`research/nx300m_fw114_listener_cross_elf_imports.py` selects a
bounded set of relevant ARM32 files from the private firmware UBI
extraction. It inspects readelf symbol tables and relocation metadata
for the **exact** demangled C++ symbol
`RegisterMemoryMapListner()` (native spelling). It reports:

- Modules which define or import the exact native symbol.
- Symbol section `UND` vs defined, without assigning runtime meaning.
- Exact ARM ELF relocation sites/types with this native symbol.
- Files examined and files excluded from the deliberately bounded set.

The associated CI output is:

```text
FW114_CROSS_ELF_REGISTRATION_REFS fw114 ...
FW114_CROSS_ELF_REGISTRATION_REFS fw115 ...
FW114_CROSS_ELF_REGISTRATION_MODULE ...
```

Do not invent module names or relocations. Use the generated CI data.

## Evidence boundary

The archive sources are **unofficial / unauthenticated**. A dynamic
symbol or relocation is not a call. This analysis does not execute
vendor code, establish process load order, find all `dlsym` or Thumb
callers, prove callback timing, validate the allocation size, or show
DMA synchronization. Full firmware flash and camera Film Simulator
installation remain **NO-GO**.

## Next verification

If an external caller is found, identify its own *direct ARM BL* and
the argument provenance into `RegisterMemoryMapListner()`. If none
is found, inspect dynamic lookup and indirect call paths. Only
instrument a physical camera after an approved read-only recovery
procedure exists.
