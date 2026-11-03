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
