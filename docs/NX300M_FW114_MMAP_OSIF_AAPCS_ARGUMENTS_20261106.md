# NX300M FW1.14 / FW1.15: OSIF `mmap` AAPCS parameter windows

**Status:** ARM32 offline static analysis; no camera runtime evidence, no patch, no flash. Source firmware mirrors are third-party and unauthenticated.

## Actual static call path (prior verified)

```text
di-camera-app → mm_photo_init()
       → libmm-photo.so → AllocListener()
       → libsys-mmap-manager.so → sysmmap_mgr_alloc()
       → sysmmap_client_alloc()
       → sysmmap_segment_alloc() (BL 0xa344)
       → sysmmap_osif_alloc() @ 0xc7a0
         ├ ioctl() @ BL 0xc7f0
         └ mmap()  @ BL 0xc81c
       ...
       → sysmmap_osif_free() @ 0xc8bc
         └ munmap() @ BL 0xc8d8
```

## New verification

`research/nx300m_fw114_sysmmap_osif_arg_windows.py` requires the real function symbols, addresses, sizes, and import-linked BL sites in both private FW ELFs. It emits bounded ARM code windows and conservative AAPCS register writer **candidates** before the `ioctl`, `mmap` and `munmap` calls. The 32-bit ARM Linux `mmap(addr,len,prot,flags,fd,offset)` signature places `len` in **r1**, when this libc entry follows the normal six-argument AAPCS convention.

Source observations must determine where r1 comes from in the actual instruction stream. A nearby MOV, ADD or LDR is a *candidate*, not a validated dataflow across branches, calls or aliases. Do not infer a runtime length, a successful kernel mapping, an owned frame buffer, or DMA-safe cache coherency. If a size is loaded from a structure, its actual bytes remain unknown until independently measured.

The native CI logs use prefix `FW114_SYSMMAP_OSIF_AAPCS_WINDOW`. They do not export or publish vendor ELF data as artifacts.

## Still required

1. Prove the `mmap` length argument's precise internal dataflow with branch-aware provenance and compare with the callback descriptor +4.
2. Obtain independently authorized, read-only evidence of real mapping capacity, mapping success, and camera buffer lifetime. Do not assume 40MiB actual capacity from pool pointer arithmetic.
3. Identify real pixel plane format/stride/matrix, ownership and DMA/cache handoff; preserve RAW/EXIF/MakerNotes.
4. Authenticate physical device firmware, protect camera calibration and establish full-brick recovery **before** any native code injection or firmware write.

**Film Simulator camera integration remains NO-GO.**
