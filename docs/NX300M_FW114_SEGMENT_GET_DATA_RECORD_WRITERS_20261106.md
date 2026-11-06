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
