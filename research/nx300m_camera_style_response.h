#ifndef NX300M_CAMERA_STYLE_RESPONSE_H
#define NX300M_CAMERA_STYLE_RESPONSE_H
#include <stddef.h>
#include <stdint.h>
/* 13 look IDs share existing single rotary menu.
 * Fujifilm X100VI-style: film-dependent highlight roll-off, Color Chrome
 * approximation, subtle deterministic luminance grain and tailored clarity.
 * Leica Q3-style: smooth tone gradation, profile-dependent local contrast,
 * clean rendering without synthetic grain.
 *
 * ORIGINAL MANUFACTURER ISP ALGORITHMS NOT RECOVERED. This independent study
 * runs AFTER the existing color LUT + sRGB quality enhancement on HOST RGB888.
 * No runtime sliders or extra menu positions.
 */
int nx_camera_style_response_rgb888(unsigned preset_id,
                                  uint8_t *pixels,size_t stride,
                                  unsigned width,unsigned height);
/* Same fixed rendering, but caches only three original luma rows. The
 * source pixels must be host-owned mutable RGB888, not camera DMA memory.
 * Returns 1 for Original/no-op, -1 for invalid input/allocation failure.
 */
int nx_camera_style_response_rgb888_streaming(unsigned preset_id,
                                             uint8_t *pixels,size_t stride,
                                             unsigned width,unsigned height);

/* Stateless HOST row helpers. luma must describe the UNMODIFIED RGB8 rows
 * before family styling; for y=0, prev=NULL; last row: next=NULL.
 * The global image y coordinate is mandatory for stable grain.
 * Apply only for non-Original IDs; RAW/native DMA is never accepted.
 */
int nx_camera_style_luma_row(const uint8_t *rgb,unsigned width,uint8_t *luma);
int nx_camera_style_apply_row(unsigned preset_id,uint8_t *rgb,unsigned width,
                              unsigned y,unsigned height,
                              const uint8_t *prev_luma,const uint8_t *cur_luma,
                              const uint8_t *next_luma);
#endif
