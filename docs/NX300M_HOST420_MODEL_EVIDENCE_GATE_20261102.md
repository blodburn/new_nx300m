# NX300M — host-only Y/C420 color-model evidence gate

## What changed

The original `nx_host420_film_to_jpeg` API remains the old explicit,
experimental **BT.601 full-range** path and keeps its byte-exact baseline
regression. It is **not** a camera-native color transform.

The separate `nx_host420_film_to_jpeg_from_reference` API requires
**all three host-owned copied** Y, chroma and corresponding RGB888 buffers,
their independently validated spans/strides, and a non-null output report.
It recomputes the existing eight-hypothesis probe from those exact bytes:
BT.601/BT.709 × full/limited × CbCr/CrCb.

Only `NX_420_MODEL_DISTINCT` results are accepted. The chosen model is
then fed to the host decoder *before* LUT, enhancement, style and JPEG
encoding. Invalid/inconclusive models or truncated references fail before
creating a JPEG. Original bypass is retained when the probe is distinct.

## Boundaries

- This cannot verify that externally supplied RGB and Y/C were actually
  acquired from the same physical camera stage. An externally signed
  acquisition record and original FW1.14 source are still missing.
- This does not identify any Samsung physical memory layout, chroma siting,
  pixel ownership, native JPEG/Exif ABI, sensor calibration, or an acceptable
  way to inject code into the camera.
- The new function is HOST-ONLY; no camera DMA, storage or firmware changes.
- The legacy BT.601 path remains only for backward compatible host fixture
  comparison. Do not treat it as a validated NX300M 1.14 output.
- Synthetic 48×32 fixtures exercise all eight hypotheses, reject greyscale
  ambiguity and truncated references, preserve input bytes and Original
  no-output semantics.

## Reproduce

```sh
make test
make multimodel-test
```

Hardware integration and firmware flash remain **NOT APPROVED**.
