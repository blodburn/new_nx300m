#include "nx300m_bayer_prejpeg.h"
#include "nx300m_film_menu.h"
#include "nx300m_camera_style_response.h"
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>

static const unsigned char cfa[4][4]={
 {0,1,1,2}, /* RGGB */
 {2,1,1,0}, /* BGGR */
 {1,0,2,1}, /* GRBG */
 {1,2,0,1}  /* GBRG */
};
static unsigned color(const nx_bayer_calibration *c,unsigned x,unsigned y){
 return cfa[c->pattern][((y&1u)<<1u)|(x&1u)];
}
static int span_overlaps(const void *a,size_t an,const void *b,size_t bn){
 uintptr_t p=(uintptr_t)a,q=(uintptr_t)b;
 if(p>UINTPTR_MAX-an||q>UINTPTR_MAX-bn)return 1;
 return p<q+bn&&q<p+an;
}
static int valid(const uint16_t *src,size_t n,size_t ss,
                 const uint16_t *dst,size_t dn,size_t ds,
                 unsigned w,unsigned h,const nx_bayer_calibration *c){
 if(!src||!dst||!c||c->pattern>NX_BAYER_GBRG||
    w<4u||h<4u||w>8192u||h>8192u||
    ss<w||ds<(size_t)w*3u||ss>SIZE_MAX/h||ds>SIZE_MAX/h||
    n<ss*h||dn<ds*h||ss*h>SIZE_MAX/sizeof(uint16_t)||
    ds*h>SIZE_MAX/sizeof(uint16_t)||
    span_overlaps(src,ss*h*sizeof(uint16_t),dst,ds*h*sizeof(uint16_t)))
  return 0;
 for(unsigned i=0;i<4;i++){
  if(c->white[i]<=c->black[i])return 0;
 }
 return 1;
}
static uint16_t normal(const uint16_t *src,size_t stride,
                       unsigned x,unsigned y,const nx_bayer_calibration *c){
 unsigned ix=((y&1u)<<1u)|(x&1u);
 uint32_t raw=src[(size_t)y*stride+x],black=c->black[ix],white=c->white[ix];
 if(raw<=black)return 0;
 if(raw>=white)return UINT16_MAX;
 const uint32_t range=white-black;
 return (uint16_t)(((raw-black)*65535u+range/2u)/range);
}
static uint16_t sample(const uint16_t *src,size_t ss,unsigned w,unsigned h,
                       unsigned x,unsigned y,const nx_bayer_calibration *c){
 uint16_t v=normal(src,ss,x,y,c),near[4];
 if(!c->defect_threshold)return v;
 unsigned k=0;
 if(x>=2)near[k++]=normal(src,ss,x-2,y,c);
 if(x+2<w)near[k++]=normal(src,ss,x+2,y,c);
 if(y>=2)near[k++]=normal(src,ss,x,y-2,c);
 if(y+2<h)near[k++]=normal(src,ss,x,y+2,c);
 if(k<3)return v;
 for(unsigned i=1;i<k;i++){
  uint16_t t=near[i];unsigned j=i;
  while(j&&near[j-1]>t){near[j]=near[j-1];j--;}
  near[j]=t;
 }
 const unsigned t=c->defect_threshold;
 if((unsigned)near[k-1]-near[0]>t)return v; /* protect edges */
 if((unsigned)v>(unsigned)near[k-1]+t||
    (unsigned)v+t<(unsigned)near[0]){
  return (uint16_t)(((unsigned)near[(k-1)/2]+near[k/2]+1u)/2u);
 }
 return v;
}
typedef struct {unsigned value,gradient,count;} nx_axis;
static nx_axis axis(const uint16_t *src,size_t ss,unsigned w,unsigned h,
                    unsigned x,unsigned y,int dx,int dy,
                    const nx_bayer_calibration *c){
 unsigned s[2],n=0;
 for(int sign=-1;sign<=1;sign+=2){
  int xx=(int)x+sign*dx,yy=(int)y+sign*dy;
  if(xx>=0&&yy>=0&&(unsigned)xx<w&&(unsigned)yy<h)
   s[n++]=sample(src,ss,w,h,(unsigned)xx,(unsigned)yy,c);
 }
 nx_axis a={0,UINT_MAX,n};
 if(n){a.value=n==2?(s[0]+s[1]+1u)/2u:s[0];
       if(n==2)a.gradient=s[0]>s[1]?s[0]-s[1]:s[1]-s[0];}
 return a;
}
static unsigned choose(nx_axis a,nx_axis b){
 if(!a.count)return b.value;
 if(!b.count)return a.value;
 if(a.count==1&&b.count==2)return b.value;
 if(b.count==1&&a.count==2)return a.value;
 if(a.gradient<b.gradient)return a.value;
 if(b.gradient<a.gradient)return b.value;
 return (a.value+b.value+1u)/2u;
}
static uint16_t reconstruct(const uint16_t *src,size_t ss,unsigned w,unsigned h,
                             unsigned x,unsigned y,unsigned target,
                             const nx_bayer_calibration *c){
 unsigned here=color(c,x,y);
 if(here==target)return sample(src,ss,w,h,x,y,c);
 if(here==1){ /* Red/blue neighbours lie along one known CFA axis. */
  int horizontal=(color(c,x^1u,y)==target);
  nx_axis a=axis(src,ss,w,h,x,y,horizontal, !horizontal,c);
  return (uint16_t)a.value;
 }
 if(target==1){ /* Edge-directed green at red/blue. */
  nx_axis a=axis(src,ss,w,h,x,y,1,0,c);
  nx_axis b=axis(src,ss,w,h,x,y,0,1,c);
  return (uint16_t)choose(a,b);
 }
 /* Opposite chroma at red/blue: edge-directed diagonal interpolation. */
 nx_axis a=axis(src,ss,w,h,x,y,1,1,c);
 nx_axis b=axis(src,ss,w,h,x,y,1,-1,c);
 return (uint16_t)choose(a,b);
}
int nx_bayer_to_rgb16(const uint16_t *src,size_t src_samples,size_t ss,
                      uint16_t *dst,size_t dst_samples,size_t ds,
                      unsigned w,unsigned h,const nx_bayer_calibration *cal){
 if(!valid(src,src_samples,ss,dst,dst_samples,ds,w,h,cal))return -1;
 for(unsigned y=0;y<h;y++){
  uint16_t *row=dst+(size_t)y*ds;
  for(unsigned x=0;x<w;x++)
   for(unsigned ch=0;ch<3;ch++)
    row[3u*x+ch]=reconstruct(src,ss,w,h,x,y,ch,cal);
 }
 return 0;
}
int nx_bayer_prejpeg_film(const uint16_t *src,size_t src_samples,size_t ss,
                          uint8_t *dst,size_t dst_bytes,size_t ds,
                          unsigned w,unsigned h,
                          const nx_bayer_calibration *cal,
                          const nx_linear_params *look,unsigned film_id){
 if(!src||!dst||!cal||!look||!nx_film_by_id(film_id)||w<4||h<4||
    w>8192||h>8192||ss<w||ss>SIZE_MAX/h||src_samples<ss*h||
    ds<(size_t)w*3u||ds>SIZE_MAX/h||dst_bytes<ds*h||
    ss*h>SIZE_MAX/sizeof(uint16_t)||
    span_overlaps(src,ss*h*sizeof(uint16_t),dst,ds*h)||
    look->black_level!=0||look->white_level!=UINT16_MAX)return -1;
 for(unsigned i=0;i<4;i++)if(cal->white[i]<=cal->black[i])return -1;
 if(cal->pattern>NX_BAYER_GBRG)return -1;
 if(film_id==0)return 1; /* Samsung original, no re-encoding */
 const size_t stride=(size_t)w*3u,n=stride*h;
 uint16_t *rgb=malloc(n*sizeof(*rgb));
 if(!rgb)return -1;
 int rc=nx_bayer_to_rgb16(src,src_samples,ss,rgb,n,stride,w,h,cal);
 if(rc==0)rc=nx_linear_prejpeg_film_rgb16(rgb,stride,dst,ds,w,h,film_id,look);
 /* Host-only film-family rendering after high-bit work. No JPEG recode.
  * Caller must discard staged dst on any negative result. */
 if(rc==0 && nx_camera_style_response_rgb888(film_id,dst,ds,w,h)!=0)rc=-1;
 free(rgb);
 return rc;
}

