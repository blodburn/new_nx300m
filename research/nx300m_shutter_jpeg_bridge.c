#include "nx300m_shutter_jpeg_bridge.h"
#include "nx300m_still_enhanced.h"
#include "nx300m_film_menu.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
int nx_shutter_save_selected(const nx_shutter_request *req,
                             nx_shutter_result *result){
 if(!req||!result)return -1;
 memset(result,0,sizeof(*result));
 if(req->mode!=NX_SAVE_JPEG_ONLY&&req->mode!=NX_SAVE_RAW_AND_JPEG&&
    req->mode!=NX_SAVE_RAW_ONLY)return -1;
 const int want_raw=req->mode!=NX_SAVE_JPEG_ONLY;
 const int want_jpeg=req->mode!=NX_SAVE_RAW_ONLY;
 if(want_raw&&(!req->write_raw||!req->opaque_raw||!req->raw_bytes))return -1;
 if(want_jpeg&&(!req->write_jpeg||!req->decoded_rgb||
    !req->width||!req->height||req->width>16384||req->height>16384||
    req->rgb_stride<(size_t)req->width*3u||
    (size_t)req->height>SIZE_MAX/req->rgb_stride||
    req->rgb_bytes<req->rgb_stride*(size_t)req->height))return -1;

 /* RAW is orthogonal to Film Simulator: never handled by a pixel LUT.
  * A RAW_ONLY request does not need decoded RGB or a menu setting. */
 if(want_raw){
    if(req->write_raw(req->opaque_raw,req->raw_bytes,req->user)!=0)return -1;
    result->raw_saved=1;
 }
 if(!want_jpeg)return 0;

 nx_film_menu chosen;
 nx_film_menu_init(&chosen);
 if(req->saved_film_setting&&
    nx_film_menu_load(&chosen,req->saved_film_setting)!=0)
    result->original_fallback=1;
 result->selected_film_id=chosen.selected_id;
 const uint8_t *to_encode=req->decoded_rgb;
 uint8_t *stage=NULL;
 const size_t frame_bytes=req->rgb_stride*(size_t)req->height;
 if(chosen.selected_id!=0){
    stage=(uint8_t*)malloc(frame_bytes);
    if(stage){
       memcpy(stage,req->decoded_rgb,frame_bytes);
       const int rc=nx_still_filter_enhanced_inplace(chosen.selected_id,
                   NX_STILL_SRGB_RGB888,stage,req->rgb_stride,
                   req->width,req->height);
       if(rc==NX_STILL_APPLIED){
          to_encode=stage;
          result->applied_film=1;
       }else result->original_fallback=1;
    }else result->original_fallback=1;
 }
 /* Exactly ONE encoder call for this shutter press; no separate sidecar JPG.
  * The callback owns actual JPEG compression, original EXIF/MakerNotes
  * preservation and file commit. Not implemented by this host bridge. */
 const int saved=req->write_jpeg(to_encode,req->rgb_stride,
                                 req->width,req->height,req->user);
 free(stage);
 if(saved!=0)return -1;
 result->jpeg_saved=1;
 return 0;
}
