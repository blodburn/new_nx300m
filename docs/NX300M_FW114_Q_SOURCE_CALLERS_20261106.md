# NX300M FW1.14/FW1.15 — reverse Q source / native field +8 writer discovery

**Read-only offline analysis.** The privately extracted firmware archives are untrusted third-party mirrors. No camera connected; no patched firmware built or flashed.

## Current verified expression

```text
segment_update_empty_seg(input source Q)
            |
   [Q + 8] word load  (ARM 0xB188)
            |
   copied to [P + 12] (ARM 0xB190; mempool helper returns P+4)
            |
   segment_alloc [P+12] <<10  (ARM 0xA32C/0xA330)
            |
   osif_alloc mmap length r1 (ARM 0xA33C → 0xC810 → 0xC81C)
```

This is a **conditional static cross-function reconstruction**, not runtime confirmation the same P and Q objects exist, that the copied source word is positive, or that an actual DMA buffer was mapped.

## New reverse-source audit

`research/nx300m_fw114_segment_source_caller_audit.py` scans **all defined ARM function bodies**, not just `sysmmap_segment_*`. For `sysmmap_segment_update_empty_seg` at `0xB0E0`, it identifies direct ARM BL or PLT/GOT-linked callsites, lists entry and pre-call ARM instructions for incoming AAPCS r0/r1 candidates, and inventories bounded native `STR Rt,[Rn,#8]` instructions for `sysmmap_*` functions, excluding plain SP/FP stack writes.

The outputs must not be confused with a complete dataflow: a native BL site does not imply it executed in the user's camera; a `[base,#8]` store does not establish that `base` is the same source object Q passed later. The audit fails closed for ambiguous or out-of-bounds ELF content and checks both FW1.14 and FW1.15 without exporting vendor binaries.

## Remaining tests

1. Locate verified incoming caller and exact value source of Q in its AAPCS register.
2. Locate all constructors and nonzero writers of `Q+8`, resolving base-register aliases and branches rather than guessing from nearby instructions.
3. Verify size conversion and actual kernel mmap extent, buffer ownership and DMA/cache coherence through authorized non-invasive device observation.
4. Do not permit firmware flash before authenticated stock image, calibration preservation, safe recovery and actual JPEG/RAW EXIF behavior.
