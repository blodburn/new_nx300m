#ifndef NX300M_LUT_GRID_HOST_H
#define NX300M_LUT_GRID_HOST_H
#include "nx300m_lut18.h"
/* HOST-ONLY variable-size RGB12 LUT. NOT an NX300M firmware/ISP API.
 * Grid ranges from 2..65; RGB12 table uses 8 bytes per node.
 * Input order: R changes fastest, G second, B slowest.
 * C loader is transactional: invalid input never alters destination.
 */
int nx_lut_grid_host_load(const char *path,unsigned grid,
                          nx_rgb12 *dst,size_t dst_nodes);
int nx_lut_grid_host_apply(const nx_rgb12 *nodes,unsigned grid,
                           const nx_rgb12 *src,nx_rgb12 *dst,size_t pixels);
#endif
