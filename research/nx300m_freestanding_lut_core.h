/* Standalone GLIBC-FREE RGB12 LUT math.
 * No camera address, DMA access, firmware hook, allocator, I/O or libc call.
 * A safe loader contract and camera JPEG integration are NOT demonstrated.
 * The caller owns the LUT, input and output. No pointer lifetime is retained.
 */
#ifndef NX300M_FREESTANDING_LUT_CORE_H
#define NX300M_FREESTANDING_LUT_CORE_H
#include "nx300m_lut18.h"

#if defined(__GNUC__)
#define NX_FREESTANDING_EXPORT __attribute__((visibility("default")))
#else
#define NX_FREESTANDING_EXPORT
#endif

/* Returns 0 on success. Returns -1 on invalid args without writing output.
 * nodes_available must contain at least grid^3 nodes; valid grid 2..65.
 * src and dst must each contain at least pixels RGB12 records. In-place OK.
 * nodes must not overlap dst and must remain immutable during the call.
 * No side effects, no malloc, no global state, no imports or file accesses.
 */
NX_FREESTANDING_EXPORT
int nx_film_core_apply_rgb12(const nx_rgb12 *nodes, size_t nodes_available,
                             unsigned grid, const nx_rgb12 *src,
                             nx_rgb12 *dst, size_t pixels);

#endif
