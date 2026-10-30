/* Independent camera-neutral 18x18x18 RGB 12-bit LUT engine.
 * Grid geometry is inspired by observed firmware buffer dimensions; implementation is original.
 * NOT Fujifilm firmware code, and not yet integrated into Samsung NX300M.
 */
#ifndef NX300M_LUT18_H
#define NX300M_LUT18_H
#include <stdint.h>
#include <stddef.h>
#define NX_LUT_GRID 18u
#define NX_LUT_COUNT (NX_LUT_GRID * NX_LUT_GRID * NX_LUT_GRID)
typedef struct { uint16_t r, g, b, reserved; } nx_rgb12;
_Static_assert(sizeof(nx_rgb12) == 8, "NX LUT packing must be 8 bytes/node");
/* Returns zero on success, negative on invalid args. */
int nx_lut18_apply(const nx_rgb12 *lut, const nx_rgb12 *src, nx_rgb12 *dst, size_t pixels);
void nx_lut18_identity(nx_rgb12 *lut);
#endif
