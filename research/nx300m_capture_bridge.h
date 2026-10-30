#ifndef NX300M_CAPTURE_BRIDGE_H
#define NX300M_CAPTURE_BRIDGE_H
#include "nx300m_still_pipeline.h"
/* Offline bridge between a saved 13-style rotary menu selection and
 * a decoded/validated capture buffer. DO NOT attach directly to CCapImage:
 * Samsung NX300M native descriptors and YCC layout are not verified yet.
 */
int nx_capture_apply_saved_look(const char *config_path,nx_still_format format,
                               unsigned char *pixels,size_t stride,
                               unsigned width,unsigned height);
#endif
