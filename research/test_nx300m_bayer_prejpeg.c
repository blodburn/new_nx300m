#include "nx300m_bayer_prejpeg.h"
#include "nx300m_film_menu.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>

enum {W=16,H=12,SS=20,DS=W*3+5,OUTS=W*3+7};
static uint16_t raw[H*SS],snapshot[H*SS],rgb[H*DS],rgb2[H*DS];
static uint8_t jpg[H*OUTS],jpg2[H*OUTS];
static const unsigned char tile[4][4]={
 {0,1,1,2},{2,1,1,0},{1,0,2,1},{1,2,0,1}
};
static nx_bayer_calibration cal={NX_BAYER_RGGB,
 {64,96,72,80},{60000,61000,62000,63000},2200};
static nx_linear_params linear={0,65535,2.f,{1.f,1.f,1.f},0.60f};
static unsigned count=0;
static unsigned site(unsigned x,unsigned y){return ((y&1u)<<1u)|(x&1u);}
static void populate(int scene){
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<SS;x++){
  if(x>=W){raw[y*SS+x]=0xbeef;continue;}
  unsigned i=site(x,y);
  unsigned signal=31000;
  if(scene==1)signal=(x<8)?20000:45000;
  if(scene==2)signal=x<4?12000:(x<8?18000:(x<12?35000:42000));
  raw[y*SS+x]=(uint16_t)(cal.black[i]+
     ((uint64_t)signal*(cal.white[i]-cal.black[i])+32767u)/65535u);
 }
 memcpy(snapshot,raw,sizeof(raw));
}
static void expect_close(unsigned a,unsigned b,unsigned d){
 assert(a<=b+d&&b<=a+d);
}
static void test_cfa_and_padding(void){
 for(unsigned pat=0;pat<4;pat++){
  cal.pattern=(nx_bayer_pattern)pat;
  populate(0);
  memset(rgb,0xa5,sizeof(rgb));
  assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&cal)==0);
  for(unsigned y=0;y<H;y++){
   for(unsigned x=2;x<W-2;x++)
    for(unsigned ch=0;ch<3;ch++)
     expect_close(rgb[y*DS+3*x+ch],31000,5);
   for(unsigned k=W*3;k<DS;k++)assert(rgb[y*DS+k]==0xa5a5);
  }
  assert(!memcmp(raw,snapshot,sizeof(raw)));
  count++;
 }
}
static void test_defect_and_edges(void){
 cal.pattern=NX_BAYER_RGGB;
 populate(0);
 unsigned x=8,y=6,i=site(x,y),c=tile[0][i];
 raw[y*SS+x]=cal.white[i]; /* definite hot-pixel impulse */
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&cal)==0);
 expect_close(rgb[y*DS+3*x+c],31000,5);
 cal.defect_threshold=0;
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb2,H*DS,DS,W,H,&cal)==0);
 assert(rgb2[y*DS+3*x+c]==65535);
 assert(raw[y*SS+x]==cal.white[i]); /* source never corrected in-place */
 cal.defect_threshold=2200;
 raw[y*SS+x]=cal.black[i]; /* definite dead-pixel impulse */
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&cal)==0);
 expect_close(rgb[y*DS+3*x+c],31000,5);
 assert(raw[y*SS+x]==cal.black[i]);
 count+=3;
 populate(1);
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&cal)==0);
 /* The reconstructed green at a red/blue site respects the vertical edge. */
 expect_close(rgb[5*DS+3*7+1],20000,5);
 expect_close(rgb[5*DS+3*8+1],45000,5);
 assert(!memcmp(raw,snapshot,sizeof(raw)));
 count++;
}
static void test_reject_and_original(void){
 cal.pattern=NX_BAYER_RGGB;
 populate(0);
 memset(rgb,0x7c,sizeof(rgb));uint16_t before[H*DS];
 memcpy(before,rgb,sizeof(before));
 nx_bayer_calibration bad=cal;
 bad.pattern=(nx_bayer_pattern)4;
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&bad)==-1);
 bad=cal;bad.white[0]=bad.black[0];
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&bad)==-1);
 assert(nx_bayer_to_rgb16(raw,H*SS-1,SS,rgb,H*DS,DS,W,H,&cal)==-1);
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS-1,DS,W,H,&cal)==-1);
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,(uint16_t*)raw,H*SS,SS,W,H,&cal)==-1);
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,W*3-1,W,H,&cal)==-1);
 assert(!memcmp(rgb,before,sizeof(rgb)));
 memset(jpg,0xe1,sizeof(jpg));
 assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                              W,H,&cal,&linear,0)==1);
 for(size_t i=0;i<sizeof(jpg);i++)assert(jpg[i]==0xe1);
 assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                              W,H,&cal,&linear,999)==-1);
 nx_linear_params badlook=linear;badlook.white_level=60000;
 assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                              W,H,&cal,&badlook,100)==-1);
 assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS-1,OUTS,
                              W,H,&cal,&linear,100)==-1);
 for(size_t i=0;i<sizeof(jpg);i++)assert(jpg[i]==0xe1);
 assert(!memcmp(raw,snapshot,sizeof(raw)));
 count+=10;
}
static void test_looks_determinism(void){
 cal.pattern=NX_BAYER_RGGB;populate(0);
 assert(nx_film_count()==13);
 for(size_t j=1;j<nx_film_count();j++){
  const nx_film_preset *look=nx_film_by_index(j);
  assert(look&&look->id!=0);
  memset(jpg,0xd2,sizeof(jpg));memset(jpg2,0xd2,sizeof(jpg2));
  assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                              W,H,&cal,&linear,look->id)==0);
  assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg2,H*OUTS,OUTS,
                              W,H,&cal,&linear,look->id)==0);
  assert(!memcmp(jpg,jpg2,sizeof(jpg)));
  for(unsigned y=0;y<H;y++)
   for(unsigned k=W*3;k<OUTS;k++)assert(jpg[y*OUTS+k]==0xd2);
  assert(!memcmp(raw,snapshot,sizeof(raw)));
  count++;
 }
}
static void test_highlight_baseline(void){
 cal.pattern=NX_BAYER_RGGB;populate(2);
 assert(nx_bayer_to_rgb16(raw,H*SS,SS,rgb,H*DS,DS,W,H,&cal)==0);
 memset(jpg,0,sizeof(jpg));
 assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                              W,H,&cal,&linear,100)==0);
 /* Same 18^3 Film LUT applied to both routes. The baseline first
  * clips exposure in linear 8-bit-equivalent space, then applies LUT.
  * The improved route uses the high-bit shoulder before LUT.
  * No JPEG codec/display/re-encoding contributes to this comparison. */
 nx_film_menu menu;nx_film_menu_init(&menu);menu.selected_id=100;
 nx_rgb12 *lut=malloc(NX_LUT_COUNT*sizeof(*lut));
 nx_preview_processor *conv=malloc(sizeof(*conv));
 assert(lut&&conv);
 assert(nx_film_lut_for_menu(&menu,lut)==0);
 assert(nx_preview_init(conv)==0);
 unsigned saturated=0,improved_white=0;
 uint8_t baseline[H*W*3];
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  nx_rgb12 v={0,0,0,0},o;
  uint16_t *c[3]={&v.r,&v.g,&v.b};
  for(unsigned ch=0;ch<3;ch++){
   unsigned linear_clipped=((unsigned)rgb[y*DS+3*x+ch]*2u);
   if(linear_clipped>=65535u)linear_clipped=65535u;
   *c[ch]=(uint16_t)((linear_clipped*4095u+32767u)/65535u);
  }
  if(rgb[y*DS+3*x+1]>=32768u)saturated++;
  assert(nx_lut18_apply(lut,&v,&o,1)==0);
  baseline[(y*W+x)*3+0]=conv->encode_srgb[o.r];
  baseline[(y*W+x)*3+1]=conv->encode_srgb[o.g];
  baseline[(y*W+x)*3+2]=conv->encode_srgb[o.b];
  if(jpg[y*OUTS+3*x+1]==255)improved_white++;
 }
 unsigned pos_a=5*W+10,pos_b=5*W+14;
 int base_gap=(int)baseline[3*pos_b]-(int)baseline[3*pos_a];
 int pre_gap=(int)jpg[5*OUTS+3*14]-(int)jpg[5*OUTS+3*10];
 assert(base_gap==0);
 assert(pre_gap>0);
 assert(improved_white<saturated);
 printf("SYNTHETIC 2x highlight: naive LUT output gap=%d, 16-bit shoulder gap=%d /255; naive pre-LUT saturated %u/%u pixels; improved final white %u/%u pixels\n",
        base_gap,pre_gap,saturated,W*H,improved_white,W*H);
 free(conv);free(lut);
 assert(!memcmp(raw,snapshot,sizeof(raw)));
 count+=4;
}
static void test_streaming_pixel_identity(void){
 uint8_t compare[H*OUTS],before[H*OUTS];
 for(unsigned pat=0;pat<4;pat++){
  cal.pattern=(nx_bayer_pattern)pat;
  for(unsigned scene_index=0;scene_index<3;scene_index++){
   populate((int)scene_index);
   /* 15 columns, 11 rows exercise odd dimensions and CFA parity. */
   unsigned w=scene_index==2?W-1:W,h=scene_index==2?H-1:H;
   for(size_t j=1;j<nx_film_count();j++){
    const nx_film_preset *look=nx_film_by_index(j);
    assert(look);
    memset(jpg,0xaa,sizeof(jpg));memset(compare,0xaa,sizeof(compare));
    assert(nx_bayer_prejpeg_film(raw,H*SS,SS,jpg,H*OUTS,OUTS,
                                 w,h,&cal,&linear,look->id)==0);
    assert(nx_bayer_prejpeg_film_streaming(raw,H*SS,SS,compare,H*OUTS,OUTS,
                                 w,h,&cal,&linear,look->id)==0);
    assert(!memcmp(jpg,compare,sizeof(jpg)));
    assert(!memcmp(raw,snapshot,sizeof(raw)));
    count++;
   }
  }
 }
 cal.pattern=NX_BAYER_RGGB;
 populate(0);
 memset(compare,0x5c,sizeof(compare));
 memcpy(before,compare,sizeof(before));
 nx_bayer_calibration invalid=cal;
 invalid.white[0]=invalid.black[0];
 assert(nx_bayer_prejpeg_film_streaming(raw,H*SS,SS,compare,H*OUTS,OUTS,
                                        W,H,&invalid,&linear,103)==-1);
 assert(nx_bayer_prejpeg_film_streaming(raw,H*SS-1,SS,compare,H*OUTS,OUTS,
                                        W,H,&cal,&linear,103)==-1);
 assert(nx_bayer_prejpeg_film_streaming(raw,H*SS,SS,compare,H*OUTS-1,OUTS,
                                        W,H,&cal,&linear,103)==-1);
 nx_linear_params bad=linear;bad.exposure=0.f;
 assert(nx_bayer_prejpeg_film_streaming(raw,H*SS,SS,compare,H*OUTS,OUTS,
                                        W,H,&cal,&bad,103)==-1);
 assert(nx_bayer_prejpeg_film_streaming(raw,H*SS,SS,compare,H*OUTS,OUTS,
                                        W,H,&cal,&linear,0)==1);
 assert(!memcmp(compare,before,sizeof(compare)));
 assert(!memcmp(raw,snapshot,sizeof(raw)));
 count+=6;
}
int main(void){
 test_cfa_and_padding();
 test_defect_and_edges();
 test_reject_and_original();
 test_looks_determinism();
 test_highlight_baseline();
 test_streaming_pixel_identity();
 printf("PASS %u assertions groups: 4 CFA, calibration, hot/dead pixels, edge-aware green, invalid metadata, source preservation, Original no-op, 12 deterministic looks, measured highlight separation\n",count);
 return 0;
}
