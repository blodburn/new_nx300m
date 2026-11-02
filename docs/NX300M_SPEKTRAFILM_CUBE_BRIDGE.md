# NX300M — offline SpektraFilm-compatible 3D LUT conversion

**Scope: HOST-ONLY. No firmware patch, no camera memory, no Picture Wizard hook, no flash.**

## Upstream and boundary

SpektraFilm by Andrea Volpato:
https://github.com/andreavolpato/spektrafilm

Upstream commit reviewed: 3bb2c2d2801ff68b92019cf1dbcbb133d60832bc
(2026-11-02). SpektraFilm is a Python desktop physically based spectral
film / photographic print / scanning simulator. Its offline LUT creator can
export Adobe 3D .cube files. This repository includes **no** SpektraFilm
source, film profile, derivative LUT, or Python runtime dependency.

The independent converter accepts a previously generated, authorized,
**sRGB-encoded input -> sRGB-encoded output**, **single 3D** .cube LUT.
On SpektraFilm, choose topology 1lut, input sRGB, output sRGB, and
resolution 33. This bridge intentionally refuses 1D LUTs, multi-LUT
topologies, non-unit DOMAIN_MIN/MAX and out-of-range node values.

## Host workflow

1. Generate the .cube on a PC with an appropriately licensed tool/profile.
2. Run the standard-library-only converter:

       python3 scripts/nx300m_cube_to_lut18.py \
         --input /local/film_srgb_to_srgb.cube \
         --output /local/film.nx18.txt \
         --source-name "SpektraFilm by Andrea Volpato" \
         --license-id "CC-BY-SA-4.0" \
         --samples 2048

3. Inspect /local/film.nx18.txt.qa.json and preserve the source file,
   its SHA-256, author, export settings, license text and any modifications.
4. In the HOST C process, allocate NX_LUT_COUNT elements of nx_rgb12,
   then call nx_lut18_text_load(path, table) from
   research/nx300m_lut18_text_io.h. Use the resulting table with the
   existing nx_lut18_apply / nx_preview_filter_rgb888.
5. Reproduce checks:

       make test
       python3 research/test_nx300m_cube_to_lut18.py

No camera firmware code path is entered by these commands.

## Mandatory color conversion

The existing NX300M research preview filter receives sRGB RGB888 pixels,
decodes them to **linear 12-bit RGB**, applies an 18x18x18 LUT, then
encodes the result to sRGB. An offline sRGB->sRGB .cube cannot be copied
directly into that table. For each of the 5,832 NX18 nodes, this bridge:

    Linear NX18 coordinate
      -> sRGB encode
      -> source .cube trilinear sample
      -> sRGB decode to linear
      -> round to 12-bit integer
      -> NX18 RGB12 node

The output begins with NX18_RGB12_TEXT_V1 and contains exactly 5,832
decimal R G B rows, each 0..4095, R fastest and B slowest.
Packed in the existing nx_rgb12 table these require **46,656 bytes**
(5,832 nodes × 8 bytes). The host loader stages the full table before
committing it, and refuses symlinks, invalid rows, truncated/extra data,
oversized input and output edits on failure.

## Quantitative offline acceptance gate

Default 2,048 off-grid Halton points compare the source trilinear LUT
against the existing NX18 12-bit fixed-point trilinear interpolation.
Error is measured in **sRGB encoded 8-bit channel-value units**:
- maximum absolute per-channel error across points: <= 12.0;
- mean of each point's maximum absolute channel error: <= 2.0.

These are engineering limits, **not established photographic tolerances**.
QA JSON includes input/output SHA-256, max, mean, p99 and source/license
declarations. Exceeding limits refuses conversion and produces no output.
This is NOT Delta-E, camera calibration, real-image proof, or hardware
colorimetry. 33^3 to 18^3 necessarily discards LUT detail.

Converter fail-closed cases: symlink or changing source; input >24 MiB;
invalid UTF-8; duplicate headers; 1D LUT; unexpected non-unit domain;
NaN / infinity / out-of-gamut node; wrong size or node count;
existing output files. The host text loader is separately tested with
synthetic identity LUT, RGB888 preview, invalid/truncated/extra data,
and symlink rejection. No upstream derivative LUT is checked in.

## Licenses

SpektraFilm code: **GPL-3.0**. Profile data and LUTs derived from those
profiles: **CC BY-SA 4.0** according to the upstream licensing files.
Preserve upstream author Andrea Volpato, source URL, CC BY-SA notice,
license terms and modification log when distributing a derivative LUT.
Some upstream files have additional licensing explanations: consult
SPEKTRAFILM_LICENSE.txt and the upstream README. This converter does
not authenticate user-provided --license-id. Contact the rights holder
for incompatible distribution requirements. Outputs made from the
synthetic test fixtures are not SpektraFilm derivatives.

## Camera gates still CLOSED

No genuine stock FW1.14 SHA-256 chain of custody; no native JPEG ABI /
ISP color matrix / white balance / buffer lifetime; no reversible
full-brick recovery; no calibrated NX300M reference images. This bridge
does not add a menu preset or install a LUT on the camera. Never flash
these host research artifacts.

## Actual SpektraFilm PROVIA 100F host CI (ephemeral)

An additional GitHub Actions workflow in .github/workflows/spektrafilm-profile-check.yml
executes a real upstream SpektraFilm pipeline in a disposable GitHub runner.
Upstream pinned SHA: 3bb2c2d2801ff68b92019cf1dbcbb133d60832bc.
Python 3.13; film: fujifilm_provia_100f; paper: fujifilm_crystal_archive_typeii.
The workflow bakes a resolution-17 sRGB-in/sRGB-out 1-LUT, converts it
to 5,832 RGB12 nodes using the independently developed converter, and
prints 2,048-point numerical max/mean RGB errors and an explicit decision.
Only metadata and numerical metrics appear in the CI log; no upstream source,
film profiles, source .cube, or derivative NX18 LUT are committed or uploaded.

The initial real-profile run uses --observe-only: it can record
REJECT_NUMERICAL_RESCALING without misreporting a valid numeric rejection as
a build crash. The actual strict guardrails stay 12.0 peak, 2.0 mean
(8-bit encoded-channel units). A numeric PASS is NOT a camera color proof.

No NX300M firmware, camera capture buffer or sensor calibration is involved.
Any outputs remain CC BY-SA 4.0 derivatives of the upstream profiles,
not automatically suitable for uncredited third-party distribution.

## Numerical 18/33/65^3 host-table comparison

The ephemeral real-profile workflow also benchmarks 18^3, 33^3, and
65^3 **12-bit linear** LUT-grid representations against the same real
sRGB .cube at identical 2,048 Halton samples. It reports peak/mean/p99
RGB8 errors and number of samples with a channel error >12. All LUT
nodes stay in runner RAM, and no derivative files are published.
This diagnostic does not change the fixed 18^3 NX300M host API or claim
that either larger table is safe on an actual camera.
