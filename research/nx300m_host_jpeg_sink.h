#ifndef NX300M_HOST_JPEG_SINK_H
#define NX300M_HOST_JPEG_SINK_H
#include "nx300m_bayer_prejpeg.h"
#include <stddef.h>
#include <stdint.h>
/*
 * Offline host JPEG 8-bit baseline 4:4:4 or 4:2:0 RGB-scanline encoder and
 * create-only transactional file writer (NOT Samsung NX JPEG implementation).
 * No full-frame RGB8 memory allocation. No firmware patch or native hook.
 * Optional ORIGINAL Exif APP1 payload must start "Exif\0\0" and be <=65533
 * bytes. When no original Exif is available, metadata are NOT synthesized.
 * It is the caller's duty to verify proprietary EXIF/MakerNotes externally.
 * Both formats are for portable host proof ONLY. ISO JPEG sampling 4:2:0
 * does NOT prove physical Samsung DMA buffer packing, chroma byte order,
 * camera colorspace/range or native 1.14 encoder interoperability.
 */
typedef struct nx_host_jpeg_writer nx_host_jpeg_writer;
typedef enum {
 NX_HOST_JPEG_444=0,
 NX_HOST_JPEG_420=1
} nx_host_jpeg_sampling;
nx_host_jpeg_writer *nx_host_jpeg_writer_create(
 const char *destination,const uint8_t *original_exif_app1,size_t exif_bytes);
/* Select actual JPEG SOF0 sampling. 4:2:0 needs only 16 RGB rows of scratch
 * and pads odd dimensions at the right/bottom edge to the MCU boundary. */
nx_host_jpeg_writer *nx_host_jpeg_writer_create_with_sampling(
 const char *destination,const uint8_t *original_exif_app1,size_t exif_bytes,
 nx_host_jpeg_sampling sampling);
nx_bayer_rgb8_sink nx_host_jpeg_writer_sink(nx_host_jpeg_writer *writer);
void nx_host_jpeg_writer_destroy(nx_host_jpeg_writer *writer);
#endif
