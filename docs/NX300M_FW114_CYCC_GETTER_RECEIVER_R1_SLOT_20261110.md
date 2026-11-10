# NX300M FW1.14/1.15: CYcc getter receiver r0 source

Date: 2026-11-10. Read-only static analysis of third-party mirror
ELFs. Firmware installation and native device callback: NO-GO.

## Why this check exists

Native ARM32 CMmDeviceDriver::EncodeYcc(CYcc&, unsigned int) calls
two CYcc::GetType() and two CYcc::GetScanMode() functions before
encoding JPEG. An earlier audit verified their ARM BL -> PLT symbols
and the local return-value paths into two JPEG enum fields. That does
NOT establish which CYcc object was passed as the receiver argument
in the ARM32 AAPCS r0 register.

At function entry (FW1.14/1.15 extracted mirror):
- 0x00034b28 is 0xe50b1064: STR r1,[fp,#-100]
  (method's incoming CYcc& argument, per its symbol signature).
- Before the first CYcc::GetType() at 0x00034bec,
  0x00034be8 is 0xe51b0064: LDR r0,[fp,#-100].

## New evidence audit

research/nx300m_fw114_ycc_getter_receiver_sources.py:
1. Pins the r1 entry-save opcode and exact stack offset.
2. Requires prior, independently verified imported getter call
   identities and four native return-to-branch paths.
3. Inspects the immediate r0 writer at all four getter callsites.
   A direct, unconditional LDR r0,[fp,#imm] reports that source
   frame offset. Other kinds of instruction are explicitly unknown.
4. Inventories direct ARM STR instructions to the fp-100 slot.
   More than one direct write prevents calling the slot singly
   sourced.
5. Emits source opcode, receiver slot, and bounded pre-call ARM words.
   The FW1.14/1.15 private CI prints the real extracted results.
6. Contains test cases for matching receiver slots, changed
   prologue, alternate source slot, unrelated r0 writer, additional
   direct stack writer and forged/malformed evidence.

## Actual FW1.14 and FW1.15 mirror ELF result

The offline native runner reported the same direct receiver source at
all four exact getter callsites on **both** firmware versions:

| Native getter | Call address | Final r0 instruction | Source offset |
|---|---|---|---|
| CYcc::GetType() #1 | 0x34bec | 0x34be8: e51b0064 | fp-100 |
| CYcc::GetType() #2 | 0x34c1c | 0x34c18: e51b0064 | fp-100 |
| CYcc::GetScanMode() #1 | 0x34c50 | 0x34c4c: e51b0064 | fp-100 |
| CYcc::GetScanMode() #2 | 0x34c80 | 0x34c7c: e51b0064 | fp-100 |

The only **direct** write to fp-100 found in the bounded 644-byte ARM
function was the known r1 parameter save at 0x34b28.
The CI now pins all four exact receiver opcodes and the one direct
incoming r1 store. A change is a hard failure, not an inferred
buffer identity.

All four getters therefore read the same *source frame slot* in
the examined native instruction stream. They likely receive the
method's input CYcc reference if that local slot is not indirectly
overwritten. This caveat matters: identical source slots do not
authenticate the live pointer value, establish that no nonlocal
writer changed it, or prove actual image memory lifecycle.

The synthetic tests also demonstrate rejection of altered R0
instructions, alternate frame offsets, additional direct slot writes,
changed prologue, unsupported R0 source and forged prior evidence.

## Interpretation boundary

Identical fp-relative source addresses are not proof of identical
runtime pointed-to objects. Indirect aliasing can modify the stack
slot, a native getter may have side effects, and physical pixel
memory may have separate lifetime and cache ownership.

The latest host Film Simulator, even with its detached snapshot,
does not run on an NX300M. Do not use this report as an injection
address, installation instruction, firmware authenticity proof or a
claim that JPEG chroma packing has been verified.

No proprietary binaries are committed, and native mirrored ELF
code is not executed. Camera firmware remains NO-GO.
