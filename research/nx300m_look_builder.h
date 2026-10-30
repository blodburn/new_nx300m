/* Independent camera-neutral 18-cube LUT builder for future NX300M integration.
 * No proprietary Fujifilm coefficients; parameters must be calibrated from real samples.
 */
#ifndef NX300M_LOOK_BUILDER_H
#define NX300M_LOOK_BUILDER_H
#include "nx300m_lut18.h"
typedef struct {
    /* Row-major matrix * linear RGB input; calibrated separately per sensor/lighting. */
    float sensor_to_reference[9];
    float film_color_matrix[9];
    float sensor_offset[3];
    float saturation;
    float shadow_gain;
    float highlight_gain;
    float gamma;
} nx_look_params;
void nx_look_params_identity(nx_look_params *p);
/* Writes exactly NX_LUT_COUNT nodes, preserving 12-bit RGB & reserved=0. */
int nx_look_build_lut18(nx_rgb12 *dst, const nx_look_params *p);
#endif
