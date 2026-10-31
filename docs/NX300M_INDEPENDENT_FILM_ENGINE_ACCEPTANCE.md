# NX300M Film Simulator: Independent image processing acceptance gate

This project must **not** be considered complete if it only changes a Samsung Picture Wizard menu value. Picture Wizard can select a film-look ID; an **independent image-pixel processing engine** must change pixel values before a single JPG is encoded.

## Required processing architecture

```text
MENU (selection only)
    Film Simulator → ID (Fuji/Leica study preset)
                               |
                               v
CAPTURE (needs native NX300M 1.14 validation)
    Raw sensor/ISP data (unchanged original) 
                               |
                               v
    Verified separate image buffer, NOT Samsung DMA in place
                               |
                               v
IMAGE ENGINE (host-only demonstrator now implemented)
    Calibration / demosaic → 16-bit WB and exposure
          → highlight shoulder → film color LUT / tone
          → per-look local contrast / grain
                               |
                               v
OUTPUT
    One baseline JPEG 4:2:0 host encode → create-only file transaction
    Optional RAW stays byte-identical / never processed by a film LUT
```

This pipeline already exists in host research components `nx300m_bayer_prejpeg.c`, `nx300m_linear_prejpeg.c`, `nx300m_look_builder.c`, `nx300m_camera_style_response.c` and `nx300m_host_jpeg_sink.c`. No actual Samsung 1.14 camera capture hook, proprietary raw decoder, on-camera encoder ABI, memory mapping, color science calibration or confirmed recovery exists. Its use on an NX300M device must remain blocked until those items are demonstrated.

## NEW end-to-end **pixel** acceptance test

Run:

```sh
make film-proof
```

The proof deliberately uses **the same synthetic, host-owned Bayer input** for three preset IDs: `101` (Fuji Velvia Study), `105` (Fuji ETERNA Study) and `204` (Leica Monochrome HC Study). It executes the real host pixel transforms; validates different RGB outputs; compresses each output to a **real baseline JPEG 4:2:0** using the host encoder; requires three distinct JPEG hashes; checks the mono rendition's channel neutrality; and verifies the original Bayer buffer never changes.

The command preserves three JPG samples in `outputs/nx_film_e2e_<pid>_<id>.jpg` for visual review. The executable can also run without `--keep` as an automatic sanitizer test, in which case it deletes its generated images. It does not publish false camera EXIF/MakerNotes.

Current deterministic proof on a 37x29 synthetic sample:

| Render | JPEG bytes | |
|---|---:|---|
| Film 101 (Fuji Velvia study) | 1,393 | Actual pixel-processed JPG |
| Film 105 (Fuji ETERNA study) | 1,262 | Actual pixel-processed JPG |
| Film 204 (Leica monochrome HC study) | 1,197 | Actual pixel-processed JPG |

RGB absolute-difference sums for that exact input: 101 vs 105 = **21,165**; 101 vs 204 = **31,379**; 105 vs 204 = **21,200**. These are **functional differentiation** measurements, not perceptual similarity or manufacturer image-quality certification.

## Pass/fail gates

- **PASS, host:** actual per-pixel transform of host-owned Bayer-derived data, distinct JPEG bitstreams, RAW unchanged, no extra strength sliders.
- **NOT VERIFIED:** Fujifilm X100VI or Leica Q3 scientific color matching; no manufacturer proprietary image-processing algorithms were recovered.
- **NOT VERIFIED:** original NX300M **1.14** capture memory, ISP, color calibration and embedded encoder integration.
- **REJECT:** a release that merely writes Samsung Picture Wizard setting IDs, or claims filming simulation works on-device without validated capture-to-ISP/JPEG pixels.
- **REJECT:** flashing firmware without independent full recovery and calibration preservation.

The next meaningful work is an **on-device-safe capture-boundary adapter**, sourced from authenticated stock 1.14, which maps a separately owned image buffer into the existing engine and then one actual JPG transaction. Until then, the experiments remain host-only.
