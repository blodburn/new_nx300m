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

## Native FW1.14/1.15 ARM result — exact static r1 transfer

The actual native CI first confirmed that both FW versions share
the same `sysmmap_osif_alloc` and `sysmmap_osif_free` bytes. It also
identified the same exact ARM32 save/restore opcodes:

```text
sysmmap_osif_alloc() @ 0xc7a0
   STR r1,[fp,#-28]  @ 0xc7b8  (0xe50b101c)
   ...
   MOV r0,#0         @ 0xc80c  (0xe3a00000)
   LDR r1,[fp,#-28]  @ 0xc810  (0xe51b101c)
   MOV r2,#3         @ 0xc814  (0xe3a02003)
   MOV r3,#1         @ 0xc818  (0xe3a03001)
   BL mmap           @ 0xc81c

sysmmap_osif_free() @ 0xc8bc
   STR r0,[fp,#-16]  @ 0xc8c8  (0xe50b0010)
   STR r1,[fp,#-20]  @ 0xc8cc  (0xe50b1014)
   LDR r0,[fp,#-16]  @ 0xc8d0  (0xe51b0010)
   LDR r1,[fp,#-20]  @ 0xc8d4  (0xe51b1014)
   BL munmap         @ 0xc8d8
```

The new source verifier `exact_static_abi_forwarding` rejects any
change in these exact instructions. The function entry second argument
is saved to stack and restored to `mmap` length register `r1`;
similarly the `munmap` second argument is restored to `r1`.
This remains **a static ABI transfer observation**, not a direct
measurement of runtime requested or allocated bytes or proof against
stack aliases and races.

## Still required

1. Prove the `mmap` length argument's precise internal dataflow with branch-aware provenance and compare with the callback descriptor +4.
2. Obtain independently authorized, read-only evidence of real mapping capacity, mapping success, and camera buffer lifetime. Do not assume 40MiB actual capacity from pool pointer arithmetic.
3. Identify real pixel plane format/stride/matrix, ownership and DMA/cache handoff; preserve RAW/EXIF/MakerNotes.
4. Authenticate physical device firmware, protect camera calibration and establish full-brick recovery **before** any native code injection or firmware write.

**Film Simulator camera integration remains NO-GO.**
