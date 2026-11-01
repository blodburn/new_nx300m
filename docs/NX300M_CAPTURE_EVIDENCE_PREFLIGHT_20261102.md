# NX300M — copied capture evidence preflight (host-only)

This command checks **synthetic or user-authorized copied** same-stage
Y, interleaved C and RGB888 files before any color-model hypothesis analysis.
It never reads camera devices, DMA addresses, proprietary firmware, raw capture
APIs or original calibration, and it does not write to its inputs.

## Input directory

A private local directory contains `capture.json`, `y.bin`,
`c.bin`, and `rgb.bin`. All three binary planes must be regular files in
that directory (not symlinks). The JSON document is:

```json
{
  "format": "NX300M_HOST420_EVIDENCE_V1",
  "camera_model": "NX300M",
  "firmware_version": "1.14",
  "same_stage_copy_declared": true,
  "width": 4,
  "height": 4,
  "planes": {
    "y": {"file": "y.bin", "stride": 8, "bytes": 32, "sha256": "64-hex-character-sha256"},
    "c": {"file": "c.bin", "stride": 8, "bytes": 16, "sha256": "64-hex-character-sha256"},
    "rgb": {"file": "rgb.bin", "stride": 16, "bytes": 64, "sha256": "64-hex-character-sha256"}
  }
}
```

Replace placeholder digests with actual 64-digit independent hashes of each
stored file. The 4x4 geometry in this example is **not a verified camera
format**. All dimensions must be even. Each plane's length must equal the
declared stride times the corresponding 4:2:0 row count. All plane paths
are simple filenames and must be distinct.

```sh
python3 research/nx300m_capture_manifest_gate.py --bundle-dir /private/copied-evidence
python3 research/test_nx300m_capture_manifest_gate.py
```

Return status **0** means only that file integrity and declared geometry are
consistent. Status **2** means reject. This tool does **not** prove that the
frames are genuinely camera-origin, that they came from the same processing
stage, that CbCr order or conversion matrix are correct, or that FW 1.14
native ABI/DMA/JPEG/EXIF handling has been established.

All returns explicitly report `same_stage_verified=false`,
`native_camera_layout_verified=false`, `camera_abi_verified=false`,
`firmware_flash_safe=false`. The manually declared firmware string is
not vendor provenance proof. No camera firmware should be flashed.
