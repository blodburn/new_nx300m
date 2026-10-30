#ifndef NX300M_STILL_ENHANCED_H
#define NX300M_STILL_ENHANCED_H
#include "nx300m_still_pipeline.h"
/* Transactional, opt-in JPEG RGB host-image pipeline: selected film LUT,
 * then conservative image enhancement. Not Samsung native DMA. Original
 * and RAW remain byte-identical; never called implicitly by old API.
 */
int nx_still_filter_enhanced_inplace(unsigned preset_id,nx_still_format format,
                                    uint8_t *pixels,size_t stride,
                                    unsigned width,unsigned height);
#endif
