#ifndef NX300M_HOST_PREVIEW420_H
#define NX300M_HOST_PREVIEW420_H

/* OFFLINE HOST-ONLY Y/C420 preview. No Samsung live-view buffer, camera
 * capture callback, native JPEG codec, firmware, or DMA access.
 *
 * The selected Film Simulator LOOK is the active preview entry when its
 * wheel UI is open; otherwise it is the committed entry. A shutter still
 * uses the committed entry, NEVER an unconfirmed preview.
 *
 * RGB888 input/output must be independent host-owned memory, not camera
 * pointers. An invalid request leaves all output pixels unchanged.
 * Samsung Original returns BYPASSED and NEVER processes image bytes.
 */
#include "nx300m_tizen_film_controller.h"
#include "nx300m_freestanding_owned420_bridge.h"
#include <stddef.h>
#include <stdint.h>

enum nx_host_preview420_result {
    NX_HOST_PREVIEW420_INVALID=-1,
    NX_HOST_PREVIEW420_APPLIED=0,
    NX_HOST_PREVIEW420_BYPASSED=1
};
typedef struct {
    const nx_tizen_film_controller *controller;
    const nx_film_owned420_hypothesis_job *copied_input;
    const char *freestanding_module_path;
    uint8_t *output_rgb;
    size_t output_bytes;
    size_t output_stride;
} nx_host_preview420_request;

/* A render applies the same 18^3 LUT generated from the menu as the host
 * shutter path. Rendering uses the same independent no-libc BT.601
 * FULL-RANGE Y/C hypothesis module as host JPEG encoding.
 *
 * All pixels are computed in private host memory before publication.
 * Returns 0 after writing only width*3 bytes per output row (padding is
 * unchanged); 1 for Original without touching any buffers; -1 on error,
 * with output_rgb and *rendered_id unchanged.
 *
 * This does not establish photo/live-view equivalence on a real NX300M:
 * Y/C packing and transfer functions are experimental host inputs.
 */
int nx_host_preview420_apply(const nx_host_preview420_request *request,
                             unsigned *rendered_id);
#endif
