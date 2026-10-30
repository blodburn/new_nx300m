#include "nx300m_still_pipeline.h"
#include "nx300m_film_menu.h"
#include "nx300m_preview_rgb.h"
#include <stdlib.h>
#include <limits.h>
static uint8_t clamp8(int v){return (uint8_t)(v<0?0:(v>255?255:v));}
static void ycbcr_to_rgb(const uint8_t *ycc,uint8_t *rgb){
    const int y=ycc[0],cb=(int)ycc[1]-128,cr=(int)ycc[2]-128;
    rgb[0]=clamp8(y+((91881*cr+32768)>>16));
    rgb[1]=clamp8(y-((22554*cb+46802*cr+32768)>>16));
    rgb[2]=clamp8(y+((116130*cb+32768)>>16));
}
static void rgb_to_ycbcr(const uint8_t *rgb,uint8_t *ycc){
    const int r=rgb[0],g=rgb[1],b=rgb[2];
    ycc[0]=clamp8((19595*r+38470*g+7471*b+32768)>>16);
    ycc[1]=clamp8(128+((-11059*r-21709*g+32768*b+32768)>>16));
    ycc[2]=clamp8(128+((32768*r-27439*g-5329*b+32768)>>16));
}
int nx_still_filter_inplace(unsigned preset_id,nx_still_format format,
                           uint8_t *pixels,size_t stride,
                           unsigned width,unsigned height){
    if(!pixels||!width||!height||width>16384||height>16384)return NX_STILL_INVALID;
    /* RAW/unsupported path is bypassed, no pixel access and no allocations. */
    if(format==NX_STILL_RAW_OR_UNKNOWN)return NX_STILL_BYPASSED;
    if(format!=NX_STILL_SRGB_RGB888&&format!=NX_STILL_JPEG_YCBCR444)return NX_STILL_BYPASSED;
    if((size_t)width*3u>stride || (size_t)width*3u>SIZE_MAX/2)return NX_STILL_INVALID;
    nx_film_menu selected;nx_film_menu_init(&selected);
    const nx_film_preset *preset=nx_film_by_id(preset_id);
    if(!preset)return NX_STILL_INVALID;
    if(preset->id==0u)return NX_STILL_BYPASSED;/* Samsung original is byte-perfect */
    nx_rgb12 *lut=malloc(sizeof(nx_rgb12)*NX_LUT_COUNT);
    nx_preview_processor *worker=malloc(sizeof(nx_preview_processor));
    uint8_t *row=NULL,*filtered=NULL;
    if(!lut||!worker)goto error;
    selected.selected_id=preset->id;
    if(nx_film_lut_for_menu(&selected,lut)!=0||nx_preview_init(worker)!=0)goto error;
    if(format==NX_STILL_JPEG_YCBCR444){
        row=malloc((size_t)width*3);
        filtered=malloc((size_t)width*3);
        if(!row||!filtered)goto error;
    }
    for(unsigned y=0;y<height;y++){
        uint8_t *dest=pixels+(size_t)y*stride;
        if(format==NX_STILL_SRGB_RGB888){
            if(nx_preview_filter_rgb888(worker,lut,dest,stride,dest,stride,width,1)!=0)goto error;
        }else{
            for(unsigned x=0;x<width;x++)ycbcr_to_rgb(dest+x*3,row+x*3);
            if(nx_preview_filter_rgb888(worker,lut,row,(size_t)width*3,filtered,
               (size_t)width*3,width,1)!=0)goto error;
            for(unsigned x=0;x<width;x++)rgb_to_ycbcr(filtered+x*3,dest+x*3);
        }
    }
    free(row);free(filtered);free(worker);free(lut);
    return NX_STILL_APPLIED;
error:
    free(row);free(filtered);free(worker);free(lut);
    return NX_STILL_INVALID;
}
