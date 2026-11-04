# NX300M FW1.14 — SHA-bound host capture evidence → eight color hypotheses

**Release decision: NO-GO for installation. This is offline host-only analysis of copies. No physical camera investigation has been performed.**

## Processing steps

```text
       (private, independently authorized host copies)
            capture.json + Y.bin + C.bin + RGB.bin
                            |
         1. File type/stride/length/SHA-256 preflight
                            |
              reject on mismatch or symlink
                            |
         2. Explicit, SHA-pinned host C analysis executable
                            |
       3. C probe: 4 color models × 2 chroma orders
       BT.601/BT.709 × Full/Limited × CbCr/CrCb
                            |
       4. Parse 8 scores, gap, sample and chroma counts
                            |
               +------------+-----------+
               |                        |
          DISTINCT_ONLY            INCONCLUSIVE
          (host hypothesis)          (no winner)
               |                        |
               +------------+-----------+
                            |
          5. Recheck the binary SHA and all plane hashes
                            |
           camera identity / buffer ownership / ABI
                     NOT VERIFIED
                            |
                 firmware flash: NO
```

## Concrete files

- `research/nx300m_capture_evidence_model_gate.py`: offline association gate for existing manifest validator and actual existing `nx300m_ycc420_multimodel_probe_cli.c` executable. Rechecks SHA-256 of all source copies after the C executable returns, requires an explicitly pinned SHA for the executable, parses every candidate score and checks its reported winner.
- `research/test_nx300m_capture_evidence_model_gate.py`: uses actual compiled C binary for eight independently generated synthetic 48×32 test cases (4 matrix/range × 2 byte orders), grayscale ambiguity, corrupted plane bytes, forged metadata, a substituted executable, symlinked source directory, and falsified score/winner.
- `Makefile`: `make capture-evidence-test` compiles and tests the existing offline C probe and new Python gate; also invoked from `make test`.
- `.github/workflows/nx300m-arm32-passive-probe.yml`: the existing passive ARM32 workflow also invokes the new read-only host evidence test.

## Usage (no camera, private files only)

```sh
make multimodel-probe
sha256sum .build/nx300m_ycc420_multimodel_probe
python3 research/nx300m_capture_evidence_model_gate.py \
  --bundle-dir /private/independently-copied-capture \
  --probe "$PWD/.build/nx300m_ycc420_multimodel_probe" \
  --probe-sha256 "<sha256 reported by sha256sum>"
```

Exit `0`: hashes and geometry valid; a **host-only hypothesis** is distinct. Exit `3`: hashes valid but the color hypotheses are inconclusive. Exit `2`: invalid evidence, damaged or ambiguous metadata, source change or untrusted/inconsistent output. No exit code authorizes a firmware flash, camera DMA access, or a native encoder call. Do not publish owner captures or proprietary firmware to public CI.

## Limitations

- The JSON string `camera_model=NX300M` and the declared `same_stage_copy_declared=true` are *not independent acquisition proof*. The tool cannot determine source firmware authenticity, frame provenance or whether Y/C and RGB are from the same real sensor processing stage.
- The only model actually implemented by the no-libc output renderer is BT.601 FULL RANGE for either chroma order. The 8-model probe does **not** make BT.709 or LIMITED dynamically supported in the freestanding DSO.
- A pinned host executable hash prevents accidental substitution against the supplied digest but does not constitute manufacturer provenance, build reproducibility or proof that a malicious executable cannot lie.
- The gate cannot establish live device buffer ownership/format, frame freshness, cache/DMA safety, native encoder ABI, MakerNotes/EXIF completeness, full-brick restore or usable memory budget. It has no connection to a camera installation workflow.
- No camera images, private samples, firmware, executables, lens calibration or serial-specific data are uploaded or committed.

**Do not copy an ARM DSO onto a camera or flash firmware based on a host hypothesis.**
