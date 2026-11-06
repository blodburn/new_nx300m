# NX300M FW1.14/1.15: segment_get_data and +12 writer discovery

**2026-11-06** · Third-party FW **offline static** ARM32 investigation.
Nothing was executed on a camera. The firmware files are not committed
or included as build artifacts. No flash is authorized.

## Confirmed get_data pointer indirection

The private native ELF symbol `sysmmap_segment_get_data` is defined
at **0x9ED4**, size **72 bytes**. Its non-null ARM path is:

```text
get_data(input r0)
  0x9EE0 STR r0,[fp,#-16]
  0x9EF0 CMP r3,#0
  0x9EF4 BEQ null-return path
  0x9EF8 LDR r3,[fp,#-16]
  0x9EFC LDR r3,[r3]       ; follow first pointer
  0x9F00 LDR r3,[r3,#4]    ; follow second field pointer
  0x9F04 STR r3,[fp,#-8]
  0x9F08 LDR r3,[fp,#-8]
  0x9F0C MOV r0,r3         ; return pointer
```

This is a *static pointer chain*, not proof of ownership or successful
pointer dereference in a real capture.

## Found one candidate non-stack write at +12

Among the `sysmmap_segment_*` functions examined, the native
`sysmmap_segment_update_empty_seg` function at **0xB0E0** includes:

```text
0xB184 LDR r3,[fp,#-28]
0xB188 LDR r2,[r3,#8]       ; copy source field +8
0xB18C LDR r3,[fp,#-20]
0xB190 STR r2,[r3,#8]       ; copy to target field +8
0xB194 LDR r3,[fp,#-20]
0xB198 MOV r2,#0
0xB19C STR r2,[r3,#12]     ; explicitly write ZERO to +12
0xB1A0 LDR r3,[fp,#-20]
0xB1A4 MOV r2,#0x65
0xB1A8 STRB r2,[r3,#16]    ; marker 0x65 (ASCII 'e')
```

This is **not a positive allocation size initializer**. It is a
candidate empty-segment reset. Whether the target record is the same
object later returned by `get_data` is **not proven**.

The other observed `STR [reg,#12]` matches use r13 (stack pointer)
and do not identify an equivalent segment-data record write.

## Correction: the empty reset writes a different relative offset

FW1.14/1.15 native `sysmmap_segment_get_mempool_data()` at
`0x9A94` calls `sysmmap_segment_get_data()` at `0x9AC4`
and, for a non-null return, executes:

```text
0x9AD8  LDR r3,[fp,#-12]     ; get_data return
0x9ADC  ADD r3,r3,#4         ; mempool helper return = get_data +4
0x9AE0  STR r3,[fp,#-8]
0x9AE8  MOV r0,r3            ; return mempool helper pointer
```

The empty-segment function uses this helper at `0xB128`,
then stores zero at `[returned_pointer +12]` (`0xB19C`):

```text
get_data(x) -> pointer P
    |-- allocation length source:   *(P +12) << 10   (0xA32C)
    +-- mempool helper return:       P +4             (0x9ADC)
           +-- empty reset store:    *(P +4 +12)=0    (0xB19C)
                                               = P+16
```

Thus, **if** these calls received the same input and returned the
same base pointer P, the two instructions still address **different**
fields: `P+12` versus `P+16`. Their inputs and runtime object
identities are not proven identical, so no runtime alias or allocation
size assertion follows. The `+12=0` observation from the prior
iteration is **not** a discovered positive allocation-size initializer.
The `0x65` status marker at `B1A8` is an adjacent field write of
the empty-segment path, not a proof of frame buffer state.

The added fail-closed native verifier pins the exact
`get_mempool_data` ARM opcodes and the two PLT-linked call edges
`get_mempool_data → get_data` and
`update_empty_seg → get_mempool_data` in **both** offline FW builds.
The allocation size record's positive writer is still unlocated.

## Mapping-length relationship from previous research

```text
segment_get_data() --> record pointer
                           |
                     record[+12]       (actual value unknown)
                           |
                       << 10           (FW native ARM 0xA330)
                           |
                   OSIF mmap r1        (FW native ARM 0xA33C)
```

There is **no complete proof** connecting the initial photo listener
`descriptor+4`, every manager transformation, and the record `+12`
contents. There is also no observation of kernel mmap success, allocated
bytes, DMA ownership, cache coherence, image planes, or physical
firmware recovery.

## Follow-up

Trace the return-pointer source of
`sysmmap_segment_update_empty_seg`'s native lookup at `0xB128`;
investigate record construction, updates via memcpy/indirect writes and
the first nonzero assignment of `+12`. Compare both firmware
versions and add fail-closed static checks. Do not flash the device.
