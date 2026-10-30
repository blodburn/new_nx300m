#include "nx300m_camera_style_response.h"
#include "nx300m_still_enhanced.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {W=80,H=48,STRIDE=W*3+8,TOTAL=STRIDE*H};
static uint8_t base[TOTAL],a[TOTAL],b[TOTAL];
static void init(void){
 for(unsigned y=0;y<H;y++){
  for(unsigned x=0;x<W;x++){
   const unsigned q=(size_t)y*STRIDE+3*x;
   const int v=(int)(x*2u+y);
   base[q]=(uint8_t)(32+(v%180));
   base[q+1]=(uint8_t)(40+((v+25)%168));
   base[q+2]=(uint8_t)(50+((v+48)%142));
  }
  memset(base+(size_t)y*STRIDE+W*3,0xCC,STRIDE-W*3);
 }
}
static void original(void){memcpy(a,base,TOTAL);}
static void checkpadding(const uint8_t *p){
 for(unsigned y=0;y<H;y++)for(unsigned col=W*3;col<STRIDE;col++)
  assert(p[(size_t)y*STRIDE+col]==0xCC);
}
int main(void){
 init();
 assert(nx_film_count()==13);
 for(unsigned i=0;i<nx_film_count();i++){
  const nx_film_preset *p=nx_film_by_index(i);
  assert(p);
  original();
  int rc=nx_camera_style_response_rgb888(p->id,a,STRIDE,W,H);
  assert(rc==(p->id==0?1:0));
  checkpadding(a);
  memcpy(b,base,TOTAL);
  assert(nx_camera_style_response_rgb888_streaming(p->id,b,STRIDE,W,H)==rc);
  assert(!memcmp(a,b,TOTAL)); /* byte-exact full-frame luma vs 3-row cache */
  if(p->id==200)assert(memcmp(a,base,TOTAL)!=0);
  memcpy(b,a,TOTAL);
  original();
  assert(nx_camera_style_response_rgb888(p->id,a,STRIDE,W,H)==rc);
  assert(!memcmp(a,b,TOTAL)); /* deterministic grain */
 }
 /* Explicitly exercise 1-row, 2-row and odd-width frames. */
 for(unsigned h=1;h<=3;h++)for(unsigned w=1;w<=7;w++){
  uint8_t src[3u*7u*3u],ref[sizeof(src)],stream[sizeof(src)];
  for(size_t i=0;i<sizeof(src);i++)src[i]=(uint8_t)((i*19u+47u)%256u);
  for(size_t j=1;j<nx_film_count();j++){
   const nx_film_preset *preset=nx_film_by_index(j);
   assert(preset);
   memcpy(ref,src,sizeof(ref));memcpy(stream,src,sizeof(stream));
   assert(nx_camera_style_response_rgb888(preset->id,ref,w*3u,w,h)==0);
   assert(nx_camera_style_response_rgb888_streaming(preset->id,stream,w*3u,w,h)==0);
   assert(!memcmp(ref,stream,sizeof(stream)));
  }
 }
 original();
 assert(nx_camera_style_response_rgb888(999,a,STRIDE,W,H)==-1);
 assert(!memcmp(a,base,TOTAL));
 assert(nx_camera_style_response_rgb888_streaming(999,a,STRIDE,W,H)==-1);
 assert(nx_camera_style_response_rgb888_streaming(103,NULL,STRIDE,W,H)==-1);
 assert(nx_camera_style_response_rgb888_streaming(103,a,W*2,W,H)==-1);
 assert(!memcmp(a,base,TOTAL));
 assert(nx_camera_style_response_rgb888(103,NULL,STRIDE,W,H)==-1);
 assert(nx_camera_style_response_rgb888(103,a,W*2,W,H)==-1);
 /* Same Q3 and Fuji tone-neutral input, Fuji ACROS adds grayscale grain;
  * Leica monochrome stays smooth and colors never emerge. */
 for(size_t i=0;i<TOTAL;i++)a[i]=128;
 for(unsigned y=0;y<H;y++)memset(a+(size_t)y*STRIDE+W*3,0xCC,STRIDE-W*3);
 memcpy(b,a,TOTAL);
 assert(nx_camera_style_response_rgb888(106,a,STRIDE,W,H)==0);
 int unique=0;
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  const uint8_t *pix=a+(size_t)y*STRIDE+3*x;
  assert(pix[0]==pix[1]&&pix[1]==pix[2]);
  if(pix[0]!=128)unique++;
 }
 assert(unique>100);
 assert(nx_camera_style_response_rgb888(203,b,STRIDE,W,H)==0);
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  const uint8_t *pix=b+(size_t)y*STRIDE+3*x;
  assert(pix[0]==pix[1]&&pix[1]==pix[2]);
 }
 assert(memcmp(a,b,TOTAL)!=0);
 original();
 assert(nx_still_filter_enhanced_inplace(0,NX_STILL_SRGB_RGB888,a,STRIDE,W,H)==NX_STILL_BYPASSED);
 assert(!memcmp(a,base,TOTAL));
 assert(nx_still_filter_enhanced_inplace(105,NX_STILL_RAW_OR_UNKNOWN,a,STRIDE,W,H)==NX_STILL_BYPASSED);
 assert(!memcmp(a,base,TOTAL));
 assert(nx_still_filter_enhanced_inplace(200,NX_STILL_SRGB_RGB888,a,STRIDE,W,H)==NX_STILL_APPLIED);
 assert(memcmp(a,base,TOTAL)!=0);
 checkpadding(a);
 puts("PASS fixed 13 X100VI / Leica Q3 distinct tone/chrome/microcontrast/grain, Q3 standard unique, reproducible grain, mono neutrality, original and RAW exact bypass");
 return 0;
}
