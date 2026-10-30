#ifndef NX300M_HOST_YCC420_PROBE_H
#define NX300M_HOST_YCC420_PROBE_H
#include <stddef.h>
#include <stdint.h>

/* Read-only HOST data classifier. It NEVER interprets ARM addresses, accesses
 * camera device memory, or establishes actual NX300M 1.14 DMA layout.
 * Caller supplies safely copied 8-bit Y, interleaved C and *corresponding*
 * RGB reference at the same pipeline stage and exact crop.
 *
 * Only two hypothesized 4:2:0 byte orders are evaluated. The model uses
 * full-range BT.601 rounding; different ISP matrices/ranges and JPEG
 * quantization will typically reject or return inconclusive.
 */
typedef enum {
 NX_YCC420_BAD_INPUT=-1,
 NX_YCC420_INCONCLUSIVE=0,
 NX_YCC420_CBCR=1,
 NX_YCC420_CRCB=2
} nx_ycc420_assessment;
typedef struct {
 unsigned width,height;
 uint64_t pixels,chroma_pairs;
 uint64_t informative_pairs;
 /* Mean absolute error, 0..255 per component, in 1/1000 units. */
 uint32_t y_mae_milli;
 uint32_t cbcr_mae_milli;
 uint32_t crcb_mae_milli;
 uint32_t winning_gap_milli;
 nx_ycc420_assessment result;
} nx_ycc420_evidence;

nx_ycc420_assessment nx_host_ycc420_probe(
 const uint8_t *y,size_t y_bytes,size_t y_stride,
 const uint8_t *c,size_t c_bytes,size_t c_stride,
 const uint8_t *reference_rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned width,unsigned height,nx_ycc420_evidence *out);
#endif
