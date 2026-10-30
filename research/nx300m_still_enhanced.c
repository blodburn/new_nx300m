#include "nx300m_still_enhanced.h"
#include "nx300m_image_enhance.h"
#include "nx300m_camera_style_response.h"
#include "nx300m_film_menu.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
int nx_still_filter_enhanced_inplace(unsigned id,nx_still_format fmt,
                                    uint8_t *data,size_t stride,
                                    unsigned width,unsigned height){
    if(!data||!width||!height||width>16384||height>16384)return NX_STILL_INVALID;
    if(fmt==NX_STILL_RAW_OR_UNKNOWN)return NX_STILL_BYPASSED;
    if(fmt!=NX_STILL_SRGB_RGB888)return NX_STILL_BYPASSED;
    const nx_film_preset *preset=nx_film_by_id(id);
    if(!preset)return NX_STILL_INVALID;
    if(preset->id==0)return NX_STILL_BYPASSED;
    if(stride<3u*(size_t)width||
       (size_t)height>SIZE_MAX/stride)return NX_STILL_INVALID;
    size_t count=stride*(size_t)height;
    uint8_t *scratch=malloc(count);
    if(!scratch)return NX_STILL_INVALID;
    memcpy(scratch,data,count);
    int rc=nx_still_filter_inplace(id,fmt,scratch,stride,width,height);
    if(rc==NX_STILL_APPLIED&&
       nx_image_enhance_rgb888(scratch,stride,width,height)!=0)
        rc=NX_STILL_INVALID;
    if(rc==NX_STILL_APPLIED &&
       nx_camera_style_response_rgb888(id,scratch,stride,width,height)!=0)
        rc=NX_STILL_INVALID;
    if(rc==NX_STILL_APPLIED)memcpy(data,scratch,count);
    free(scratch);
    return rc;
}
