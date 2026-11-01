# NX300M still-main address mode 7: verified static ARM boundary

**Reference:** Private older modified MFW 1.1 / embedded Samsung SLP **1.15** `libcapture-fw-slpcam-nx300.so`. The owner reports stock **NX300M 1.14**, but that original firmware has **not** been obtained/authenticated. No runtime camera code, pixel addresses, patches, or flash images are produced.

## Native still-main chain, with source-supported identities

```text
CRecipeStillSetting::GetMainImage(CCapImage*)
     |
     +-- CCapImage::setImageFormat(2)
     +-- CCapImage::setYccFormat(1)
     +-- CCapImage::setYccPackType(0)
     +-- CCapImage::getBuffer()
            |
            +-- CCapBuffer::setAddrType(7)
                     |
                     v
GetAddrFromCapImage(CCapImage*, Y0&, Y1&, C0&, C1&, ...)
     |
     +-- getBuffer() -> getAddressType()
     +-- selector <= 7; mode 7 jumps to verified code block
             |
             +-- Y0 from input / local address
             +-- Y1: base + stride math
             +-- C0 from separate input / local address
             +-- C1: base + stride math
             +-- conditional missing-address fallback
             |
             v
          OPAQUE Y/C address tuple
             |
             v
CYcc getter calls -> DscImage::EncodeYCC (previous separate ELF proof)
             |
             v
    Actual camera JPEG from Film Simulator: NOT VERIFIED
```

**Evidence level:** The new read-only `nx300m_native_still_mode7_boundary_audit.py` verifies four exact enum immediate instructions in the still-main recipe, resolves **nine** native setter/getter calls by ARM BL target → PLT stub → GOT `R_ARM_JUMP_SLOT` relocation, validates the address-mode computed branch table up to 7, and checks precise instructions inside the mode-7 branch that form Y1 and C1 offsets and handle null pointers.

The previously published `nx300m_native_jpeg_abi_boundary_audit.py` independently confirms `CYcc::GetY0/Y1/C0/C1`, Width/Height/Stride and `DscImage::EncodeYCC` within the **modified 1.15 reference**. Neither inspection proves that the capture descriptor is allocated the same way, or that any film-processed bytes reach the native codec.

## Exact conclusions and limits

| Question | Result |
|---|---|
| Main-image setting calls | Image format **2**, YCC format **1**, pack **0**, address mode **7** |
| Mode 7 selector | Computed ARM branch range 0..7, reference target checked |
| Y/C address calculations | Separate Y0/Y1/C0/C1 outputs with stride arithmetic and conditional fallback |
| Actual Y/C pixel layout | **UNKNOWN** — no assertion of NV12/NV21, NV16/NV61 or CbCr order |
| Actual camera 1.14 state | **UNKNOWN** — 1.15 offsets cannot be reused |
| Physical capture, ISP and JPEG encoding with look | **NOT VERIFIED** |

## Reproduce without hardware access

```sh
python3 research/nx300m_native_still_mode7_boundary_audit.py \
    --capture-lib /private/reference/libcapture-fw-slpcam-nx300.so --summary
python3 research/test_nx300m_native_still_mode7_boundary_audit.py
make test
```

Eight synthetic fixtures cover the expected mode-7 branch and stride calculations, modified guard, invalid jump target, changed pointer arithmetic, wrong enum constants, wrong/missing PLT symbols, and invalid/symlink ELF rejection. These tests **reject changes**, rather than silently treating another firmware as compatible.

## Next implementation requirements

1. Authenticate original **NX300M 1.14** and independently locate native capture/camera-encoder equivalents; compare code and signatures without reusing modified 1.15 offsets.
2. Establish live **read-only** measurements of Y0/Y1/C0/C1 plane layout, stride, chroma order/siting, ownership and lifetime. Never directly reinterpret a DMA pointer as RGB or host 4:2:0.
3. Build a verified owned-copy boundary to run the **independent per-pixel Film Simulator** then native JPEG, retaining RAW and Exif/MakerNotes integrity.
4. Before a flashable build, independently prove complete camera recovery and preservation of calibration data.

**Picture Wizard remains a film-profile selector only; altering its settings without pixel processing cannot pass acceptance.**
