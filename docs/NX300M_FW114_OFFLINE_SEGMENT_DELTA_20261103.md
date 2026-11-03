# NX300M FW 1.14 / 1.15 offline static region diff — NO FLASH

**Scope:** compare two exact externally supplied local SLP BIN/ZIP files. This is an *integrity and static-difference* tool, not a firmware compatibility tester, patcher or installer.

## Source inspection (2026-11-03)

- Official Samsung support model records (for NX300M) currently list the **1.15** upgrade archive. Example: https://www.samsung.com/uk/support/model/EV-NX300MBQUSE/ .
- Historical catalog (third-party, **not authenticated payload**): 2014-10-13, `NX300M_FW_v1.14.zip`, ~233.7 MB: https://drivers.softpedia.com/get/SCANNER-Digital-CAMERA-WEBCAM/Samsung/Samsung-NX300M-Camera-Firmware-114.shtml .
- Prior modified MFW **1.1** is an SLP image whose internal Samsung firmware version is **1.15**, not 1.14. This was reconfirmed by reading the local SLP header. It can be used only as an **explicitly marked modified 1.15 reference**.
- **No authenticated unmodified Samsung FW 1.14 file was available** to this investigation, and a file listing is not evidence of a valid binary. **No actual 1.14/1.15 binary differences were measured this turn.**

## Run with real files; read-only

```sh
python3 research/nx300m_fw114_binary_delta.py \
    --fw114 "/path/to/independently-acquired/NX300M_FW_v1.14.zip" \
    --reference115 "/path/to/known-reference/nx300m_mfw_1.1.bin" \
    --expect-fw114-archive-sha256 "<independent-vendor-supplied-64-hex-digest>"
```

Use fingerprints from a separate trusted source when available. Never copy a digest computed from the same candidate into the trusted field and present it as independent verification.

The tool **refuses** mislabeled 1.15 firmware used as a 1.14 target; checks ZIP entry/path/size/compression ratio, five SLP image JAMCRC32 values and pcache JAMCRC32, decoded payload SHA-256, and file stability. Each image/pcache receives **streamed SHA-256**. The comparison prints region sizes and SHA-256 equality only, never raw proprietary bytes or guessed ARM addresses.

It performs no device I/O, firmware flashing, image extraction, calibration writes, or destructive file operations. Synthetic tests create only temporary small research fixtures.

## GO / NO-GO technical diagram

```text
[1.14 archive listing] -- historical evidence only --> [NO hardware GO]
           |
           v
[Actual stock 1.14 ZIP/BIN + independent vendor provenance]
           |
           v
[Read-only SLP/JAMCRC/ZIP/SHA-256/region delta] -- missing/mismatch --> [REJECT]
           |
           v
[Version-specific ELF/native ABI, ISP buffer ownership/copy,
 source-of-truth Y/C format and camera RAM examination]
           |
           v
[Proven complete brick recovery + calibration preservation]
           |
           v
[Separately reviewed reversible on-device design]  [NOT IMPLEMENTED]
```

**Even a perfect SHA match only proves agreement with the provided digest; it does not prove Samsung authenticity, camera compatibility, buffer ownership, exact address compatibility, repairability or permission to flash.** The tool intentionally reports those fields false.

Source:
- `research/nx300m_slp_firmware_integrity.py`
- `research/nx300m_fw114_binary_delta.py`
- `research/test_nx300m_fw114_binary_delta.py`

## Archive availability discovery and isolated CI attempt (2026-11-03)

The third-party Samsung NX Files archive exposes **both**
`NX300M_FW_v1.14.zip` and `NX300M_FW_v1.15.zip` at
`https://nxfiles.ydns.eu/files/NX300M/Firmware/`. This is a **non-official**
mirror with no verified manufacturer's signing or independent hash ledger.
The historical Softpedia listing independently confirms that firmware v1.14
was distributed, **not** that the mirror bytes are official or identical.

A new GitHub Actions workflow
`.github/workflows/nx300m-unofficial-firmware-audit.yml` performs a
single isolated **read-only investigation** of two pinned archive URLs:

1. Test the acquisition, size, URL, redirect and ZIP-safety logic with
   network-free synthetic fixtures.
2. Download at most 300 MiB per ZIP into mode-0700 runner temp storage; reject
   unsafe redirects, corrupt/truncated/oversized data and same-path overwrite.
3. Parse SLP version/model/5 image JAMCRC/pcache JAMCRC plus SHA-256 with
   `nx300m_slp_firmware_integrity.py`. Require v1.14 and v1.15 internally.
