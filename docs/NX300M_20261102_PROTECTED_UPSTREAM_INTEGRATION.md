# NX300M host-only Film Simulator integration — 2026-11-02

## Scope

This branch builds on public `main` commit
`576400080f90e97ffbad984300e445a238fc064d`.
It is **not a camera firmware image**; do not install or flash it.

The experimental Film Simulator is independent of Samsung Picture Wizard
strength settings. Picture Wizard is only a possible future menu selector.
The host processing stages are copied Y/C 4:2:0 input, an independent preset
LUT, local edge-aware enhancement, per-look tone/grain, and a create-only JPEG
writer. Samsung Original and RAW pixels remain unchanged in host tests.

## Work delivered

1. Replace full-RGB-frame film enhancement staging with three-row rolling
   RGB enhancement and tone/grain support for copied host Y/C frames.
2. Add a bounded, read-only 8-hypothesis Y/C color model checker:
   BT.601 / BT.709, full / limited signal, CbCr / CrCb.
3. Strengthen offline firmware SLP analysis: archive and decoded BIN SHA-256
   comparison, ZIP member safety, file mutation refusal, six JAMCRC checks.
4. Add independent ASAN/UBSAN regression tests and `multimodel-test` /
   `multimodel-probe` targets, included in `make test`.
5. Preserve unmodified baseline paths from remote `main`; host images and
   firmware files are not bundled.

## Verification

Local source snapshot was compared against 133 public upstream Git blobs.
116 files matched exactly. The 17 different paths were investigated.
All source blobs selected for this branch were also compared by their
Git SHA-1 to their original local files.

Offline validation prior to remote integration: 19 C ASAN/UBSAN executables
(in three batches), 138 Python test cases, and 6 mocked EFL UI scenarios
passed. **GitHub Actions for this remote branch must be checked separately.**

```sh
make multimodel-test
make multimodel-probe
make test
```

## Hard safety gates

- The authenticated **stock NX300M 1.14** firmware binary is not available.
- Static study data is from a modified SLP 1.15 reference, not stock 1.14.
- Physical still-image Y/C packing, color matrix, memory ownership, native
  JPEG/EXIF/MakerNotes contracts and on-device EFL dial mapping are unverified.
- Full-brick recovery and camera-specific calibration preservation have not
  been demonstrated.
- Never flash, patch, or inject any of these host programs into the camera
  until all requirements have passed separately.

This is a source and regression-validation milestone, **not** a claim of a
working on-camera Fujifilm/Leica-quality simulator.
