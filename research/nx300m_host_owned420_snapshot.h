#ifndef NX300M_HOST_OWNED420_SNAPSHOT_H
#define NX300M_HOST_OWNED420_SNAPSHOT_H
#include "nx300m_freestanding_owned420_bridge.h"

/* HOST-ONLY boundary. The caller supplies readable host memory, not a
 * camera/DMA/kernel pointer. This copies every input byte used by the
 * renderer into independent allocations before any JPEG work begins.
 * It does NOT authenticate the caller's source memory provenance.
 *
 * Caller must zero-initialize the object, call take once, and release
 * before reusing it. No firmware interface or NX300M device IO exists.
 */
typedef struct {
    nx_film_owned420_hypothesis_job job;
    uint8_t *owned_y;
    uint8_t *owned_chroma;
    nx_rgb12 *owned_lut;
    uint16_t *owned_decode;
    uint8_t *owned_encode;
} nx_host_owned420_snapshot;

/* 0 on complete copy, -1 on invalid metadata/overlap/allocation failure.
 * On failure the output object remains cleared; no file is published.
 * Actual camera mapping length, DMA ownership, and coherency UNVERIFIED.
 */
int nx_host_owned420_snapshot_take(
    nx_host_owned420_snapshot *out,
    const nx_film_owned420_hypothesis_job *input);

void nx_host_owned420_snapshot_release(nx_host_owned420_snapshot *out);
#endif