4. Compare image-region SHA-256 and sizes using
   `nx300m_fw114_binary_delta.py`. Print factual hashes and changed region
   counts only, with manufacturer provenance and installability marked false.
5. Delete temporary copies. **Never** upload a firmware or binary artifact to
   GitHub, the chat session or an archive.

CI can succeed only when it truly downloads/validates both files. If the
unofficial mirror blocks download, the workflow **fails** rather than
fabricating a successful real-firmware comparison.

**Camera firmware installation and native ABI assumptions remain NO-GO.**

## ACTUAL retrieved mirror-archive 1.14 vs 1.15 comparison (2026-11-03)

Source: isolated CI [run 41587787130](https://github.com/blodburn/new_nx300m/actions/runs/41587787130).
**Files were really downloaded, checked and removed, NOT committed.**

| Source | 1.14 | 1.15 |
|---|---|---|
| ZIP bytes | 245,027,217 | 245,016,220 |
| ZIP SHA-256 | `dccb51ae1497b95123eb9f35035d90e53ab793b3d98a535747d1d3653c89cf05` | `ccd3b357f85b4d50b583ba874504dd896f4fff1d5d1b41e7384ac78f2a4e2df0` |
| Decoded BIN bytes | 331,140,312 | 331,140,200 |
| BIN SHA-256 | `173865f6da4e062b7293031eb0c49f983b9cd73b59fce3afa30787045db6cba4` | `75ededdc1e191ea3cdf8fb1201faced001d47b164224601a21150f75f8f7922f` |
| Internal header | NX300M, 1.14 | NX300M, 1.15 |
| 5 image JAMCRC + pcache | PASS | PASS |

| SLP section | 1.14 bytes | 1.15 bytes | SHA-256 comparison |
|---|---:|---:|---|
| Image 0 (vImage, SLP convention) | 5,193,616 | 5,193,616 | Identical |
| Image 1 (D4_IPL, SLP convention) | 7,652 | 7,652 | Identical |
| Image 2 (D4_PNLBL, SLP convention) | 63,580 | 63,580 | Identical |
| Image 3 (uImage, SLP convention) | 2,745,960 | 2,745,848 | **Different** |
| Image 4 (platform.img, SLP convention) | 323,092,480 | 323,092,480 | **Different** |
| pcache | 36,864 | 36,864 | **Different** |

The changed uImage and platform image make FW1.15 native offsets,
ISR/ISP assumptions and JPEG hook ABI **NON-PORTABLE by default**.
Only version-specific ELF/static analysis and same-stage read-only camera
captures could establish a 1.14 contract. This is not a signed Samsung
vendor-source verification, only a fact about internally valid mirror copies.

The initial workflow labeled a self-computed download digest as if externally
supplied. A follow-up change explicitly removed that label: the digest proves
consistency among reads, **not independent trusted manufacturer provenance**.

## Native FW1.14 UBI / ELF static comparison (2026-11-03)

The two actual mirror archives were previously validated with the SLP v1
five-image JAMCRC + pcache checks. Image 4, the **platform UBI** filesystem,
was different between FW1.14 and FW1.15, even though both are the same size.
This means **never transplant old 1.15 numerical ARM callsite offsets**.

A new host-only pipeline `research/nx300m_fw114_native_elf_diff.py`:

- Opens each existing private ZIP and validates the internal SLP model/version,
  region CRC and SHA-256 before streaming only **platform.img** to mode-0600
  ephemeral storage; never exposes the firmware as an upload/repository artifact.
- Checks sampled UBI EC headers at eraseblock boundaries, PEB 131072 bytes,
  VID offset 2048, data offset 4096, as documented for the Samsung NX family.
- Calls pinned userspace `ubi-reader==0.8.16` **without mount, chroot, device,
  root permissions or firmware code execution**; extracts to disposable temp.
- Inspects ARM32 ELF files whose names match Capture/ISP/JPEG-related
  libraries/app; reads dynamic symbols only via readelf and demangles symbols.
- Compares byte hashes, lengths and same-named native dynamic-symbol values
  across the two versions. A changed file or symbol is **negative evidence**
  for reusing 1.15 offsets. It is NOT a complete verified 1.14 calling contract.
- Synthetic tests include version mismatch, SLP CRC, NAND header geometry,
  rejected symlink/writable output roots, ELF SHA/address difference and
  conservative metadata-only ABI gates.

Action: `.github/workflows/nx300m-fw114-native-elf-diff.yml`.
Run artifact policy: **no Samsung firmware, ELF or generated derivative
uploaded or committed**. Logs may contain short symbol/path/hash metadata.
The source is an unofficial mirror and remains untrusted for authenticity.

Real FW1.14 camera integration **remains NO-GO** until version-specific
callsite/dependency, sensor Y/C data ownership, hardware RAM and full recovery
are established independently.

## REAL 1.14/1.15 UBI → camera ELF inspection, run 41603973944

**Actual isolated CI passed**, from untrusted mirror archives, full disposable
UBI/UBIFS extraction. Both had 2,465 128-KiB physical eraseblocks.
Among **11 selected same-named ARM32 camera-related ELF files**, 10 were
byte-for-byte equal. The different file was **`libsif.so`** (both 420,844 bytes):

- `libmm-photo.so`: byte-identical SHA-256
  `69bc5d912ceb8c762afb27b3b410a048c1606852846b89b3c70b16714697ecba`.
- `libcapture-fw-slpcam-nx300.so`: byte-identical (4,791,660 bytes).
- `libcapture-fw-plat.so`: byte-identical (35,648 bytes).
- `libsif.so` v1.14 SHA-256:
  `280472a65f6b301f1c6bf21f6c73e0cc0f17609fc193a2d9ba8bc75c30b3fe72`.
- `libsif.so` v1.15 SHA-256:
  `c50eb4448fc58fd8b24721dca30b15169bf95d28295c846eb0bc9cd9c32f6ff8`.

Extracted actual dynamic-symbol evidence: `DscImage::SaveExifImage` is
0x0005b9b4 in v1.14, versus 0x0005b8ac in v1.15 (**delta +0x108**).
`DscImage::CopyExifInfo` is 0x00059900 versus 0x000597f8.
`DscImage::GetExifImageInfo` is 0x00057320 versus 0x00057218.
No firmware or ELF artifact was uploaded; sources are temporary runner data.

**Next verification** (`nx300m_fw114_function_proofs.py`): compare exact
function bytes by each file's own ARM PT_LOAD mapping for the JPEG parser,
JpegEncode, EncodeYcc, EXIF and MakerNotes. Test the previous 1.15 exact
JPEG SOF 4:2:2/4:2:0 ARM opcode signature against 1.14 independently.
This verifies specific instructions only, not native runtime ABI, DMA
ownership, camera RAM, or recovery. Installation remains **NO-GO**.

## REAL FW1.14 native JPEG function-body comparison (run 41604709782)

Static ARM32 PT_LOAD file-backed function-body SHA-256 comparisons from the
same temporary, version-validated UBI/UBIFS files:

| Native ELF + function | Version 1.14 address | Version 1.15 address | Code-body SHA equal |
|---|---|---|---|
| `libmm-photo.so` `CMmDeviceDriver::EncodeYcc(CYcc&, unsigned int)` | 0x00034b18 | 0x00034b18 | **YES** (644 bytes) |
| `libsif.so` `DscJfifHal::Parse` | 0x00029084 | 0x00029084 | **NO** (1216 bytes) |
| `libsif.so` `DscJfifHal::Encode` | 0x00029830 | 0x00029830 | **NO** (936 bytes) |
| `libsif.so` `DscJfif::JpegEncode` | 0x00028a88 | 0x00028a88 | **NO** (456 bytes) |
| `libsif.so` `DscImage::CopyExifInfo` | 0x00059900 | 0x000597f8 | **NO** (772 bytes) |
| `libsif.so` `DscImage::GetExifImageInfo` | 0x00057320 | 0x00057218 | **NO** (192 bytes) |
| `libsif.so` `DscImage::SaveExifImage` | 0x0005b9b4 | 0x0005b8ac | **NO** (1212 bytes) |

The earlier FW1.15 JPG SOF sampling branch **exactly matched 12 of 12**
old-reference ARM instruction words in actual mirror FW1.14 `libsif.so`,
including 0x21 (4:2:2) and 0x22 (4:2:0) branches. **This is a local
instruction observation, not evidence that JPEG function bodies are equal:
they are not.** Do not reuse 1.15 function sizes/addresses/patches without
version-specific proof and independently verified hardware recovery.

**Completion gates still open**: trusted manufacturer-source identity,
Picture Wizard + capture callback dynamic paths on actual FW1.14,
full JPEG encoder/EXIF/MakerNotes compatibility, real live Y/C buffer
shape and ownership, camera RAM and save latency, safe firmware roll-back
and full-brick recovery. No real camera was accessed.
