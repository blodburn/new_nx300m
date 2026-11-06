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

## Actual FW1.14/1.15 read-only evidence

Native CI confirms all the following in **both** firmware versions:

```text
sysmmap_segment_update_empty_seg() @ 0xB0E0
    r1 → [fp,-28]              @ 0xB0F8
    [Q+8] → r2                 @ 0xB188
    r2 → [get_data(P)+12]      @ 0xB190

ELF relocation: R_ARM_GLOB_DAT  @ 0x1BB14 → update_empty_seg
ELF relocation: R_ARM_JUMP_SLOT @ 0x1BABC → update_empty_seg
raw image pointer literal        @ 0x1214  → 0xB0E0

All defined ELF function bodies:
    direct BL / ARM PLT caller count: ZERO

Potential indirect BLX r3 callsites:
    sysmmap_mempool_merge_empty        @ 0xB9E8, 0xBA2C, 0xBAD4, 0xBB3C
    sysmmap_mempool_get_empty_by_size  @ 0xBCE0
    sysmmap_mempool_get_empty_by_offset @ 0xBE48
    sysmmap_mempool_insert_opreation_by_type
                                       @ 0xC0C4, 0xC0D4,
                                         0xC140, 0xC1EC,
                                         0xC260, 0xC3CC, 0xC3E4
```

The relocations establish that the *address of the copier is represented
in dynamic linkage data*. The raw pointer literal independently
matches its native address. None of the listed BLX targets has yet
been linked to that relocation with branch-aware register/GOT dataflow.
A site-specific indirect caller must **not** be declared proven.

Candidate `STR Rt,[Rn,#8]` instructions also appear in
`sysmmap_list_*`, `sysmmap_mgr_*`, `sysmmap_opmode_arrange`, and
the copier itself. These instruction shapes alone do not identify the
same source record Q.

## Remaining tests

1. Locate verified incoming caller and exact value source of Q in its AAPCS register.
2. Locate all constructors and nonzero writers of `Q+8`, resolving base-register aliases and branches rather than guessing from nearby instructions.
3. Verify size conversion and actual kernel mmap extent, buffer ownership and DMA/cache coherence through authorized non-invasive device observation.
4. Do not permit firmware flash before authenticated stock image, calibration preservation, safe recovery and actual JPEG/RAW EXIF behavior.
