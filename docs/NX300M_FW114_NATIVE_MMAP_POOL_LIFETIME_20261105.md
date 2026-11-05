# NX300M FW1.14 — Real mmap-backed Y/C pool base, slots, and lifecycle: ARM static evidence

**2026-11-05.** Real ARM32 instructions from privately extracted firmware-identified FW1.14 and FW1.15 *third-party / unauthenticated* SLP/JAMCRC/UBI archives. **Offline only.** No camera, hardware DMA access, patch, firmware install or test shot.

## Main result — base pointer origin now found

```text
FW1.14 libmm-photo.so  AllocListener             @ 0x00034d9c
   │
   ├─ optional cached allocation:
   │    sysmmap_cached_alloc                       @ BL 0x00034e44
   │    MOV r3,r0 / STR r3,[fp,#-16]               @ 0x34e48/34e4c
   │    B 0x00034e78                              @ 0x34e50
   │
   └─ non-cached allocation:
        descriptor [base+4] -> r0 (size parameter)
        descriptor [base+12] -> r1 (mode parameter)
        sysmmap_alloc                              @ BL 0x00034e6c
        MOV r3,r0 / STR r3,[fp,#-16]               @ 0x34e70/34e74
                                              │
   LDR r0,[fp,#-16]  (returned mmap pointer)  @ 0x34e78
   CMemoryPool::CreateInstance(unsigned int)  @ BL 0x34e7c
                                              │
                CMemoryPool::CMemoryPool       @ 0x351b4
                 +0  = base pointer
                 +4  = base + 0x01e00000 (30 MiB)
                 +8  = base + 0x02800000 (40 MiB)
                                              │
               CMmDeviceDriver::EncodeYcc
                 GetType ==1 ? yes
                 GetAddr(2) -> CMemoryPool +8
                 CYcc(temp), ResizeImage
                 copy *descriptor*, not proved copy of owned pixels
                 ~CYcc() directly frees no pixels
                                              │
                  FreeListener                @ 0x34fc8
                    CMemoryPool::GetInstance  @ BL 0x35028
                    MOV r1,#0                 @ 0x35034
                    CMemoryPool::GetAddr(0)   @ BL 0x35038
                    save base to [fp,#-16]    @ 0x35040
                    MOV r0,size; MOV r1,base  @ 0x35050/0x35054
                    sysmmap_free              @ BL 0x35058
                    CMemoryPool::Destory      @ BL 0x35068
```

### Scope and confidence

- **Proven native symbol and ARM call graph, per mirror build:** `AllocListener` calls `sysmmap_cached_alloc` and `sysmmap_alloc` on separate static paths. Both returned values feed the common `CMemoryPool::CreateInstance` argument via `[fp,-16]`.
- **Proven layout by exact ARM instructions:** constructor `CMemoryPool(unsigned int)` @ `0x351b4` copies incoming `r1` to `this+0`, uses `ADD r2,r3,#0x1e00000` @ `0x351dc` to store `this+4`, then `ADD r2,r3,#0xa00000` @ `0x351f0` to store `this+8` at `0x351f8`. These are **pointer offsets**; not a measured allocated buffer capacity.
- **Proven release argument transfer:** `FreeListener` obtains `CMemoryPool::GetAddr(0)`, passes returned base to `sysmmap_free(size,base)`, and destroys the pool wrapper. Its lifecycle frequency and whether concurrent readers are active is *not* known.
- **Constrained inventory:** 1,233 native functions of `libmm-photo.so` inspected per version for ARM **direct BL** calls. One `AllocListener→CreateInstance` and one `FreeListener→Destory` match. Other dynamic, virtual, indirect or cross-ELF accesses and raw stores may exist.
- **No memory safety proof:** firmware might share/reuse the same mapped region, alter contents, use DMA and caches, or free the base while another thread accesses it. No mutex, reference count, physical frame stride, allocator-returned length, sensor format or real shutter timing has been verified.
- `CYcc::~CYcc()` in actual `libmm-type.so` is 9 ARM instructions with no direct free, but **absence of a free in a wrapper does not grant ownership**.

## New code and verification

- `research/nx300m_fw114_pool_slot8_writer_audit.py`: read all six real `CMemoryPool::` methods; list actual 32-bit ARM direct member `+8` stores, decode exact constructor 30MiB/40MiB pointer calculations and native method imports; reject changed ARM opcodes.
- `research/nx300m_fw114_pool_create_caller_audit.py`: search all bounded `libmm-photo.so` defined ARM functions for actual CreateInstance/Destroy `BL→PLT→R_ARM_JUMP_SLOT` imports, then verify *both* alloc return-value copies and pool-base free argument transfer using same-version ARM instructions.
- `research/test_nx300m_fw114_pool_slot8_writer_audit.py` and `research/test_nx300m_fw114_pool_create_caller_audit.py`: synthetic source-only negative tests; no vendor code committed.
- `research/nx300m_fw114_native_elf_diff.py`, `.github/workflows/nx300m-fw114-native-elf-diff.yml`, `Makefile`: require actual FW1.14 and FW1.15 ELF evidence, explicit no-device and no-flash guardrails and regression checks. Actual firmware ZIP, extracted UBI and proprietary ELFs stay in ephemeral private CI and are deleted.

## Next hard blockers (in order)

1. Locate OS-level actual `sysmmap_alloc/sysmmap_cached_alloc/sysmmap_free` implementations, validate allocated sizes, cached/uncached aliasing and possible DMA cache fencing.
2. Find **when** `AllocListener` and `FreeListener` run in actual camera capture sessions; determine whether pool is reused on each shot, subject to asynchronous concurrency, and who owns the read/write window.
3. On owner-authorized physical device, obtain *read-only* same-stage Y0/Y1/C0/C1/stride/format and pool pointer snapshots without capturing sensitive imagery or touching existing calibration; verify memory fence and buffer lifetime.
4. Only after proof of a copy-owned, validated buffer and firmware recovery, consider a separately reviewed Film Simulator native adapter; verify native JPEG/EXIF/MakerNotes, 20.6MP, RAW independence, speed and thermal impact.

**Final status: Static allocator→pool→free path is identified. Live camera DMA and Film Simulator are NOT implemented or verified. Firmware patch/flash NO-GO.**