int nx_bayer_prejpeg_film_streaming(const uint16_t *src,size_t src_samples,
                                    size_t ss,uint8_t *dst,size_t dst_bytes,
                                    size_t ds,unsigned w,unsigned h,
                                    const nx_bayer_calibration *cal,
                                    const nx_linear_params *look,unsigned film_id){
 /* Reject bad sizes, aliasing and calibration BEFORE writing anything.
  * This adapter intentionally makes no attempt to decode Samsung SRW. */
 if(!src||!dst||!cal||!look||!nx_film_by_id(film_id)||w<4||h<4||
    w>8192||h>8192||ss<w||ss>SIZE_MAX/h||src_samples<ss*h||
    ds<(size_t)w*3u||ds>SIZE_MAX/h||dst_bytes<ds*h||
    ss*h>SIZE_MAX/sizeof(uint16_t)||
    span_overlaps(src,ss*h*sizeof(uint16_t),dst,ds*h)||
    look->black_level!=0||look->white_level!=UINT16_MAX||
    cal->pattern>NX_BAYER_GBRG)return -1;
 for(unsigned i=0;i<4;i++)
  if(cal->white[i]<=cal->black[i])return -1;
 /* Prepare also checks exposure, knee and WB before destination is touched. */
 nx_linear_prejpeg_work *work=NULL;
 int rc=nx_linear_prejpeg_prepare(&work,film_id,look);
 if(rc!=0)return rc;
 const size_t n=(size_t)w*3u;
 uint16_t *row=malloc(n*sizeof(*row));
 if(!row){nx_linear_prejpeg_release(work);return -1;}
 for(unsigned y=0;y<h;y++){
  for(unsigned x=0;x<w;x++)
   for(unsigned ch=0;ch<3;ch++)
    row[3u*x+ch]=reconstruct(src,ss,w,h,x,y,ch,cal);
  rc=nx_linear_prejpeg_process_row(work,row,dst+(size_t)y*ds,w);
  if(rc!=0)break;
 }
 free(row);
 nx_linear_prejpeg_release(work);
 if(rc==0 && nx_camera_style_response_rgb888_streaming(film_id,dst,ds,w,h)!=0)
  rc=-1;
 return rc;
}

