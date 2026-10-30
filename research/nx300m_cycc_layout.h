#ifndef NX300M_CYCC_LAYOUT_H
#define NX300M_CYCC_LAYOUT_H
#include <stdint.h>
#include <stddef.h>
/* 36-byte ARM EABI CYcc header from original NX300M libmm-type.so.
 * This represents address metadata, NOT decoded RGB or YCbCr pixels.
 */
typedef struct {
 uint32_t width,height,stride,y0,y1,c0,c1,scan_mode,image_ycc_type;
} nx_native_cycc;
_Static_assert(sizeof(nx_native_cycc)==0x24,"NX300M CYcc header size");
int nx_cycc_make_contiguous(uint32_t base,uint32_t width,uint32_t height,
 uint32_t stride,uint32_t type,nx_native_cycc *out);
int nx_cycc_read_contiguous_header(const void *bytes,size_t size,nx_native_cycc *out);
int nx_cycc_footprint(const nx_native_cycc *hdr,uint32_t *bytes,uint32_t *end_address);
#endif
