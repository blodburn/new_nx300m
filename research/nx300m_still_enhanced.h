#ifndef NX300M_STILL_ENHANCED_H
#define NX300M_STILL_ENHANCED_H
#include "nx300m_still_pipeline.h"
/* Transactional, opt-in JPEG RGB host-image pipeline: selected film LUT,
 * then conservative image enhancement. Not Samsung native DMA. Original
 * and RAW remain byte-identical; never called implicitly by old API.
 */
/* Call only on an already isolated private RGB copy. A failed call can
 * change that private buffer: publish it only on NX_STILL_APPLIED.
 * Host-only. Reuses all stages without allocating a second full RGB copy. */
int nx_still_filter_enhanced_private_copy(unsigned preset_id,
                                    nx_still_format format,
                                    uint8_t *private_rgb,size_t stride,
                                    unsigned width,unsigned height);
int nx_still_filter_enhanced_inplace(unsigned preset_id,nx_still_format format,
                                    uint8_t *pixels,size_t stride,
                                    unsigned width,unsigned height);
#endif
