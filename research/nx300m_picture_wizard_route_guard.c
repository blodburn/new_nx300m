#include "nx300m_picture_wizard_route_guard.h"
#include "nx300m_film_menu.h"
#include <string.h>

nx_pw_route nx_pw_plan_capture(const nx_pw_route_request *r,
                               nx_pw_route_plan *out){
 if(!out)return NX_PW_ROUTE_REFUSE;
 memset(out,0,sizeof(*out));
 out->route=NX_PW_ROUTE_REFUSE;
 out->original_vendor_mode_must_be_preserved=1;
 /* Fail-closed contract: vendor controls NEVER written by this guard. */
 if(!r || (r->source!=NX_PW_SOURCE_HOST_COPIED_FRAME &&
            r->source!=NX_PW_SOURCE_CAMERA_DEVICE) ||
    (r->mode!=NX_PW_CAPTURE_JPEG_ONLY &&
     r->mode!=NX_PW_CAPTURE_RAW_ONLY &&
     r->mode!=NX_PW_CAPTURE_RAW_PLUS_JPEG))
  return NX_PW_ROUTE_REFUSE;
 const nx_film_preset *preset=nx_film_by_id(r->film_preset_id);
 if(!preset)return NX_PW_ROUTE_REFUSE;
 out->validated_film_id=preset->id;
 if(preset->id==0){
  /* Preserve original camera selection + RAW/JPEG and EXIF behavior.
   * DO NOT map preset ID 0 to any specific native Samsung mode number. */
  out->route=NX_PW_ROUTE_ORIGINAL_UNCHANGED;
  return out->route;
 }
 /* Experimental mode needs a validated, independently owned RGB888
  * frame and an explicit HOST-only simulation context.
  * Unknown camera ISR/IPC/ISP/capture pipeline is always blocked. */
 if(r->source!=NX_PW_SOURCE_HOST_COPIED_FRAME ||
    r->mode==NX_PW_CAPTURE_RAW_ONLY ||
    r->host_rgb888_validated!=1)
  return NX_PW_ROUTE_REFUSE;
 out->route=NX_PW_ROUTE_HOST_RGB_EFFECT;
 out->use_host_rgb_frame=1;
 out->requires_independent_jpeg_output=1;
 return out->route;
}
