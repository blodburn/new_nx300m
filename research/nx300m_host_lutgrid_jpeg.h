#ifndef NX300M_HOST_LUTGRID_JPEG_H
#define NX300M_HOST_LUTGRID_JPEG_H
#include "nx300m_lut_grid_host.h"
#include <stddef.h>
#include <stdint.h>

/* HOST-ONLY RGB888 (already copied from an authorized source) -> variable
 * grid RGB12 LUT -> independent JPEG 4:2:0 encoder. Not Samsung firmware.
 * 0: create-only committed JPEG; 1: Original/no output; -1: fail.
 * Source RGB and LUT are NEVER modified. No camera DMA or ISP access.
 * Input and output paths are caller-supplied; no camera storage effects.
 */
int nx_host_rgb888_lutgrid_jpeg(
 const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned width,unsigned height,const nx_rgb12 *lut,unsigned grid,
 int original_bypass,const char *new_jpeg_path,
 const uint8_t *original_exif_app1,size_t exif_bytes);
#endif
