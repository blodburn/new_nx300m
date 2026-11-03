#ifndef NX300M_HOST420_LUTGRID_JPEG_H
#define NX300M_HOST420_LUTGRID_JPEG_H
#include <stddef.h>
#include <stdint.h>
#include "nx300m_host_native420_bridge.h"
#include "nx300m_ycc420_multimodel_probe.h"
#include "nx300m_lut_grid_host.h"

/* HOST COPY-ONLY EXPERIMENT: Y and interleaved Cb/Cr are caller-owned,
 * non-DMA buffers. Order/matrix/range are hypotheses, NOT FW1.14 proof.
 * Stream decode -> sRGB/linear RGB12 -> 3D grid -> host 4:2:0 JPEG.
 * Returns 0 for new JPEG, 1 for Original bypass, -1 for reject.
 * Does not change the source planes, LUT or existing JPEG files.
 */
int nx_host420_lutgrid_jpeg_hypothesis(
    const uint8_t *y,size_t y_bytes,size_t y_stride,
    const uint8_t *chroma,size_t chroma_bytes,size_t chroma_stride,
    unsigned width,unsigned height,enum nx_host420_order order,
    enum nx_420_model color_model,const nx_rgb12 *lut,unsigned grid,
    int original_bypass,const char *new_jpeg_path,
    const uint8_t *original_exif_app1,size_t exif_bytes);

/* Extra guarded path: re-probe an independently copied, same-stage RGB
 * reference before selecting a Y/C decode hypothesis. The reference
 * is never modified. No inference from ordinary JPG/SRW is sufficient.
 */
int nx_host420_lutgrid_jpeg_from_reference(
    const uint8_t *y,size_t y_bytes,size_t y_stride,
    const uint8_t *chroma,size_t chroma_bytes,size_t chroma_stride,
    const uint8_t *reference_rgb,size_t reference_bytes,size_t reference_stride,
    unsigned width,unsigned height,
    const nx_rgb12 *lut,unsigned grid,int original_bypass,
    const char *new_jpeg_path,const uint8_t *original_exif_app1,
    size_t exif_bytes,nx_420_model_report *report);
#endif
