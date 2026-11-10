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
