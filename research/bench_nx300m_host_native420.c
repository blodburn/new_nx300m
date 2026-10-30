#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_native420_bridge.h"
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
static double elapsed(struct timespec a,struct timespec b){
 return (double)(b.tv_sec-a.tv_sec)+1e-9*(double)(b.tv_nsec-a.tv_nsec);
}
int main(void){
 enum {W=5546,H=3714,STRIDE=5552};
 const size_t count=(size_t)W*H;
 uint16_t *raw=malloc(count*sizeof(*raw));
 if(!raw)return 2;
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)
  raw[(size_t)y*W+x]=(uint16_t)(12000u+(x/5u)%34000u);
 nx_host420_stage *stage=nx_host420_create(W,H,STRIDE,
                                          NX_HOST420_CBCR_EXPERIMENTAL);
 if(!stage){free(raw);return 2;}
 nx_bayer_calibration cal={NX_BAYER_RGGB,{64,64,64,64},
                            {60000,60000,60000,60000},2200};
 nx_linear_params look={0,65535,1.6f,{1.05f,1.f,1.1f},.67f};
 nx_bayer_rgb8_sink sink=nx_host420_sink(stage);
 struct timespec a,b;clock_gettime(CLOCK_MONOTONIC,&a);
 int rc=nx_bayer_prejpeg_emit_rows(raw,count,W,W,H,&cal,&look,103,&sink);
 clock_gettime(CLOCK_MONOTONIC,&b);
 size_t bytes=0;nx_native_cycc header;
 const uint8_t *frame=nx_host420_published(stage,&bytes,&header);
 if(rc||!frame){nx_host420_destroy(stage);free(raw);return 1;}
 uint64_t hash=UINT64_C(14695981039346656037);
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  hash^=frame[(size_t)y*STRIDE+x];hash*=UINT64_C(1099511628211);
 }
 const uint8_t *c=frame+(size_t)STRIDE*H;
 for(unsigned y=0;y<H/2;y++)for(unsigned x=0;x<W;x++){
  hash^=c[(size_t)y*STRIDE+x];hash*=UINT64_C(1099511628211);
 }
 printf("HOST MODEL YCC420 %ux%u: rc=%d time=%.3f sec RAW=%zu bytes 2-region staging=%zu bytes active_YCC=%zu bytes Y0=%08x C0=%08x TYPE=%u HASH=%016llx; NOT native NX300M DMA\n",
        W,H,rc,elapsed(a,b),count*2u,bytes,count*3u/2u,
        header.y0,header.c0,header.image_ycc_type,(unsigned long long)hash);
 nx_host420_destroy(stage);free(raw);return 0;
}
