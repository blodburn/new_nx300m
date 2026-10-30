#ifndef NX300M_HOST_NATIVE420_BRIDGE_H
#define NX300M_HOST_NATIVE420_BRIDGE_H
#include "nx300m_bayer_prejpeg.h"
#include "nx300m_cycc_layout.h"
#include <stdint.h>
#include <stddef.h>

/* HOST-ONLY integration study, NOT a firmware hook.
 * Reuses source-proved original CYcc 0x24-byte geometry, but actual NX300M
 * camera DMA chroma packing, byte order, RGB->YCC matrix/range, alignment
 * and installed 1.14 API are NOT proven. Do not apply to live pointers.
 *
 * The explicit hypothesis models 2 contiguous stride*height-byte regions,
 * with Y in region 0 and NV12/NV21-like interleaved C in the FIRST h/2 rows
 * of region 1. The second half of region 1 stays 0xA5 (guard).
 * Film ID 0 Original bypasses the entire sink. Host stager never saves JPEG,
 * reads/writes RAW, changes native memory or calls original EncodeYCC.
 */
enum nx_host420_order {
 NX_HOST420_ORDER_UNSPECIFIED=0,
 NX_HOST420_CBCR_EXPERIMENTAL=1,
 NX_HOST420_CRCB_EXPERIMENTAL=2
};
typedef struct nx_host420_stage nx_host420_stage;
nx_host420_stage *nx_host420_create(unsigned width,unsigned height,
                                    unsigned stride,
                                    enum nx_host420_order explicit_order);
nx_bayer_rgb8_sink nx_host420_sink(nx_host420_stage *stage);

/* Returns only after the entire image was emitted and committed.
 * Metadata base=0x10000000 is SYNTHETIC and must never be used as an ARM
 * pointer. Data is host-owned. CbCr order is hypothetical. */
const uint8_t *nx_host420_published(const nx_host420_stage *stage,
                                    size_t *bytes,
                                    nx_native_cycc *synthetic_header);
void nx_host420_destroy(nx_host420_stage *stage);
#endif
