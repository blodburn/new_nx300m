#include "nx300m_camera_style_response.h"
#include "nx300m_film_menu.h"
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef struct { int shoulder,shadow,contrast,clarity,chrome,blue,grain; } response;
static uint8_t cv8(int a){return (uint8_t)(a<0?0:a>255?255:a);}
static int absint(int a){return a<0?-a:a;}
static int limit(int a,int n){return a<-n?-n:a>n?n:a;}
static int yluma(const uint8_t *p){return (54*(int)p[0]+183*(int)p[1]+19*(int)p[2]+128)>>8;}
static response select_response(unsigned id){
 switch(id){
 case 100:return (response){3,0,1,2,1,0,0}; /* PROVIA */
 case 101:return (response){3,-2,3,3,7,5,0}; /* Velvia */
 case 102:return (response){5,3,-1,1,1,0,0}; /* ASTIA */
 case 103:return (response){5,-3,2,2,5,2,1}; /* Classic Chrome */
 case 104:return (response){3,-5,5,3,4,1,2}; /* Classic Negative */
 case 105:return (response){8,4,-2,0,0,0,0}; /* ETERNA */
 case 106:return (response){4,-3,4,4,0,0,3}; /* ACROS */
 case 200:return (response){2,0,2,5,0,0,0}; /* Q3 Standard distinct */
 case 201:return (response){2,-2,5,7,0,0,0}; /* Q3 Vivid */
 case 202:return (response){5,2,-1,3,0,0,0}; /* Q3 Natural */
 case 203:return (response){3,1,3,5,0,0,0}; /* Q3 Mono */
 case 204:return (response){1,-5,7,9,0,0,0}; /* Q3 Mono HC */
 default:return (response){0,0,0,0,0,0,0};
 }
}
static uint32_t mixhash(uint32_t x){
 x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;x^=x>>16;return x;
}
static void style_row(unsigned id,const response cfg,uint8_t *line,
                      const uint8_t *prev,const uint8_t *cur,
                      const uint8_t *next,unsigned width,unsigned y,
                      unsigned height){
  for(unsigned x=0;x<width;x++){
   uint8_t *p=line+3u*x;
   int r=p[0],g=p[1],b=p[2];
   const int lum=cur[x];
   int delta=0;
   /* Smooth highlight shoulder: compresses existing 8-bit levels only;
    * cannot reconstruct already clipped raw sensor channels. */
   if(lum>160){
    const int t=lum-160;
    delta-=cfg.shoulder*t*t/(95*95);
   }
   if(lum<112){
    const int t=112-lum;
    delta+=cfg.shadow*t*t/(112*112);
   }
   /* S-shaped Q3 and Fujifilm profile contrast around mids; clamp endpoints. */
   if(lum>18&&lum<238){
    const int cen=lum-128;
    const int fall=lum<128?lum-18:238-lum;
    delta+=(cfg.contrast*cen*fall)/(110*110);
   }
   /* Color Chrome-like density in strong red/green or blue colors only.
    * Fuji has such controls. Leica's native Film Styles don't expose it. */
   if(cfg.chrome||cfg.blue){
    const int hi=r>g?(r>b?r:b):(g>b?g:b);
    const int lo=r<g?(r<b?r:b):(g<b?g:b);
    const int chroma=hi-lo;
    if(chroma>42&&lum>35&&lum<242){
     const int amt=(chroma-42)*(chroma>168?168:chroma)/255;
     if((r>=(int)b+8||g>=(int)b+10) && cfg.chrome)
      delta-=cfg.chrome*amt/105;
     else if(b>r+12&&b>g+8 && cfg.blue)
      delta-=cfg.blue*amt/105;
    }
   }
   if(cfg.clarity&&x>0&&x+1<width&&y>0&&y+1<height
      &&lum>28&&lum<235){
    const int l=cur[x-1],rr=cur[x+1];
    const int top=prev[x];
    const int bottom=next[x];
    const int span=absint(lum-l)>absint(lum-rr)?
                   absint(lum-l):absint(lum-rr);
    const int max1=span>absint(lum-top)?span:absint(lum-top);
    const int maxd=max1>absint(lum-bottom)?max1:absint(lum-bottom);
    if(maxd>=2&&maxd<=36){
     const int hp=lum-(l+rr+top+bottom+2)/4;
     delta+=limit(hp*cfg.clarity/13,cfg.clarity);
    }
   }
   if(cfg.grain&&lum>22&&lum<245){
    /* Neutral monochrome luma grain; coordinate-stable; no RNG state.
     * Camera film simulation is not literally this synthetic hash pattern. */
    const uint32_t h=mixhash((uint32_t)x*0x9e3779b9u ^
                       (uint32_t)y*0x85ebca6bu ^ (uint32_t)id);
    const int ng=(int)(h%9u)-4;
    delta+=ng*cfg.grain/4;
   }
   delta=limit(delta,18);
   p[0]=cv8(r+delta);p[1]=cv8(g+delta);p[2]=cv8(b+delta);
  }
}
static int validate(unsigned id,uint8_t *pixels,size_t stride,
                    unsigned width,unsigned height,const nx_film_preset **out){
 if(!pixels||!width||!height||width>16384||height>16384||
    stride<(size_t)width*3u||(size_t)height>SIZE_MAX/stride||
    (size_t)width>SIZE_MAX/height)return -1;
 *out=nx_film_by_id(id);
 return *out?((*out)->id==0?1:0):-1;
}
static void get_luma_row(uint8_t *dst,const uint8_t *src,unsigned width){
 for(unsigned x=0;x<width;x++)dst[x]=(uint8_t)yluma(src+3u*x);
}
int nx_camera_style_luma_row(const uint8_t *rgb,unsigned width,uint8_t *luma){
 if(!rgb||!luma||!width||width>16384)return -1;
 get_luma_row(luma,rgb,width);
 return 0;
}
int nx_camera_style_apply_row(unsigned id,uint8_t *rgb,unsigned width,
                              unsigned y,unsigned height,
                              const uint8_t *prev,const uint8_t *cur,
                              const uint8_t *next){
 if(!rgb||!cur||!width||width>16384||!height||height>16384||y>=height||
    (y>0&&!prev)||(y+1<height&&!next))return -1;
 const nx_film_preset *preset=nx_film_by_id(id);
 if(!preset)return -1;
 if(preset->id==0)return 1;
 style_row(id,select_response(preset->id),rgb,prev,cur,next,width,y,height);
 return 0;
}
int nx_camera_style_response_rgb888(unsigned id,uint8_t *pixels,size_t stride,
                                   unsigned width,unsigned height){
 const nx_film_preset *preset=NULL;
 int rc=validate(id,pixels,stride,width,height,&preset);
 if(rc!=0)return rc;
 const response cfg=select_response(preset->id);
 uint8_t *luma=malloc((size_t)width*height);
 if(!luma)return -1;
 for(unsigned y=0;y<height;y++)
  get_luma_row(luma+(size_t)y*width,pixels+(size_t)y*stride,width);
 for(unsigned y=0;y<height;y++){
  uint8_t *line=pixels+(size_t)y*stride;
  style_row(id,cfg,line,y?luma+(size_t)(y-1)*width:NULL,
            luma+(size_t)y*width,y+1<height?luma+(size_t)(y+1)*width:NULL,
            width,y,height);
 }
 free(luma);return 0;
}
int nx_camera_style_response_rgb888_streaming(unsigned id,uint8_t *pixels,
                                              size_t stride,
                                              unsigned width,unsigned height){
 const nx_film_preset *preset=NULL;
 int rc=validate(id,pixels,stride,width,height,&preset);
 if(rc!=0)return rc;
 uint8_t *rows=malloc((size_t)width*3u);
 if(!rows)return -1;
 uint8_t *prev=rows,*cur=rows+width,*next=rows+2u*width;
 const response cfg=select_response(preset->id);
 get_luma_row(cur,pixels,width);
 if(height>1)get_luma_row(next,pixels+stride,width);
 for(unsigned y=0;y<height;y++){
  style_row(id,cfg,pixels+(size_t)y*stride,y?prev:NULL,cur,
            y+1<height?next:NULL,width,y,height);
  /* Rotate after processing the current row. Next luma was read BEFORE
   * its RGB pixels were changed, preserving legacy full-frame behavior. */
  uint8_t *old=prev;prev=cur;cur=next;next=old;
  if(y+2<height)
   get_luma_row(next,pixels+(size_t)(y+2)*stride,width);
 }
 free(rows);return 0;
}
