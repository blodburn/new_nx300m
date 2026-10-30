#ifndef NX300M_HOST_CAPTURE_COPY_ADAPTER_H
#define NX300M_HOST_CAPTURE_COPY_ADAPTER_H
#include "nx300m_picture_wizard_route_guard.h"
#include <stddef.h>
#include <stdint.h>

/* OFFLINE HOST-ONLY. The source must be a separately owned/captured,
 * correctly decoded RGB888 frame. This does NOT wrap Samsung CYcc/DMA
 * buffers or establish any NX300M 1.14 firmware ABI.
 *
 * Never changes src. Never changes dst if result != NX_HOST_COPY_APPLIED.
 * No overlap (including partial overlap) is permitted for source/dest.
 * On success, publishes a full stride*height buffer into dst; padding
 * bytes remain identical to the source. JPEG encoding is separate.
 */
enum nx_host_copy_result {
 NX_HOST_COPY_INVALID=-1,
 NX_HOST_COPY_APPLIED=0,
 NX_HOST_COPY_BYPASSED=1
};
typedef struct {
 const char *config_path;
 nx_pw_source source;
 nx_pw_capture_mode capture_mode;
 int rgb888_validated; /* EXACTLY 1 for experimental host simulation */
 const uint8_t *src;
 size_t src_bytes;
 uint8_t *dst;
 size_t dst_bytes;
 size_t stride;
 unsigned width,height;
} nx_host_copy_job;
int nx_host_capture_apply_copy(const nx_host_copy_job *job);
#endif
