#include "nx300m_host_capture_copy_adapter.h"
#include "nx300m_film_menu.h"
#include "nx300m_still_pipeline.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

int nx_host_capture_apply_copy(const nx_host_copy_job *job){
 if(!job || !job->config_path) return NX_HOST_COPY_INVALID;
 nx_film_menu menu;
 nx_film_menu_init(&menu);
 /* Missing/corrupted config is original bypass, never an experimental mode. */
 if(nx_film_menu_load(&menu,job->config_path)!=0)
  menu.selected_id=0;
 const nx_pw_route_request req={
  menu.selected_id,job->source,job->capture_mode,job->rgb888_validated
 };
 nx_pw_route_plan plan;
 const nx_pw_route route=nx_pw_plan_capture(&req,&plan);
 if(route==NX_PW_ROUTE_REFUSE) return NX_HOST_COPY_INVALID;
 /* Never publish or modify anything for Original, including device source. */
 if(route==NX_PW_ROUTE_ORIGINAL_UNCHANGED) return NX_HOST_COPY_BYPASSED;
 if(route!=NX_PW_ROUTE_HOST_RGB_EFFECT ||
    !plan.use_host_rgb_frame || !plan.requires_independent_jpeg_output ||
    plan.may_change_samsung_picture_wizard || plan.may_write_native_ycc ||
    plan.may_write_raw || !plan.original_vendor_mode_must_be_preserved)
  return NX_HOST_COPY_INVALID;
 /* Check ALL dimensions and byte spans before reading or writing a byte.
  * The existing still filter is bounded by dimensions/stride, not by a
  * caller-provided length, so this adapter adds that required guard. */
 if(!job->src || !job->dst || !job->width || !job->height ||
    job->width>16384u || job->height>16384u) return NX_HOST_COPY_INVALID;
 const size_t min_row=(size_t)job->width*3u;
 if(job->stride<min_row || job->stride>SIZE_MAX/job->height)
  return NX_HOST_COPY_INVALID;
 const size_t span=job->stride*job->height;
 /* Cap temporary allocation; this is an offline RGB frame, not DMA memory.
  * Allows a 20 MP RGB888 copy, but rejects oversized allocation requests. */
 if(span>(size_t)128u*1024u*1024u ||
    span>job->src_bytes || span>job->dst_bytes ||
    span>UINTPTR_MAX) return NX_HOST_COPY_INVALID;
 const uintptr_t a=(uintptr_t)job->src;
 const uintptr_t b=(uintptr_t)job->dst;
 if(a>UINTPTR_MAX-span || b>UINTPTR_MAX-span ||
    (a<b+span && b<a+span))
  return NX_HOST_COPY_INVALID;
 uint8_t *stage=malloc(span);
 if(!stage) return NX_HOST_COPY_INVALID;
 memcpy(stage,job->src,span);
 int status=nx_still_filter_inplace(plan.validated_film_id,
     NX_STILL_SRGB_RGB888,stage,job->stride,job->width,job->height);
 if(status!=NX_STILL_APPLIED){
  free(stage);
  return NX_HOST_COPY_INVALID;
 }
 /* The only user-supplied write happens after a complete successful filter. */
 memcpy(job->dst,stage,span);
 free(stage);
 return NX_HOST_COPY_APPLIED;
}
