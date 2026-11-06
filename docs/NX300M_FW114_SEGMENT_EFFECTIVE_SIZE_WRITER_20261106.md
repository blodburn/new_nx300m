# NX300M FW1.14/1.15 — actual segment size-word copy into `get_data +12`

**2026-11-06 · SOURCE: privately extracted, unauthenticated third-party FW ELF · CAMERA FLASH: NO-GO**

## Corrected source of `record+12`

The previous investigation identified:
- `sysmmap_segment_get_data(x)` -> pointer `P` on its non-null path.
- `sysmmap_segment_get_mempool_data(x)` -> `P+4` for the same hypothetical `x`.
- `sysmmap_segment_alloc` loads `[P+12]`, shifts left 10 bits, passes it via r1 to `sysmmap_osif_alloc`, which forwards it to `mmap`.

A previously overlooked **`STR [r3,#8]`** is the candidate writer of `P+12` because the destination pointer is `P+4`. Within `sysmmap_segment_update_empty_seg` (`0xB0E0`):

```text
get_mempool_data(input) → P +4                     (BL 0xB128)
                                     │
                saved in [fp-20]    (0xB12C)
                                     │
source_ptr = [fp-28]                 (0xB184)
value      = *(source_ptr +8)        (0xB188)
dest_ptr   = [fp-20]                 (0xB18C)
*(dest_ptr +8) = value               (0xB190) ───> *(P+12)
                                     │
value = 0                            (0xB198)
*(dest_ptr +12) = 0                  (0xB19C) ───> *(P+16)
                                     │
*(dest_ptr +16) = 0x65 (one byte)    (0xB1A8) ───> *(P+20)
```

This is a **conditional native code path**, not proof that the source value is nonzero or that it represents the original listener's requested byte length. The source and destination pointer identities, runtime values and call frequency remain unknown. It is incorrect to say `P+12` is initialized directly to zero by `B19C`. The **actual writer candidate at B190 copies the source's +8 field**.

## New fail-closed native regression test

`research/nx300m_fw114_record_size_copy_proof.py` verifies 21 exact A32 instructions from the function, checks the previously established `get_data→get_mempool_data (+4)` contract, and the exact imported `update_empty_seg → get_mempool_data` call. It rejects any mismatch in FW1.14/1.15 private extraction. The companion synthetic tests corrupt each required word to ensure failures.

**Still unverified:** Is `source_ptr` a particular structure passed from `client_alloc` or an independent/free-list record? Is `source_ptr+8` a size in units of 1024 bytes, and how is it initialized? Do the two calls reference the same `P`? What bytes did the kernel really map? No camera hardware validation, DMA cache fence, Y/C layout, RAW/MakerNotes guard or calibration restoration is proven.

## Next static gate

Identify the actual caller(s) and the input register/stack source of `sysmmap_segment_update_empty_seg`, then trace the origin of `source_ptr+8` without equating it to the listener descriptor or an unmeasured camera allocation.
