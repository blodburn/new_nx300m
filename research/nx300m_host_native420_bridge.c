#include "nx300m_host_native420_bridge.h"
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

struct nx_host420_stage {
 unsigned width,height,stride,rows,active,published;
 enum nx_host420_order order;
 uint8_t *frame;
 uint8_t *prior_rgb8;
 size_t frame_bytes;
 nx_native_cycc synthetic;
};

/* BT.601 full-range HOST experiment. Native camera B2Y matrix, color range,
 * gamma domain and CbCr packing are not established from source evidence. */
static uint8_t sat(int a){return (uint8_t)(a<0?0:a>255?255:a);}
static uint8_t channel_y(const uint8_t *p){
 return sat((19595*(int)p[0]+38470*(int)p[1]+7471*(int)p[2]+32768)>>16);
}
static uint8_t channel_cb(const uint8_t *p){
 return sat(128+((-11059*(int)p[0]-21709*(int)p[1]+32768*(int)p[2]+32768)>>16));
}
static uint8_t channel_cr(const uint8_t *p){
 return sat(128+((32768*(int)p[0]-27439*(int)p[1]-5329*(int)p[2]+32768)>>16));
}
nx_host420_stage *nx_host420_create(unsigned w,unsigned h,unsigned stride,
                                    enum nx_host420_order order){
 if(w<4||h<4||(w&1u)||(h&1u)||w>8192||h>8192||
    stride<w||(stride&1u)||stride>16384||
    (order!=NX_HOST420_CBCR_EXPERIMENTAL&&
     order!=NX_HOST420_CRCB_EXPERIMENTAL))return NULL;
 /* Source recovered CYcc default contiguous constructor allocates
  * 2 * stride * height; this is an intentionally overallocated HOST model
  * because only the first h/2 rows of the C region are used as a hypothesis. */
 nx_native_cycc synthetic;
 if(nx_cycc_make_contiguous(UINT32_C(0x10000000),w,h,stride,1,
                            &synthetic)!=0)return NULL;
 size_t total=(size_t)2u*stride*h;
 if(total>SIZE_MAX/2u)return NULL;
 nx_host420_stage *s=calloc(1,sizeof(*s));
 if(!s)return NULL;
 s->frame=malloc(total);
 s->prior_rgb8=malloc((size_t)w*3u);
 if(!s->frame||!s->prior_rgb8){
  free(s->frame);free(s->prior_rgb8);free(s);return NULL;
 }
 s->width=w;s->height=h;s->stride=stride;
 s->frame_bytes=total;s->synthetic=synthetic;s->order=order;
 memset(s->frame,0xa5,total);
 return s;
}
static int begin(void *user,unsigned w,unsigned h,unsigned film){
 nx_host420_stage *s=user;
 if(!s||!film||s->active||s->published||s->width!=w||
    s->height!=h)return -1;
 s->rows=0;s->active=1;
 memset(s->frame,0xa5,s->frame_bytes);
 memset(s->prior_rgb8,0,(size_t)w*3u);
 return 0;
}
static int write_row(void *user,unsigned y,const uint8_t *rgb,size_t bytes){
 nx_host420_stage *s=user;
 if(!s||!s->active||!rgb||y!=s->rows||
    bytes!=(size_t)s->width*3u)return -1;
 uint8_t *yline=s->frame+(size_t)y*s->stride;
 for(unsigned x=0;x<s->width;x++)
  yline[x]=channel_y(rgb+(size_t)x*3u);
 if(!(y&1u)){
  memcpy(s->prior_rgb8,rgb,bytes);
 }else{
  uint8_t *c=s->frame+(size_t)s->stride*s->height+
             (size_t)(y/2u)*s->stride;
  for(unsigned x=0;x<s->width;x+=2u){
   unsigned cb=0,cr=0;
   for(unsigned k=0;k<2;k++){
    const uint8_t *a=s->prior_rgb8+3u*(x+k);
    const uint8_t *b=rgb+3u*(x+k);
    cb+=channel_cb(a)+channel_cb(b);
    cr+=channel_cr(a)+channel_cr(b);
   }
   const uint8_t c1=(uint8_t)((cb+2u)/4u);
   const uint8_t c2=(uint8_t)((cr+2u)/4u);
   c[x+(s->order==NX_HOST420_CRCB_EXPERIMENTAL?1u:0u)]=c1;
   c[x+(s->order==NX_HOST420_CRCB_EXPERIMENTAL?0u:1u)]=c2;
  }
 }
 s->rows++;
 return 0;
}
static int commit(void *user){
 nx_host420_stage *s=user;
 if(!s||!s->active||s->published||s->rows!=s->height)return -1;
 s->active=0;s->published=1;return 0;
}
static void abort_image(void *user){
 nx_host420_stage *s=user;
 if(!s)return;
 s->active=0;s->published=0;s->rows=0;
 if(s->frame)memset(s->frame,0,s->frame_bytes);
 if(s->prior_rgb8)memset(s->prior_rgb8,0,(size_t)s->width*3u);
}
nx_bayer_rgb8_sink nx_host420_sink(nx_host420_stage *s){
 nx_bayer_rgb8_sink cb={begin,write_row,commit,abort_image,s};
 return cb;
}
const uint8_t *nx_host420_published(const nx_host420_stage *s,
                                    size_t *bytes,
                                    nx_native_cycc *synthetic_header){
 if(!s||!s->published||s->active||!bytes||!synthetic_header)return NULL;
 *bytes=s->frame_bytes;*synthetic_header=s->synthetic;
 return s->frame;
}
void nx_host420_destroy(nx_host420_stage *s){
 if(!s)return;
 if(s->frame)memset(s->frame,0,s->frame_bytes);
 free(s->frame);free(s->prior_rgb8);free(s);
}
