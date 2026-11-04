# NX300M FW1.14 — host JPEG structure / Exif APP1 / MakerNote preservation

**Scope: offline synthetic host JPEGs only. Firmware install: NO-GO.**

## Proof chain

```text
          Host synthetic RGB / synthetic TIFF Exif APP1
                           |
               existing host JPEG 4:2:0 writer
                           |
              +------------+-------------+
              |                          |
       ORIGINAL RGB JPEG         FILM-altered RGB JPEG
              |                          |
             SOI, SOF0, SOS, FF-D9, no trailing bytes
              |                          |
       exactly one Exif APP1      exactly one Exif APP1
              |                          |
       TIFF IFD0 -> ExifIFD -> MakerNote (tag 0x927C)
              |                          |
              +---------- compare -------+
                           |
                 APP1 exact byte equality
                 MakerNote field SHA equal
                 same SOF 34x22 / 4:2:0
                           |
                 HOST FILE SAFETY: PASS
                           |
         Native camera JPEG/Exif ABI: NOT PROVEN
         Samsung MakerNote semantics: NOT PROVEN
         Physical on-camera 20.6MP: NOT PROVEN
         Camera firmware flash permission: NO
```

### New tools

- `research/nx300m_jpeg_exif_provenance_gate.py`: read-only ISO JPEG frame/scan structure verifier. Checks SOI, baseline SOF0, SOS, entropy-stuffed markers, exactly one Exif APP1, EOI with no trailing bytes, dimensions, 4:2:0 component sampling. Validates TIFF endian marker, offset bounds, ExifIFD pointer, MakerNote type/size and unique tag; compares complete APP1 bytes between caller-supplied original and modified host JPEG.
- `research/nx300m_test_jpeg_pair_fixture.c`: synthesizes two **actual host-encoded JPEG files**, with one identical, synthetic `NX-MAKER` Exif MakerNote tag. This string does not represent, reconstruct or authenticate a Samsung MakerNote.
- `research/test_nx300m_jpeg_exif_provenance_gate.py`: tests real host encoder output, exact APP1 and MakerNote checksum, changed APP1 bytes, wrong chroma sampling/size, damaged EOI, unexpected trailing data, duplicate Exif APP1, corrupted Exif offset, missing MakerNote and source symlinks.
- `make jpeg-exif-test`: compile the disposable host encoder fixture and run the read-only audit regression. Also part of `make test`.

### Offline private file audit

```sh
python3 research/nx300m_jpeg_exif_provenance_gate.py \
    --original-jpeg /private/caller-authorized-original.jpg \
    --film-jpeg /private/caller-authorized-film.jpg \
    --require-makernote \
    --width 5546 --height 3714
```

- A success reports **exact APP1 byte identity** and structural consistency between two supplied JPEG files, not that those JPEGs came from a camera or are decodable by Samsung native software.
- A mismatch reports exit code 2. The tool does not rewrite EXIF/MakerNotes, modify either file, access camera devices or call firmware routines.
- Exif TIFF pointers are verified *within the APP1 segment* only. This does not confirm thumbnail, proprietary Samsung MakerNote semantics, lens metadata accuracy or multiple APP1/XMP/ICC marker parity. APP marker equality is reported separately.
- The tool does not decompress JPEG scan entropy, prove pixel similarity, manufacturer firmware authenticity, native ISP/DMA buffer ownership, memory budget, camera write ABI, or calibration/recovery safety.
- Never commit private owner captures or proprietary firmware to a public repository. Firmware changes remain prohibited until physical recovery and authentic FW1.14 evidence are independently verified.
