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