/* The sole full-frame storage required by this host adapter is the read-only
 * Bayer source supplied by the caller. No JPEG storage, codec, or DMA hook. */
static int emit_bayer_row(const uint16_t *src,size_t ss,unsigned w,unsigned h,
                          unsigned y,const nx_bayer_calibration *cal,
                          const nx_linear_prejpeg_work *work,
                          uint16_t *linear_row,uint8_t *rgb_row,uint8_t *luma){
 for(unsigned x=0;x<w;x++)
  for(unsigned c=0;c<3;c++)
   linear_row[3u*x+c]=reconstruct(src,ss,w,h,x,y,c,cal);
 if(nx_linear_prejpeg_process_row(work,linear_row,rgb_row,w)!=0)return -1;
 return nx_camera_style_luma_row(rgb_row,w,luma);
}
int nx_bayer_prejpeg_emit_rows(const uint16_t *src,size_t src_samples,
                               size_t ss,unsigned w,unsigned h,
                               const nx_bayer_calibration *cal,
                               const nx_linear_params *look,unsigned id,
                               const nx_bayer_rgb8_sink *sink){
 if(!src||!cal||!look||!nx_film_by_id(id)||w<4||h<4||
    w>8192||h>8192||ss<w||ss>SIZE_MAX/h||
    src_samples<ss*h||ss*h>SIZE_MAX/sizeof(uint16_t)||
    cal->pattern>NX_BAYER_GBRG||
    look->black_level!=0||look->white_level!=UINT16_MAX)return -1;
 for(unsigned i=0;i<4;i++)
  if(cal->white[i]<=cal->black[i])return -1;

 nx_linear_prejpeg_work *work=NULL;
 int rc=nx_linear_prejpeg_prepare(&work,id,look);
 if(rc!=0)return rc; /* Original never starts a new image transaction. */
 if(!sink||!sink->begin||!sink->write_row||!sink->commit||!sink->abort){
  nx_linear_prejpeg_release(work);return -1;
 }
 uint16_t *linear_row=malloc((size_t)w*3u*sizeof(*linear_row));
 uint8_t *pixel_rows=malloc((size_t)w*6u);
 uint8_t *luma_rows=malloc((size_t)w*3u);
 if(!linear_row||!pixel_rows||!luma_rows){
  free(linear_row);free(pixel_rows);free(luma_rows);
  nx_linear_prejpeg_release(work);return -1;
 }
 uint8_t *current=pixel_rows,*next=pixel_rows+(size_t)w*3u;
 uint8_t *previous_luma=luma_rows,*current_luma=luma_rows+w;
 uint8_t *next_luma=luma_rows+2u*w;
 rc=emit_bayer_row(src,ss,w,h,0,cal,work,linear_row,current,current_luma);
 if(rc==0&&h>1)
  rc=emit_bayer_row(src,ss,w,h,1,cal,work,linear_row,next,next_luma);
 if(rc==0){
  /* No sink callbacks happen before frame validation / allocation / startup.
   * On begin failure abort remains mandatory to dispose temporary state. */
  if(sink->begin(sink->user,w,h,id)!=0){
   sink->abort(sink->user);rc=-1;
  }else{
   for(unsigned y=0;y<h;y++){
    if(nx_camera_style_apply_row(id,current,w,y,h,
                               y?previous_luma:NULL,current_luma,
                               y+1<h?next_luma:NULL)!=0||
       sink->write_row(sink->user,y,current,(size_t)w*3u)!=0){
     rc=-1;break;
    }
    uint8_t *r=current;current=next;next=r;
    uint8_t *t=previous_luma;previous_luma=current_luma;
    current_luma=next_luma;next_luma=t;
    if(y+2<h&&emit_bayer_row(src,ss,w,h,y+2,cal,work,linear_row,
                             next,next_luma)!=0){
     rc=-1;break;
    }
   }
   if(rc==0&&sink->commit(sink->user)!=0)rc=-1;
   if(rc!=0)sink->abort(sink->user);
  }
 }
 free(linear_row);free(pixel_rows);free(luma_rows);
 nx_linear_prejpeg_release(work);
 return rc;
}
