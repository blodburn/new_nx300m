/* Standalone, no-libc HOST-HYPOTHESIS Y/C420 -> RGB12 LUT -> RGB888.
 * No camera pointer discovery, live capture, DMA access, JPEG/EXIF,
 * allocation, I/O, syscalls, or target firmware patch/loader integration.
 * The caller must explicitly declare copy ownership and format hypothesis.
 * Source pixel buffers MUST be independent, host-owned copies; this cannot
 * authenticate the provenance of a pointer passed by an untrusted caller.
 */
#ifndef NX300M_FREESTANDING_OWNED420_BRIDGE_H
#define NX300M_FREESTANDING_OWNED420_BRIDGE_H
#include "nx300m_freestanding_lut_core.h"
#include <stddef.h>
#include <stdint.h>

#define NX_FILM_420_COPY_DECLARATION 0x4e58434fu
enum nx_film_420_hypothesis {
    NX_FILM_BT601_FULL_CBCR_HYPOTHESIS=1,
    NX_FILM_BT601_FULL_CRCB_HYPOTHESIS=2
};
typedef struct {
    uint32_t copy_declaration; /* EXACT NX_FILM_420_COPY_DECLARATION */
    unsigned hypothesis;     /* caller asserts hypothetical Cb/Cr packing */
    const uint8_t *y;        /* independent, immutable Y plane bytes */
    size_t y_bytes;
    size_t y_stride;
    const uint8_t *chroma;   /* independent, immutable interleaved 420 */
    size_t chroma_bytes;
    size_t chroma_stride;
    unsigned width;
    unsigned height;
    const uint16_t *decode_srgb; /* owned 256 entries; host-provided */
    size_t decode_entries;
    const uint8_t *encode_srgb;  /* owned 4096 entries; host-provided */
    size_t encode_entries;
    const nx_rgb12 *lut;         /* immutable 2-65 RGB12 LUT nodes */
    size_t lut_nodes;
    unsigned grid;
    uint8_t *rgb;           /* independent caller-owned RGB888 output */
    size_t rgb_bytes;
    size_t rgb_stride;
} nx_film_owned420_hypothesis_job;

/* 0: success; -1: invalid parameters, with no output modified.
 * Output RGB payload changed only, row padding unchanged.
 * Source planes, lookup tables and LUT remain unchanged. No malloc.
 * This implements only BT.601 FULL RANGE sampling as a HOST hypothesis;
 * does not prove Samsung NX300M native matrix, range or buffer ownership.
 */
NX_FREESTANDING_EXPORT
int nx_film_core_render_owned420_hypothesis(
    const nx_film_owned420_hypothesis_job *job);

/* Emit only [first_row, first_row + row_count) into rgb[0..].
 * RGB payload uses job->rgb_stride per emitted row, NOT the global frame
 * offset. Y/C and height still describe the complete independent COPY.
 * Any first_row parity is valid; 4:2:0 chroma sampling uses global row/2.
 * Output may be one RGB row (width*3 bytes), not a full-frame staging
 * allocation. Caller must handle JPEG row/MCU ordering externally.
 * All validation occurs before any writes; invalid spans leave rgb intact.
 */
NX_FREESTANDING_EXPORT
int nx_film_core_render_owned420_rows_hypothesis(
    const nx_film_owned420_hypothesis_job *job,
    unsigned first_row, unsigned row_count);
#endif
