# NX300M FW1.14 — Y/C memory pool and temporary CYcc lifetime: native ARM evidence

**Date:** 2026-11-05. **Source:** third-party unauthenticated FW1.14 and FW1.15 mirror archives unpacked privately in CI (read-only SLP/JAMCRC/UBI→ELF32). Do not equate static code with runtime camera ownership. No firmware has been flashed, modified or executed on a camera.

## Newly confirmed branch: Type 1 only

The native 644-byte `CMmDeviceDriver::EncodeYcc(CYcc&, unsigned)` function starts at `0x00034b18`. It calls `CYcc::GetType` at `0x34b34`, compares the returned value with **1** at `0x34b3c`, and branches on equality via the result guard. At `0x34b50`, `BEQ 0x34be0` **skips** the temporary-pool/resize block when the test **GetType == 1 is false**. Therefore not every JPEG encode executes the same buffer path.

For Type 1, the ARM block does:

```text
CYcc::GetType @ 0x34b34 ── GetType == 1?
          │
       yes│                  no ──────────┐
          ▼                               │
CMemoryPool::GetInstance @ 0x34b64        │
MOV r1,#2               @ 0x34b70        │
CMemoryPool::GetAddr(2) @ 0x34b74        │
  └─ pool object [+8] pointer             │
CYcc(temp) constructor  @ 0x34b8c        │
CMmDeviceDriver::ResizeImage @ 0x34bac   │
  └─ ipcs_one/several_resize              │
CYcc descriptor copy    @ 0x34bb0–0x34bd0
CYcc(temp) destructor   @ 0x34bdc        │
           └──────────────────────────────┤
                                         ▼
                                  0x34be0 continue
                                    │
                                    ▼
                      CYcc Y0/Y1/C0/C1 getters
                                    │
                                    ▼
                      DscImage::EncodeYCC @ 0x34d78
```

Do **not** infer that this is a safe copy of full sensor pixel data. The descriptor is copied from the temporary `CYcc` to a caller-provided `CYcc` object using ARM load/store instructions. The actual image memory is addressed via a pool pointer. There is no independently demonstrated ownership/refcount, pool size, lifetime, stride, cache coherency, color matrix, or on-device callback history.

## Exact real provider methods

| Private ELF | Native function | ARM start / size | Verified fact |
|---|---|---|---|
| `libmm-photo.so` | `CMemoryPool::GetInstance()` | `0x352bc` / 52 B | Reads a global pointer through PC-relative PIC/GOT sequence, no native direct alloc call in method |
| `libmm-photo.so` | `CMemoryPool::GetAddr(eMemMode)` | `0x3534c` / 172 B | For mode **2**, `CMP r3,#2` at `0x3539c` followed by `LDR r3,[r3,#8]` at `0x353a8`, returns value via `MOV r0,r3` at `0x353dc` |
| `libmm-type.so` | `CYcc::CYcc(sImgSize,unsigned long)` | `0x20b8` / 544 B | Initializes Y/C image descriptor and calls `CYcc::VerifyBuffer`; no claim of pixel-memory allocation |
| `libmm-type.so` | `CYcc::~CYcc()` | `0x2a00` / **36 B** | **Nine ARM instructions**, only stack save/load, return; **no ARM direct BL, BLX or body heap-free call** |
| `libmm-type.so` | `CYcc::GetType()` | `0x31d8` / 40 B | Reads descriptor type field at object offset `+0x20` |

The nine-instruction destructor is directly analyzed and also checked byte-by-byte by the new CI gate. Its lack of deallocation **does not imply** the underlying memory-pool slot remains unchanged after camera JPEG submission. Buffer reuse can occur elsewhere in another thread or on a later capture.

## Actual static branch caveats

- The `CYcc` destructor at `0x34bdc` is in the Type 1 resize path before the final native JPEG call.
- The second imported destructor at `0x34d94` is in an out-of-line block after the normal return sequence at `0x34d84–0x34d88`. It must **not** be described as a universally executed post-JPEG free; it is consistent with cleanup code. Full unwind-edge analysis is still outside the evidence.
- The typed Y/C input is either passed through or changed through a resize/pool-backed descriptor. Exactly which runtime frames take each branch and when the shared pool slot is rewritten remains **unknown**.

## Implementation and checks

- `research/nx300m_fw114_photo_buffer_lifetime.py` — bounded exact ARM branch and caller-code windows, including the Type 1 condition, `CMemoryPool::GetAddr(2)`, `ResizeImage`, temporary `CYcc` construction/destruction and JPEG call.
- `research/nx300m_fw114_cycc_provider_probe.py` — securely resolve actual libraries in the private UBI tree and inspect defined native method symbol/body SHA, direct/imported calls, indirect branches and bounded raw ARM opcode evidence. Strict validation of `CMemoryPool::GetAddr(2)` and the CYcc destructor.
- `research/test_nx300m_fw114_photo_buffer_lifetime.py`, `research/test_nx300m_fw114_cycc_provider_probe.py` — synthetic branch/alias/symlink and corrupted-opcode guard cases.
- `research/nx300m_fw114_native_elf_diff.py` and `.github/workflows/nx300m-fw114-native-elf-diff.yml` — independently run **real** FW1.14 and FW1.15 ELF inspections in ephemeral CI; require both proven code paths while retaining false device-ownership/flash flags.

## What must happen next

1. Locate `CMemoryPool` construction and the **writer/reuser of pool slot `+8`** in actual `libmm-photo.so`. Identify buffer size, alignment, synchronization and overwrite timing. A static 36-byte `CYcc` destructor alone cannot certify safety.
2. Obtain owner-authorized **physical** Tizen read-only, same-stage capture observations of image descriptors and pool reuse timing, with all sensitive images/private calibration kept off GitHub.
3. Only after proving the actual memory lifetime/format, design a copy-owned Y/C adapter that runs the existing standalone LUT film engine and returns into the native JPEG pipeline without changing RAW, EXIF, MakerNotes or live view.
4. Authenticate original Samsung FW1.14, establish full-brick recovery and calibration preservation, then independently test real 20.6MP JPEG/RAW/latency on the camera.

**State: static buffer-control evidence improved; native Film Simulator integration remains NOT IMPLEMENTED. Firmware installation and patch remain NO-GO.**
