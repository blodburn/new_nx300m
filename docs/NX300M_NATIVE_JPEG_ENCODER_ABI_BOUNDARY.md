# NX300M: native JPEG encoder ABI boundary — offline evidence

**Source:** modified MFW 1.1 / underlying Samsung SLP 1.15 research files, NOT the camera owner's authenticated original 1.14 firmware. No proprietary ELF is distributed or executed.

## Verified machine-code chain

```text
CMmDeviceDriver::EncodeYcc(CYcc&, unsigned int)
       |
       +--> CYcc::GetY0()
       +--> CYcc::GetY1()
       +--> CYcc::GetC0()
       +--> CYcc::GetC1()
       +--> CYcc::GetWidth()
       +--> CYcc::GetHeight()
       +--> CYcc::GetStride()
       |
       +--> DscImage::EncodeYCC(...)
                  |
                  +--> native JPG encoder (actual runtime not observed)
```

For every one of these **eight direct ARM BL instructions**, the read-only analyzer resolves the BL target, decodes the three-instruction ARM PLT stub, extracts the GOT address and matches that address to a verified **R_ARM_JUMP_SLOT relocation** symbol. Thus the calls are verified by machine-code instruction and ELF relocation identity rather than by unrelated import lists or assumed PLT indices.

The JPEG parser in the separate 1.15 research `libsif.so` has exact ARM branch signatures for the SOF component sampling factors **0x21 → eImgYCCType 0 (4:2:2)** and **0x22 → eImgYCCType 1 (4:2:0)**. These are JPEG sampling indicators, not a certificate for the physical camera Y/C memory layout.

## Connection to independent Film Simulator

```text
Picture Wizard → chooses film look ID only
                       |
Capture native Y/C descriptor (1.14: UNKNOWN)
                       |
            non-destructive buffer copy needed
                       v
Host-owned Y/C → independent film pixel transform → HOST JPEG  [PASS]
                       |
Native processed buffer → DscImage::EncodeYCC               [NOT VERIFIED]
                       |
Camera JPEG with selected look                           [NOT VERIFIED]
```

The existing host-only Y/C 4:2:0 bridge proves distinct JPEG file outputs after processing pixels and leaving original Y/C bytes unchanged. The native JPEG ABI audit does not install a hook or prove a camera encoder can accept that host-owned buffer.

## Offline reproduction

```sh
python3 research/nx300m_native_jpeg_abi_boundary_audit.py \
  --mm-photo /private/reference/libmm-photo.so \
  --sif /private/reference/libsif.so
python3 research/test_nx300m_native_jpeg_abi_boundary_audit.py
make test
```

The new Python analyzer has eight synthetic fixture tests, covering ARM immediate decoding, correct PLT/GOT mapping, wrong call targets, missing relocations, altered PLT instructions, readelf relocation parsing, changed JPEG SOF branches, and non-ELF/symlink rejection.

## Critical remaining gates

1. Authenticate the ORIGINAL NX300M **1.14** firmware, independently inspect its three library APIs, and do not reuse 1.15 offsets.
2. Determine the actual camera Y0/Y1/C0/C1 layout, CbCr/CrCb order, YCC type, width/stride bounds, DMA ownership and lifetime.
3. Verify an on-device-safe image copy that keeps RAW unaffected, processed pixels before the native JPEG encode operation, and Exif/MakerNotes integrity.
4. Establish independent full-brick recovery and calibration preservation before any physical firmware modification.

**Result:** static encoder ABI symbol/PLT/relocation evidence PASS on modified 1.15; real-camera Film Simulator JPEG result NOT VERIFIED.
