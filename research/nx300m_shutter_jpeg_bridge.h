#ifndef NX300M_SHUTTER_JPEG_BRIDGE_H
#define NX300M_SHUTTER_JPEG_BRIDGE_H
#include <stddef.h>
#include <stdint.h>
/* HOST / abstract test adapter for user-selected NX300M still capture.
 * NOT an on-camera firmware hook and NOT a JPEG encoder implementation.
 * The native codec must provide an independently verified writable RGB888
 * buffer and an encoder callable through these interfaces.
 * Actual Samsung ISP main YCC is type1 420 with mode7 addresses: do NOT
 * pretend it is RGB888. No writes to camera DMA or firmware from this API.
 */
typedef enum {
 NX_SAVE_JPEG_ONLY=0, NX_SAVE_RAW_AND_JPEG=1, NX_SAVE_RAW_ONLY=2
} nx_save_mode;
typedef int (*nx_save_jpeg_cb)(const unsigned char *rgb,size_t stride,
                                unsigned width,unsigned height,void *user);
typedef int (*nx_save_raw_cb)(const void *opaque_raw,size_t raw_size,void *user);
typedef struct {
 nx_save_mode mode;
 const char *saved_film_setting; /* existing one-wheel 13 preset storage */
 const uint8_t *decoded_rgb; /* known packed sRGB888 in host RAM */
 size_t rgb_bytes;
 size_t rgb_stride;
 unsigned width,height;
 const void *opaque_raw; /* no parsing/alteration of SRW bytes */
 size_t raw_bytes;
 nx_save_jpeg_cb write_jpeg;
 nx_save_raw_cb write_raw;
 void *user;
} nx_shutter_request;
typedef struct {
 unsigned jpeg_saved; /* true only if codec callback returned success */
 unsigned raw_saved;
 unsigned selected_film_id;
 unsigned applied_film;
 unsigned original_fallback;
} nx_shutter_result;
/* Returns 0 if all requested saves completed; -1 if any save failed or
 * request invalid. Never calls RAW saver under JPEG_ONLY; processes only one
 * chosen look into at most one JPEG (not 13 files). If film filter fails,
 * JPEG is encoded from unmodified source RGB via a single callback.
 * RAW+JPEG RAW saver is called before JPEG, and RAW bytes are never changed.
 */
int nx_shutter_save_selected(const nx_shutter_request *request,
                             nx_shutter_result *result);
#endif
