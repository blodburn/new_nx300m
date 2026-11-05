# NX300M FW 1.14 / 1.15 — SYSMMAP nine-function argument chain

**Date:** 2026-11-06 · **State:** offline ARM32 analysis of unauthenticated third-party firmware; NO DEVICE FLASH.

## New code

`research/nx300m_fw114_sysmmap_upstream_size_chain.py` performs a
bounded ELF symbol + PLT/GOT relocation check for the exact native call
sequence below. It emits entry ARM words and up-to-32 ARM instructions
preceding each call, plus conservative r1 argument register writer
candidates. `research/test_nx300m_fw114_sysmmap_upstream_size_chain.py`
tests synthetic edge cases. The GitHub Actions native job analyzes both
private firmware extractions, but publishes **no vendor ELF bytes**.

```text
libmm-photo.so: AllocListener(descriptor+4: length)
            |
            v
libsys-mmap-manager.so:
  sysmmap_alloc   \---> sysmmap_mgr_alloc
  sysmmap_cached_alloc /
                               |
                               v
                     sysmmap_client_alloc
                               |
                               v
                     sysmmap_segment_alloc
                               |
                               v
                     sysmmap_osif_alloc
                               |
                        mmap (r1=length)

  sysmmap_free → sysmmap_mgr_free
                    → sysmmap_client_free
                        → sysmmap_segment_free
                            → sysmmap_osif_free
                                → munmap (r1=length)
```

## Research limits

An ARM machine-code BL callsite demonstrates that a function can call
a target. It does not prove control-flow conditions, successful
execution, what the full argument dataflow is through all nine
functions, actual runtime byte length, allocation size, memory ownership,
DMA coherence, or firmware safety. A nearby LDR/MOV instruction is only
an argument writer **candidate** until aliasing and cross-call paths
are validated.

Existing confirmed facts: the photo listener loads its length from
`[descriptor+4]`; the OS interface wrapper stores its incoming r1 at
`[fp-28]` and reloads r1 before mmap. This audit is intended to
identify every intermediate size conversion or redirection, not infer
that `40 MiB` was actually allocated from pool pointer offsets.

**Next gate:** analyze the native r1 writer windows for each layer,
examine branching and size rounding/selection, then perform
non-invasive runtime capacity and frame lifetime observation on a
specifically authorized camera; do not flash or patch on the basis
of static evidence.
