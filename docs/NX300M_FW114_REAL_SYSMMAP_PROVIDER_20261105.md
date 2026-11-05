# NX300M FW1.14/1.15 — Real SYSMMAP allocation provider

Date: 2026-11-05. Read-only static native ARM32 analysis. **NO FIRMWARE FLASH**.

## Why this investigation matters

The actual extracted `libmm-photo.so` ELF has a DT_NEEDED reference to
`libsys-mmap-manager.so` in *both* Samsung SLP 1.14 and 1.15 mirror
archives. The former assumed `libsysmmap.so` name is not a match.

```text
di-camera-app
    -> mm_photo_init()
    -> libmm-photo.so
          RegisterMemoryMapListner()
             r1=AllocListener / r2=FreeListener
          AllocListener
             -> sysmmap_cached_alloc / sysmmap_alloc
             -> CMemoryPool::CreateInstance(base)
          FreeListener
             -> sysmmap_free(length,base)
    DT_NEEDED: libsys-mmap-manager.so
```

## Work added

`research/nx300m_fw114_sysmmap_provider_audit.py` selects the
*exact* `libsys-mmap-manager.so` library within the private extracted
firmware root, validates it is ARM32 EABI5, and collects the actual ELF
definition/import status for four API functions:

- `sysmmap_alloc`
- `sysmmap_cached_alloc`
- `sysmmap_free`
- `sysmmap_client_callback_register`

Where functions have file-backed ARM32 bodies, the audit also lists
their bounded direct BL/PLT callees. It records provider SHA-256 and
dependent SONAMEs for both versions. The CI report is prefixed
`FW114_REAL_SYSMMAP_PROVIDER`.

This resolves **which provider the actual photo library requires**.
It does not prove how the kernel maps each request, the actual callback
descriptor length, or cache coherency. If a symbol definition is not in
the provider, search its transitively linked libraries and dynamic
loader metadata before claiming the symbol is absent from firmware.

## Release gates

1. Confirm actual mapping request/return size at an authorized, read-only
   camera diagnostic boundary; do not infer it from the constructor's
   `base+30MiB` and `base+40MiB` pointer arithmetic.
2. Validate that every live mapping covers at least 40 MiB if the pool
   regions are dereferenced.
3. Determine the cached vs ordinary memory path, any ioctl/mmap
   interaction, DMA synchronization, and buffer ownership during JPEG
   encoding.
4. Preserve Samsung RAW and JPEG semantics, EXIF/MakerNotes and
   calibration with verified brick recovery before native integration.

Read-only mirror-ELF metadata alone **does not authorize a patch or
camera firmware installation**.
