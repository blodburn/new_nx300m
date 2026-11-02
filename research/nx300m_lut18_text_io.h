#ifndef NX300M_LUT18_TEXT_IO_H
#define NX300M_LUT18_TEXT_IO_H
#include "nx300m_lut18.h"
/* Host-only data import for independently created 18^3 linear RGB12 LUTs.
 * Input is ASCII: "NX18_RGB12_TEXT_V1\n", followed by exactly 5832
 * R G B decimal rows (R changes fastest), each channel 0..4095.
 * No camera/device/DMA/file publication operations.
 * Does not update dst on ANY invalid or truncated input.
 */
int nx_lut18_text_load(const char *path, nx_rgb12 *dst);
#endif
