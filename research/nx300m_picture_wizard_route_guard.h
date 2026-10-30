#ifndef NX300M_PICTURE_WIZARD_ROUTE_GUARD_H
#define NX300M_PICTURE_WIZARD_ROUTE_GUARD_H
#include <stdint.h>
/*
 * Portable, pure planner. No vendor function addresses or camera API calls.
 * Camera source NEVER receives an experimental Film Simulator ID.
 * Original mode bypasses without altering Samsung's Picture Wizard mode.
 *
 * "Host simulation" means explicitly supplied non-camera image bytes. It
 * is NOT a camera runtime mode, and does not authorize native JPEG/RAW hooks.
 */
typedef enum {
 NX_PW_SOURCE_HOST_COPIED_FRAME=1,
 NX_PW_SOURCE_CAMERA_DEVICE=2
} nx_pw_source;
typedef enum {
 NX_PW_CAPTURE_JPEG_ONLY=1,
 NX_PW_CAPTURE_RAW_ONLY=2,
 NX_PW_CAPTURE_RAW_PLUS_JPEG=3
} nx_pw_capture_mode;
typedef enum {
 NX_PW_ROUTE_REFUSE=-1,
 NX_PW_ROUTE_ORIGINAL_UNCHANGED=0,
 NX_PW_ROUTE_HOST_RGB_EFFECT=1
} nx_pw_route;
typedef struct {
 unsigned film_preset_id;
 nx_pw_source source;
 nx_pw_capture_mode mode;
 int host_rgb888_validated;
} nx_pw_route_request;
typedef struct {
 nx_pw_route route;
 unsigned validated_film_id;
 unsigned original_vendor_mode_must_be_preserved;
 unsigned may_change_samsung_picture_wizard;
 unsigned may_write_native_ycc;
 unsigned may_write_raw;
 unsigned use_host_rgb_frame;
 unsigned requires_independent_jpeg_output;
} nx_pw_route_plan;
/* Rejects unknown IDs, unknown capture formats, and any attempt to apply
 * experimental looks to a live camera or directly to unvalidated RAW/YCC.
 * A host RAW+JPEG job may process the independent JPEG RGB copy only.
 * Caller is responsible for publishing only validated destination formats.
 */
nx_pw_route nx_pw_plan_capture(const nx_pw_route_request *request,
                               nx_pw_route_plan *plan);
#endif
