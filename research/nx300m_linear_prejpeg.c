#include "nx300m_linear_prejpeg.h"
#include "nx300m_film_menu.h"
#include "nx300m_preview_rgb.h"
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
static float shoulder(float x,float knee){
 if(x<=0.f)return 0.f;
 if(x<=knee)return x;
 /* derivative is 1 at knee; carries linear detail above nominal display
  * white while converging asymptotically to 1.0 */
 const float rem=1.f-knee;
 return knee+rem*(1.f-expf(-(x-knee)/rem));
}
struct nx_linear_prejpeg_work {
 nx_linear_params params;
 nx_rgb12 *lut;
 nx_preview_processor conv;
 float inv;
};
int nx_linear_prejpeg_prepare(nx_linear_prejpeg_work **out,unsigned id,
                             const nx_linear_params *params){
 if(!out)return -1;
 *out=NULL;
 if(!params||params->white_level<=params->black_level||
    !isfinite(params->exposure)||params->exposure<0.25f||params->exposure>4.f||
    !isfinite(params->highlight_knee)||params->highlight_knee<0.5f||
    params->highlight_knee>0.95f)return -1;
 for(unsigned c=0;c<3;c++)
  if(!isfinite(params->white_balance[c])||params->white_balance[c]<0.25f||
     params->white_balance[c]>4.f)return -1;
 const nx_film_preset *preset=nx_film_by_id(id);
 if(!preset)return -1;
 if(preset->id==0)return 1;
 nx_linear_prejpeg_work *work=calloc(1,sizeof(*work));
 if(!work)return -1;
 work->lut=malloc(NX_LUT_COUNT*sizeof(*work->lut));
 if(!work->lut){free(work);return -1;}
 nx_film_menu menu;nx_film_menu_init(&menu);menu.selected_id=preset->id;
 if(nx_film_lut_for_menu(&menu,work->lut)!=0||
    nx_preview_init(&work->conv)!=0){
  nx_linear_prejpeg_release(work);return -1;
 }
 work->params=*params;
 work->inv=1.f/(float)(params->white_level-params->black_level);
 *out=work;
 return 0;
}
void nx_linear_prejpeg_release(nx_linear_prejpeg_work *work){
 if(work){free(work->lut);free(work);}
}
int nx_linear_prejpeg_process_row(const nx_linear_prejpeg_work *work,
                                 const uint16_t *src,uint8_t *dst,
                                 unsigned width){
 if(!work||!src||!dst||!width||width>16384)return -1;
 const nx_linear_params *params=&work->params;
 for(unsigned x=0;x<width;x++){
  nx_rgb12 linear={0,0,0,0},filmed;
  uint16_t *arr[3]={&linear.r,&linear.g,&linear.b};
  for(unsigned c=0;c<3;c++){
   const int code=(int)src[3u*x+c]-(int)params->black_level;
   const float radiance=(float)(code>0?code:0)*work->inv*
                        params->white_balance[c]*params->exposure;
   *arr[c]=(uint16_t)(4095.f*shoulder(radiance,params->highlight_knee)+0.5f);
  }
  if(nx_lut18_apply(work->lut,&linear,&filmed,1)!=0)return -1;
  dst[3u*x+0]=work->conv.encode_srgb[filmed.r];
  dst[3u*x+1]=work->conv.encode_srgb[filmed.g];
  dst[3u*x+2]=work->conv.encode_srgb[filmed.b];
 }
 return 0;
}
int nx_linear_prejpeg_film_rgb16(const uint16_t *src,size_t src_stride_samples,
                                uint8_t *dst,size_t dst_stride_bytes,
                                unsigned width,unsigned height,
                                unsigned id,const nx_linear_params *params){
 if(!src||!dst||!params||!width||!height||width>16384||height>16384||
    src_stride_samples<(size_t)width*3u||dst_stride_bytes<(size_t)width*3u||
    (size_t)height>SIZE_MAX/src_stride_samples||
    (size_t)height>SIZE_MAX/sizeof(uint16_t)/src_stride_samples||
    (size_t)height>SIZE_MAX/dst_stride_bytes||
    !params->white_level||params->white_level<=params->black_level||
    !isfinite(params->exposure)||params->exposure<0.25f||params->exposure>4.f||
    !isfinite(params->highlight_knee)||params->highlight_knee<0.5f||
    params->highlight_knee>0.95f)return -1;
 for(unsigned c=0;c<3;c++)
   if(!isfinite(params->white_balance[c])||params->white_balance[c]<0.25f||
      params->white_balance[c]>4.f)return -1;
 const nx_film_preset *preset=nx_film_by_id(id);
 if(!preset)return -1;
 if(preset->id==0)return 1; /* Samsung native original path, not synthesized */
 const uintptr_t sa=(uintptr_t)src,da=(uintptr_t)dst;
 const size_t source_size=(size_t)height*src_stride_samples*sizeof(uint16_t);
 const size_t dest_size=(size_t)height*dst_stride_bytes;
 if(sa+source_size<sa||da+dest_size<da||
    !(sa+source_size<=da||da+dest_size<=sa))return -1;

 nx_linear_prejpeg_work *work=NULL;
 if(nx_linear_prejpeg_prepare(&work,id,params)!=0)return -1;
 for(unsigned y=0;y<height;y++){
  const uint16_t *s=src+(size_t)y*src_stride_samples;
  uint8_t *d=dst+(size_t)y*dst_stride_bytes;
  if(nx_linear_prejpeg_process_row(work,s,d,width)!=0){
   nx_linear_prejpeg_release(work);return -1;
  }
 }
 nx_linear_prejpeg_release(work);return 0;
}
