# NX300M FW1.14/1.15 — Native memory-map size contract

**Date:** 2026-11-05. **Scope:** ARM32 ELF static analysis of unauthenticated, unofficial firmware mirrors in a private, read-only GitHub Actions runner. No camera flash.

## Verified code relationship

```text
AllocListener(callback descriptor)
  descriptor + 4 @ ARM 0x34e58    -> sysmmap_alloc length r0 @ 0x34e64
  descriptor + 12 @ ARM 0x34e60   -> sysmmap_alloc mode r1 @ 0x34e68
  sysmmap_alloc() -> CMemoryPool::CreateInstance(base)

CMemoryPool constructor @ 0x351b4
  this+0 = base
  this+4 = base + 30 MiB
  this+8 = base + 40 MiB

FreeListener(callback descriptor)
  descriptor + 4 @ ARM 0x35048  -> sysmmap_free length r0 @ 0x35050
  CMemoryPool::GetAddr(mode 0) -> sysmmap_free base r1 @ 0x35054
```

## New actionable offline guard

`research/nx300m_fw114_pool_mmap_size_contract.py` rechecks the
exact version-matched ARM opcodes, derives the minimum region extent
`40 * 1024 * 1024 = 41,943,040 bytes`, and introduces
`assert_contract(alloc_bytes, free_bytes)` for **future explicit
runtime diagnostic size samples**.

The guard rejects: non-integer samples, either length smaller than
40 MiB, and unequal allocation/release lengths. Even a passing sample
does not prove that a mapping can safely be used by image processing,
or that a buffer remains valid for DMA. No samples are fabricated.

## Critically unverified

**The actual descriptor size at runtime is unknown.** The constructor
adding 40 MiB is not evidence that the kernel allocated at least
40 MiB. The `sysmmap_cached_alloc` alternative requires separate
runtime bounds verification. These checks do not establish an mmap
physical bound, write permissions, cache flush/invalidation, ISP
pixel layout or capture frame lifetime.

`FW114_MMAP_ALLOC_LISTENER_ARM_WINDOW` and
`FW114_MMAP_FREE_LISTENER_ARM_WINDOW` CI logs provide the bounded
actual ARM words around both native size descriptors, without leaking
firmware binaries as repository artifacts.

## Release decision

```text
        Native static 40MiB lower-bound proof: YES
        Actual allocated region >= 40MiB:    UNKNOWN
        Same actual alloc/free descriptor:     UNKNOWN
        Camera pixel DMA coherency:            UNKNOWN
        Firmware flash / camera hook:          NO-GO
```

Next: parse the bounded native `AllocListener` cached vs uncached
branch and identify a safe, read-only runtime diagnostic source for
descriptor length and buffer ownership, before any film engine
integration on a physical camera.
