# NX300M FW1.14 / FW1.15 — segment-record size to mmap r1

**2026-11-06 · OFFLINE ARM32 STATIC RESEARCH · CAMERA FLASH: NO-GO**

## New confirmed static formula

In actual extracted FW1.14/1.15 third-party firmware
`libsys-mmap-manager.so`, `sysmmap_segment_alloc()` at
`0x0000a114` contains these instructions:

```text
BL sysmmap_segment_get_data   @ 0xa2e4
STR r0,[fp,#-36]              @ 0xa2e8       save data record
  ... BNE -> 0xa320           @ 0xa2f4       conditional branch
LDR r3,[fp,#-36]              @ 0xa320       reload record
LDR r1,[r3,#8]                @ 0xa324       independent record field
LDR r3,[fp,#-36]              @ 0xa328       reload record
LDR r3,[r3,#12]               @ 0xa32c       size-unit record word
MOV r2,r3,LSL #10             @ 0xa330       multiply by 1024 in u32
LDR r3,[fp,#-104]             @ 0xa334
MOV r0,r1                     @ 0xa338
MOV r1,r2                     @ 0xa33c       second OSIF argument
MOV r2,r3                     @ 0xa340
BL sysmmap_osif_alloc         @ 0xa344
   ... incoming r1 stored/reloaded ...       (PR #43)
BL mmap                     @ 0xc81c       OS mapping request
```

**The proven static mapping-request formula on this branch is
`uint32(record_word_at_+12 << 10)`.** The 10-bit left shift corresponds
to multiplying a record value by 1,024; the semantic unit may be KiB,
but the record's actual contents are NOT known.

This is different from claiming that the listener's
`descriptor+4` length is exactly the OS-requested size. The manager
can select, align, split or otherwise transform a record before the
segment allocator. The earlier `base+40MiB` CMemoryPool pointer
offset is NOT proof that the OS mapped 40MiB.

## Code and CI

- `research/nx300m_fw114_segment_record_size_proof.py` pins 11 exact
  native ARM words, the conditional BNE target, the
  `segment_get_data` and `sysmmap_osif_alloc` PLT-linked calls,
  and the ARM `MOV r2,r3,LSL #10` decoder.
- `research/test_nx300m_fw114_segment_record_size_proof.py`
  mutates each exact instruction, rejects changed shifts, and
  fail-closes on potential 32-bit byte-length wrap. The host-side
  example `40*1024` produces `40*1024*1024` bytes; this is **only
  a simulation, not a device observation**.
- The native CI revalidates the actual instruction sequence
  independently in both privately extracted third-party firmware
  versions and deletes the extracted images after testing.

## Remaining hard blockers

1. Determine where `sysmmap_segment_get_data()` obtains the
   record `+12` field and whether it selects or rounds a request.
2. Prove the relationship between the photo listener's
   `descriptor+4`, segment record `+12`, the actual kernel mmap
   size, and any memory-pool overlaps in a real capture session.
3. Prove same-stage Y/C plane strides, pixel packing, DMA ownership,
   cache synchronization and release/concurrency behavior.
4. Verify target Tizen loader integration, JPEG/EXIF/MakerNotes
   retention and RAW isolation with a recoverable physical camera.
5. Establish camera-specific calibration preservation and full-brick
   recovery before any firmware write.

**No physical NX300M was contacted. No installable firmware was
produced. Static source analysis is NOT a flash authorization.**
