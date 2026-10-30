#ifndef NX300M_IMAGE_ENHANCE_H
#define NX300M_IMAGE_ENHANCE_H
#include <stddef.h>
#include <stdint.h>
/* Opt-in, camera-neutral post-LUT RGB888 image quality pass.
 * Works on host-accessible sRGB bytes ONLY; never native YCC DMA or Bayer RAW.
 * Fixed conservative settings: edge-aware shadow chroma noise reduction,
 * mild flat-field luma denoise and bounded midtone-only detail recovery.
 * It cannot remove camera shake, restore saturated highlights or RAW detail.
 * Returns 0 on success (which may be a no-op for flat images), -1 on error.
 * No partial image edits if dimensions/allocations fail.
 */
int nx_image_enhance_rgb888(uint8_t *pixels,size_t stride,
                           unsigned width,unsigned height);
#endif
