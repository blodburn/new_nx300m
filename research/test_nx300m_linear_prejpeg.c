#include "nx300m_linear_prejpeg.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
enum {W=6,H=4,SRC_STRIDE=21,DST_STRIDE=23};
static uint16_t scene[H*SRC_STRIDE],preserved[H*SRC_STRIDE];
static uint8_t out[H*DST_STRIDE],backup[H*DST_STRIDE];
static nx_linear_params p={0,65535,2.f,{1.f,1.f,1.f},0.70f};
int main(void){
 for(unsigned y=0;y<H;y++){
  for(unsigned x=0;x<W;x++){
   uint16_t v=(x<2)?10000u:(x==2?38000u:(x==3?44000u:52000u));
   for(unsigned c=0;c<3;c++)scene[y*SRC_STRIDE+3*x+c]=v;
  }
  for(unsigned j=W*3;j<SRC_STRIDE;j++)scene[y*SRC_STRIDE+j]=0xabcd;
 }
 memcpy(preserved,scene,sizeof(scene));
 memset(out,0xcd,sizeof(out));memcpy(backup,out,sizeof(out));
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,0,&p)==1);
 assert(!memcmp(out,backup,sizeof(out)));
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,999,&p)==-1);
 assert(!memcmp(out,backup,sizeof(out)));
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,100,&p)==0);
 assert(!memcmp(scene,preserved,sizeof(scene)));
 /* Both 38k and 44k linear values become 65535 when exposed 2x and
  * clipped BEFORE Picture Wizard; pre-clip smooth shoulder keeps separation. */
 const int a=out[3*2],b=out[3*3];
 assert(b>a && b-a>=1);
 assert(out[0]<a);
 for(unsigned y=0;y<H;y++)
  for(unsigned j=3*W;j<DST_STRIDE;j++)assert(out[y*DST_STRIDE+j]==0xcd);
 memset(out,0xcd,sizeof(out));memcpy(backup,out,sizeof(out));
 nx_linear_params invalid=p;invalid.white_level=0;
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,101,&invalid)==-1);
 assert(!memcmp(out,backup,sizeof(out)));
 invalid=p;invalid.highlight_knee=0.f;
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,101,&invalid)==-1);
 assert(!memcmp(out,backup,sizeof(out)));
 invalid=p;invalid.exposure=9.f;
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,out,DST_STRIDE,W,H,101,&invalid)==-1);
 assert(!memcmp(out,backup,sizeof(out)));
 assert(nx_linear_prejpeg_film_rgb16(scene,SRC_STRIDE,(uint8_t*)scene,DST_STRIDE,W,H,101,&p)==-1);
 assert(!memcmp(scene,preserved,sizeof(scene)));
 /* Byte multiplication overflow must fail before frame access. */
 memset(out,0xcd,sizeof(out));
 assert(nx_linear_prejpeg_film_rgb16(scene,SIZE_MAX/2u,out,DST_STRIDE,W,H,101,&p)==-1);
 assert(!memcmp(out,backup,sizeof(out)));
 puts("PASS PRE-JPEG 16bit linear highlight detail survives 2x exposure before 8bit clamp, sensor RGB untouched, no extra frame memory, 13-film LUT integration, guards and original bypass");
 return 0;
}
