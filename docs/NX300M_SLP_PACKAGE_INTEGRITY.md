# NX300M SLP firmware integrity gate (read-only)

**Current real target: Samsung NX300M firmware 1.14. Not yet obtained and not analyzed. Do not flash or install firmware.**

## Important historical version correction

Existing private research file `nx300m/original/nx300m_mfw_1.1.bin` was inspected through its **actual SLP header**, rather than deriving camera firmware version from its filename. The internal fields were:

| Field | Verified extracted metadata |
|---|---|
| SLP magic | `SLP\0` |
| Camera model | `NX300M` |
| Embedded Samsung firmware version | **`1.15`**, NOT `1.1` |
| Internal release identifier | `NX300MGLUANL1` |
| BIN size | **333,237,352 bytes** |
| Contiguous image sections | **5 / 5 JAMCRC verified** |
| Extra pcache section | **JAMCRC verified** |

**MFW 1.1 is the modified-firmware research release identifier, not the Samsung firmware 1.1 version.** Previous notes describing these ELF libraries as originating from a vendor `1.1` image must be understood as the **MFW 1.1 research set built on internal Samsung 1.15**, unless separate provenance proves otherwise. This does not establish unmodified Samsung 1.15 binaries, and no native ABI equivalence to the user's installed **1.14** is established.

## New offline verifier

`research/nx300m_slp_firmware_integrity.py` is deliberately read-only and accepts an already present local `.bin` or `.zip`. It never invokes firmware update services or executes the image, nor does it extract proprietary files to disk.

```sh
# Inspection of the existing, research-modified 1.15 SLP reference:
python3 research/nx300m_slp_firmware_integrity.py \
  --input /path/to/private/nx300m_mfw_1.1.bin --expect-version 1.15

# Only AFTER separate authorized acquisition of original 1.14 ZIP:
python3 research/nx300m_slp_firmware_integrity.py \
  --input /path/to/private/NX300M_FW_v1.14.zip --expect-version 1.14
```

Checks: internal SLP model and version, five contiguous segment size/offset descriptors, five JAMCRC checks, pcache pointer/size/JAMCRC, exact total file length, streamed SHA-256 of the actual uncompressed BIN, and ZIP member integrity. The ZIP path requires one `.bin` member and blocks traversal paths, nested symlinks, encryption, duplicate BIN candidates and suspicious compressed/uncompressed ratios. Processing is streaming with at most a 1MiB data chunk; it does not require a 333MB in-memory blob.

The script prints JSON evidence only, never firmware bytes. Its results set `manufacturer_authenticity_proven=false`, `camera_flash_safe=false`, and `picture_wizard_abi_114_verified=false`, **even when all CRCs match**. CRC and SHA-256 of one file do not independently establish a trustworthy manufacturer-provided image or the ability to recover a bricked NX300M.

## After the original 1.14 archive can be obtained

1. Verify the original ZIP's source and chain of custody separately. Prefer original manufacturer hashes, when actually available; do not invent them.
2. Run this verifier. Record the BIN's embedded exact model/version, SHA-256 and all six JAMCRC results.
3. Extract or analyze the image only offline with a reviewed method; do not execute it. Determine the exact `libcapture-fw-slpcam-nx300.so` from that **1.14** image and compare it using `research/nx300m_picture_wizard_abi_gate.py`.
4. Verify ELF/loader/EFL/IPC and full-brick recovery independently before any physical-camera experiments. **No flash procedure is part of this project.**

## Testing

`python3 research/test_nx300m_slp_firmware_integrity.py` uses nine synthetic test cases; no proprietary bytes are packaged in test fixtures. The existing private 333,237,352-byte MFW reference was also streamed through this integrity checker and all six JAMCRC checks passed. It remains a modified image and **not the missing original 1.14**.
