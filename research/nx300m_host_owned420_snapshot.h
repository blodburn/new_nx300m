#ifndef NX300M_HOST_OWNED420_SNAPSHOT_H
#define NX300M_HOST_OWNED420_SNAPSHOT_H
#include "nx300m_freestanding_owned420_bridge.h"

/* HOST-ONLY boundary. The caller supplies readable host memory, not a
 * camera/DMA/kernel pointer. This copies every input byte used by the
 * renderer into independent allocations before any JPEG work begins.
 * It does NOT authenticate the caller's source memory provenance.
 *
 * Caller must zero-initialize the object, call take once, and release
 * before reusing it. A second take on a live snapshot is refused without
 * freeing or changing it. Source/job/out may not overlap. Callers must
 * keep each source stable until take returns. No NX300M device IO exists.
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
 * On failure a zero-initialized output stays cleared. If the caller passes
 * an existing live snapshot, that snapshot remains owned and unchanged.
 * No JPEG file is published by this module.
 * Actual camera mapping length, DMA ownership, and coherency UNVERIFIED.
 */
int nx_host_owned420_snapshot_take(
    nx_host_owned420_snapshot *out,
    const nx_film_owned420_hypothesis_job *input);

/* Structural integrity only; does not authenticate forged pointers or
 * prove physical camera buffer ownership. No input data is written. */
int nx_host_owned420_snapshot_ready(const nx_host_owned420_snapshot *out);

void nx_host_owned420_snapshot_release(nx_host_owned420_snapshot *out);
#endif
