#ifndef NX300M_HOST_420_FILM_JPEG_H
#define NX300M_HOST_420_FILM_JPEG_H
#include <stddef.h>
#include <stdint.h>
#include "nx300m_host_native420_bridge.h"

/* HOST-ONLY explicit 4:2:0 -> RGB -> independent film look -> JPEG.
 * Never access a camera/DMA pointer or edit the input Y/C/RAW planes.
 * Explicit CBCR/CRCB byte ordering is an experimental model. It does NOT
 * identify actual Samsung NX300M 1.14 CYcc packing or capture ABI.
 * Returns 0 only for a committed new JPG, 1 for Original no-op, -1
 * on validation, allocation, filter, encoding, or file commit failure.
 * Never overwrites an existing destination. No Picture Wizard parameters
 * are modified or used to process the pixel data.
 */
int nx_host420_film_to_jpeg(
    const uint8_t *y, size_t y_bytes, size_t y_stride,
    const uint8_t *chroma, size_t chroma_bytes, size_t chroma_stride,
    unsigned width, unsigned height, enum nx_host420_order byte_order,
    unsigned film_id, const char *new_jpeg_path,
    const uint8_t *original_exif_app1, size_t exif_bytes);
#endif
