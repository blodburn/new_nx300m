#ifndef NX300M_STILL_PIPELINE_H
#define NX300M_STILL_PIPELINE_H
#include <stddef.h>
#include <stdint.h>
/* Camera-neutral AFTER-capture buffer proof-of-concept. Target format is
 * not proven for the original Samsung CCapImage / CYcc memory. Do not hook
 * original firmware until image descriptors, ownership and matrix confirmed.
 */
typedef enum {
 NX_STILL_RAW_OR_UNKNOWN=0,  /* STRICT BYPASS for RAW/unsupported */
 NX_STILL_SRGB_RGB888=1,     /* packed sRGB R,G,B bytes */
 NX_STILL_JPEG_YCBCR444=2   /* packed full-range JFIF-style BT.601 Y,Cb,Cr */
} nx_still_format;
enum { NX_STILL_APPLIED=0, NX_STILL_BYPASSED=1, NX_STILL_INVALID=-1 };
/* In-place effect on one camera capture frame. Never tries to decode .SRW or
 * modify the JPEG bitstream; a codec/native frame adapter is still required.
 */
int nx_still_filter_inplace(unsigned preset_id,nx_still_format format,
                           uint8_t *pixels,size_t stride,
                           unsigned width,unsigned height);
#endif
