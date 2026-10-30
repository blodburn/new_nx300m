#ifndef NX300M_BAYER_PREJPEG_H
#define NX300M_BAYER_PREJPEG_H
#include <stddef.h>
#include <stdint.h>
#include "nx300m_linear_prejpeg.h"

/* Host-only. src contains UNPACKED 16-bit linear Bayer samples.
 * This is NOT a Samsung compressed SRW decoder or a native ISP/DMA adapter.
 * The caller MUST independently verify the actual CFA and calibration.
 * Pattern describes the top-left pixel at src[0]; crop origin affects CFA.
 */
typedef enum {
 NX_BAYER_RGGB=0, NX_BAYER_BGGR=1, NX_BAYER_GRBG=2, NX_BAYER_GBRG=3
} nx_bayer_pattern;
typedef struct {
 nx_bayer_pattern pattern;
 uint16_t black[4]; /* top-left, top-right, bottom-left, bottom-right */
 uint16_t white[4]; /* per-site saturation reference, must be > black */
 uint16_t defect_threshold; /* normalized 16-bit units; zero disables */
} nx_bayer_calibration;

/* Buffer lengths and row strides are measured in uint16_t samples.
 * Returns 0 on success, -1 on invalid input; no partial writes on bad
 * metadata. Output RGB16 is linear, normalized to [0,65535], with black
 * already subtracted and per-site white already scaled. No WB/color matrix.
 * Defect replacement only affects isolated same-CFA-phase outliers, and
 * never mutates the input RAW samples. Output row padding is untouched.
 */
int nx_bayer_to_rgb16(const uint16_t *src,size_t src_samples,
                       size_t src_stride_samples,
                       uint16_t *dst,size_t dst_samples,
                       size_t dst_stride_samples,
                       unsigned width,unsigned height,
                       const nx_bayer_calibration *cal);

/* Safe OFFLINE research bridge. Applies calibrated Bayer reconstruction,
 * then 16-bit WB/exposure/highlight shoulder, fixed Film LUT, RGB888 transfer
 * and the fixed Fuji/Leica family response after the high-bit-depth stage.
 * Caller supplies params black=0,white=65535 because
 * nx_bayer_to_rgb16 has ALREADY normalized its black/white levels.
 * Returns 1 (no-op) for Samsung Original; never generates a JPEG or SRW.
 * RGB scratch is 6*width*height bytes; family response adds width*height.
 * Not validated for NX300M camera RAM.
 */
int nx_bayer_prejpeg_film(const uint16_t *src,size_t src_samples,
                          size_t src_stride_samples,
                          uint8_t *dst,size_t dst_bytes,
                          size_t dst_stride_bytes,
                          unsigned width,unsigned height,
                          const nx_bayer_calibration *cal,
                          const nx_linear_params *look,
                          unsigned film_id);

/* Memory-reduced HOST equivalent. Reconstruct one RGB16 row at a time,
 * preserving global Bayer CFA parity, edge handling, fixed LUT response and
 * output bytes of nx_bayer_prejpeg_film on the same input.
 * RGB16 staging: 6*width bytes, not 6*width*height bytes. Final
 * RGB888 style response caches 3*width original luma bytes only.
 * Does not change RAW bytes or perform file I/O / JPEG encoding.
 * A negative return requires caller to discard output, not save it.
 */
int nx_bayer_prejpeg_film_streaming(const uint16_t *src,size_t src_samples,
                                    size_t src_stride_samples,
                                    uint8_t *dst,size_t dst_bytes,
                                    size_t dst_stride_bytes,
                                    unsigned width,unsigned height,
                                    const nx_bayer_calibration *cal,
                                    const nx_linear_params *look,
                                    unsigned film_id);

/* Host test seam for ONE prospective incremental JPEG encoding operation.
 * This sink is NOT a JPEG codec. An actual encoder must consume ordered RGB8
 * scanlines without buffering a full RGB frame and implement an ATOMIC
 * transaction: begin -> write_row* -> commit, or abort on any failure.
 * write_row receives an ephemeral buffer valid ONLY until callback return.
 * commit must not publish a corrupt/partial image on failure; abort removes
 * any temporary output. Metadata, JPEG encoding and SRW storage are the
 * responsibility of a future proven native adapter, NOT this test seam.
 */
typedef struct {
 int (*begin)(void *user,unsigned width,unsigned height,unsigned film_id);
 int (*write_row)(void *user,unsigned y,const uint8_t *row,size_t row_bytes);
 int (*commit)(void *user);
 void (*abort)(void *user);
 void *user;
} nx_bayer_rgb8_sink;
/* Returns 0 only after commit success, 1 for Original/no sink action and
 * -1 on rejection or aborted operation. No RAW output or camera RAM writes.
 * Worst-case pixel scratch: (6 + 6 + 3)*width bytes, plus fixed LUT context.
 */
int nx_bayer_prejpeg_emit_rows(const uint16_t *src,size_t src_samples,
                               size_t src_stride,unsigned width,unsigned height,
                               const nx_bayer_calibration *cal,
                               const nx_linear_params *look,unsigned film_id,
                               const nx_bayer_rgb8_sink *sink);
#endif
