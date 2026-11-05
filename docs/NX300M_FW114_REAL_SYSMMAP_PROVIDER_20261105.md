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

## Actual native FW1.14 + FW1.15 ARM callsites found

The actual `libsys-mmap-manager.so` binary SHA256 is identical in
both mirror versions: `118a0d77927bfca7576458d86284889143ece1c13578edc96a480911faa5bea9`.

```text
sysmmap_alloc                       BL @ 0x3360 ┐
sysmmap_cached_alloc                BL @ 0x33f4 ├→ sysmmap_mgr_alloc
                                                   BL @ 0x4620
                                                      → sysmmap_client_alloc
                                                         BL @ 0x786c
                                                            → sysmmap_segment_alloc

sysmmap_free                        BL @ 0x347c → sysmmap_mgr_free
                                                   BL @ 0x4784
                                                      → sysmmap_client_free
                                                         BL @ 0x7914
                                                            → sysmmap_segment_free

sysmmap_client_callback_register   BL @ 0x3160 → sysmmap_mgr_register_callback
```

The direct targets above are resolved via the provider's ARM PLT
relocations. This does **not** prove the chain is executed in the user's
camera, that allocation succeeds, the allocated byte count or the actual
Linux kernel mapping length.

The native CI pins all eight exact ARM callsites for both firmware
versions; a changed native target or callsite fails closed.

**Next unresolved link:** `sysmmap_segment_alloc/free` and possible
underlying device mmap/ioctl operations. Analyze read-only ARM bytes
and operator/lifetime semantics before considering a native image hook.

## Next static segment-provider audit

The additional actual ARM call edges in PR #41 reach
`sysmmap_segment_alloc`, `sysmmap_segment_free`,
`sysmmap_segment_init` and `sysmmap_segment_destroy`. The native
auditor now includes these exact exported ELF functions, if present,
and reports their direct ARM BL/PLT callees. This is intended to identify
whether the local segment implementation calls OS `mmap/munmap`,
`ioctl`, other helpers, or indirect register branches.

Any inferred kernel mapping length remains UNKNOWN unless an
independently observed descriptor and valid return size are available.
The analysis is read-only and does not run on the physical camera.

## Exact OS interface ARM callsites found (2026-11-05)

Both **FW1.14 and FW1.15** third-party mirrored firmware builds
contain identical native `libsys-mmap-manager.so` static ARM code
reaching Linux memory interfaces:

```text
sysmmap_segment_alloc() @ 0xa114
   └── BL 0xa344 → sysmmap_osif_alloc() @ 0xc7a0
        ├── BL 0xc7f0 → ioctl
        └── BL 0xc81c → mmap

sysmmap_segment_free() @ 0xa828
   ├── BL 0xa93c → sysmmap_osif_free() @ 0xc8bc
   └── BL 0xa9e4 → sysmmap_osif_free() @ 0xc8bc
        └── BL 0xc8d8 → munmap
```

The CI asserts all six precise ARM callsites for both firmware
versions. This proves the **static call linkage** reaches OS mapping
APIs. It does not prove specific execution paths (e.g. both frees per
call), an ioctl request number, mmap arguments, a returned base,
allocated size, frame lifetime, physical DMA synchronization or
camera recovery.

Next: reconstruct bounded `sysmmap_osif_alloc` argument registers
before the `mmap` call and compare the requested length with
`descriptor+4`, then obtain only independently authorized, read-only
runtime evidence for actual allocation extent. Device flashing
continues as **NO-GO**.

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
