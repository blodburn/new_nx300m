#ifndef NX300M_LINEAR_PREJPEG_H
#define NX300M_LINEAR_PREJPEG_H
#include <stdint.h>
#include <stddef.h>
/* Independent LINEAR-16-bit RGB pre-JPEG stage.
 * Input MUST be calibrated linear demosaiced RGB, not Samsung proprietary
 * Bayer SRW and not ISP's packed Y/C DMA. Actual native sensor mapping,
 * black/white levels, WB, demosaicing, noise model remain future work.
 *
 * The key difference from Picture Wizard's encoded-JPEG LUT is that
 * sensor signal values are tone-mapped BEFORE 8-bit clipping, retaining
 * distinctions in bright pixels that naive exposure would blow out.
 * The single 13-preset wheel is unchanged; Samsung Original = return 1
 * without touching output (native original is handled separately).
 */
typedef struct {
 uint16_t black_level;
 uint16_t white_level;
 float exposure;
 float white_balance[3];
 float highlight_knee; /* 0.50 ... 0.95, smooth shoulder onset */
} nx_linear_params;
/* src_stride_samples counts 16-bit elements; dst_stride_bytes counts bytes.
 * Returns 0 on processed, 1 on original no-op, -1 on invalid. */
int nx_linear_prejpeg_film_rgb16(const uint16_t *src,size_t src_stride_samples,
                                uint8_t *dst,size_t dst_stride_bytes,
                                unsigned width,unsigned height,
                                unsigned film_preset,
                                const nx_linear_params *params);

/* Reusable HOST-only row processor for memory-limited Bayer staging.
 * Prepare validates numeric calibration, builds the same fixed 18^3 LUT and
 * transfer table ONCE; it does not own frame buffers or call a JPEG encoder.
 * Prepare returns 1 and *out=NULL for Samsung Original, -1 on failure.
 * Caller validates row capacities / overlap before calling process_row.
 * These functions are NOT a native NX300M firmware interface.
 */
typedef struct nx_linear_prejpeg_work nx_linear_prejpeg_work;
int nx_linear_prejpeg_prepare(nx_linear_prejpeg_work **out,
                             unsigned film_preset,const nx_linear_params *params);
int nx_linear_prejpeg_process_row(const nx_linear_prejpeg_work *work,
                                 const uint16_t *rgb16,uint8_t *rgb8,
                                 unsigned width);
void nx_linear_prejpeg_release(nx_linear_prejpeg_work *work);
#endif
