# NX300M FW1.14 — Actual `HalRegister(tDscHal*)` -> JPEG callback slot (2026-11-04)

**Result: new real ARM machine-code evidence, NOT another host JPEG/LUT test.**

## Source and limitations
- Read-only two firmware builds: NX300M internal FW1.14 and FW1.15 from a **third-party, unauthenticated** firmware archive. Temporary CI-only SLP/JAMCRC verified, UBI/UBIFS extracted and native ARM32 `libsif.so` inspected. Original camera or manufacturer provenance is **NOT** independently established.
- No firmware image or private ELF is committed, uploaded, loaded into a device, patched or flashed.

## Exact static pointer copy — the missing connection

```text
   DscJPEG::TaskMain()         0x0002ab9c
        | ARM BL -> PLT -> R_ARM_JUMP_SLOT    0x0002ad5c
        v
   DscJfif::JpegEncode(...)    0x00028a88
        |
        | [C++ this/r0] --STR--> [fp - 48]   0x00028a9c
        | [fp - 48]  --LDR-->  r3            0x00028b18
        | [r3 + 12]  --LDR-->  r6            0x00028b1c
        v
     BLX r6                                 0x00028c18
        |
        : Target function address not yet verified

   DscJfif::DscJfif()        0x0002868c
      MOV r2,#0                    0x000286e0
      STR r2,[r3,#12]             0x000286e4
        |
        v
    callback field initially NULL

   DscJfif::HalRegister(tDscHal*)   0x00028828
       ARM copies from the tDscHal* pointer (C++ argument/r1)
       into the DscJfif instance (this/r0):
       tDscHal + 0   -> DscJfif + 4     STR 0x00028854
       tDscHal + 4   -> DscJfif + 8     STR 0x00028864
       tDscHal + 8   -> DscJfif + 12    STR 0x00028874
                                    |
                          read by JpegEncode as r6
                                    |
                                  BLX r6
```

This resolves the **static pointer-layout mapping** between native `HalRegister` and `JpegEncode`. It does **NOT** prove that the runtime instance executed `HalRegister`, or that its third callback table field points to `DscJfifHal::Encode` in the live camera. The camera's native JPEG ABI, DMA lifetime and MakerNotes still require independent proof.

## Relevant independent ELF relocation

FW1.14 `libsif.so` contains a separate `R_ARM_GLOB_DAT` entry for `DscJfifHal::Encode` at GOT `0x0006ce98`, and that function is located at symbol address `0x00029830`. However, simply having the symbol and GOT entry in the same ELF **does not yet prove** that the `tDscHal +8` callback field is initialized with that address. Establishing its writer and the passed table-instance identity remains the next discrete task.

### Implemented real-evidence checks

- `research/nx300m_fw114_jfif_r6_arg_provenance.py`: decode FW1.14 and FW1.15 per-version actual `DscJfif::JpegEncode` first-object pointer stack save, r6 field load and BLX; search actual constructor and named Jfif methods for member +12 writes; verify the constructor writes an immediate **zero**; and require exact `HalRegister` three-member transfer from `tDscHal[0,4,8]` to `DscJfif[4,8,12]`.
- `research/test_nx300m_fw114_jfif_r6_arg_provenance.py`: synthesized ARM opcode negative tests, including swapped callbacks/stack arguments and absent callback field.
- `research/nx300m_fw114_native_elf_diff.py`: feed privately extracted actual version-specific libsif ELFs into the new disassembly.
- `.github/workflows/nx300m-fw114-native-elf-diff.yml`: explicit fail-closed checks against real ARM symbols, addresses and relocation evidence; the true callback address and camera flash remain **NO-GO**.

## Next real reverse-engineering task

**Find the code that initializes `tDscHal[+8]`**, confirm it is `DscJfifHal::Encode` on a real FW1.14 native capture path, and identify the actual still-shutter ownership/lifetime of the buffer passed to the native HAL JPEG encoder. Then design a reversible camera-side adapter under an independently proven full-brick recovery procedure.

**Camera firmware modification, on-device 20.6MP output and final integration are NOT complete.**
