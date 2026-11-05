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

## Same-version native ARM r1 observations

Private CI of actual FW1.14 and FW1.15 extracted library found the
following same-layout **last immediately recognized r1 writer** before
each direct ARM BL. The new code pins the exact opcode and location
for regression detection, not full value identity.

| Function passing to | ARM BL site | Last r1 writer | Meaning |
|---|---|---|---|
| `sysmmap_alloc → mgr_alloc` | 0x3360 | 0x3358 `MOV r1,r3` | r3 value needs tracing |
| `sysmmap_cached_alloc → mgr_alloc` | 0x33f4 | 0x33ec `MOV r1,r3` | r3 value needs tracing |
| `mgr_alloc → client_alloc` | 0x4620 | 0x4618 `LDR r1,[fp,-36]` | stack source |
| `client_alloc → segment_alloc` | 0x786c | 0x7864 `LDR r1,[fp,-20]` | stack source |
| `segment_alloc → osif_alloc` | 0xa344 | 0xa33c `MOV r1,r2` | r2 value needs tracing |
| `sysmmap_free → mgr_free` | 0x347c | 0x3478 `LDR r1,[fp,-12]` | stack source |
| `mgr_free → client_free` | 0x4784 | 0x4780 `LDR r1,[fp,-36]` | stack source |
| `client_free → segment_free` | 0x7914 | 0x7910 `LDR r1,[fp,-20]` | stack source |
| `segment_free → osif_free` | 0xa93c | 0xa938 `MOV r1,r3` | first conditional path |
| `segment_free → osif_free` | 0xa9e4 | 0xa9e0 `MOV r1,r3` | second path |

**IMPORTANT:** AAPCS uses r1 for the second argument, but no evidence
here proves that every function's second argument always means
**allocation size**. In particular, `segment_alloc` forwards r2
into r1. This could represent a transformed/selected length; do not
equate it to the incoming descriptor without full control/dataflow.
Likewise, the existence of two free callsites does not mean both
execute in a single invocation.

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
