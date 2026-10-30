#include "nx300m_host_native420_bridge.h"
#include "nx300m_bayer_prejpeg.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum { W=16,H=12,SW=W+4,DST=W+6,RAWCOUNT=H*SW,RGBSTRIDE=W*3+9 };
static uint16_t raw[RAWCOUNT],original[RAWCOUNT];
static uint8_t rgb[H*RGBSTRIDE];
static uint8_t expected_y[H*DST],expected_c[(H/2)*DST];
static nx_bayer_calibration cal={NX_BAYER_RGGB,{64,64,64,64},
                                 {61500,61500,61500,61500},2400};
static nx_linear_params look={0,65535,1.6f,{1.1f,1.f,.8f},.62f};
static uint8_t clamp8(int n){return (uint8_t)(n<0?0:n>255?255:n);}
static uint8_t yy(const uint8_t *p){
 return clamp8((19595*(int)p[0]+38470*(int)p[1]+7471*(int)p[2]+32768)>>16);
}
static uint8_t cb(const uint8_t *p){
 return clamp8(128+((-11059*(int)p[0]-21709*(int)p[1]+32768*(int)p[2]+32768)>>16));
}
static uint8_t cr(const uint8_t *p){
 return clamp8(128+((32768*(int)p[0]-27439*(int)p[1]-5329*(int)p[2]+32768)>>16));
}
static void fill(unsigned scene){
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<SW;x++)
  raw[(size_t)y*SW+x]=(uint16_t)(x>=W?0xbeef:
     (scene==0?(16000u+x*2500u+y*800u)%60000u:
      scene==1?(x<W/2?6000u:53000u):
       3000u+(x*1033u+y*2789u)%56000u));
 memcpy(original,raw,sizeof(raw));
}
static void convert_expected(enum nx_host420_order order){
 memset(expected_y,0xa5,sizeof(expected_y));
 memset(expected_c,0xa5,sizeof(expected_c));
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)
  expected_y[(size_t)y*DST+x]=yy(rgb+(size_t)y*RGBSTRIDE+3u*x);
 for(unsigned y=0;y<H;y+=2u)for(unsigned x=0;x<W;x+=2u){
  unsigned acb=0,acr=0;
  for(unsigned row=0;row<2;row++)for(unsigned k=0;k<2;k++){
   const uint8_t *p=rgb+(size_t)(y+row)*RGBSTRIDE+3u*(x+k);
   acb+=cb(p);acr+=cr(p);
  }
  uint8_t *c=expected_c+(size_t)(y/2u)*DST+x;
  c[order==NX_HOST420_CRCB_EXPERIMENTAL?1:0]=(uint8_t)((acb+2u)/4u);
  c[order==NX_HOST420_CRCB_EXPERIMENTAL?0:1]=(uint8_t)((acr+2u)/4u);
 }
}
int main(void){
 unsigned cases=0;
 assert(nx_host420_create(W,H,DST,NX_HOST420_ORDER_UNSPECIFIED)==NULL);
 assert(nx_host420_create(W-1,H,DST,NX_HOST420_CBCR_EXPERIMENTAL)==NULL);
 assert(nx_host420_create(W,H-1,DST,NX_HOST420_CBCR_EXPERIMENTAL)==NULL);
 assert(nx_host420_create(W,H,W-1,NX_HOST420_CBCR_EXPERIMENTAL)==NULL);
 assert(nx_host420_create(W,H,DST-1,NX_HOST420_CBCR_EXPERIMENTAL)==NULL);
 for(unsigned pattern=0;pattern<4;pattern++)for(unsigned scene=0;scene<3;scene++){
  cal.pattern=(nx_bayer_pattern)pattern;fill(scene);
  for(size_t j=1;j<nx_film_count();j++){
   const nx_film_preset *preset=nx_film_by_index(j);
   assert(preset);
   memset(rgb,0xa5,sizeof(rgb));
   assert(nx_bayer_prejpeg_film_streaming(raw,RAWCOUNT,SW,rgb,sizeof(rgb),
              RGBSTRIDE,W,H,&cal,&look,preset->id)==0);
   for(unsigned order=1;order<=2;order++){
    nx_host420_stage *host=nx_host420_create(W,H,DST,
                                  (enum nx_host420_order)order);
    assert(host);
    size_t size=0;nx_native_cycc meta;
    assert(!nx_host420_published(host,&size,&meta));
    nx_bayer_rgb8_sink sink=nx_host420_sink(host);
    assert(nx_bayer_prejpeg_emit_rows(raw,RAWCOUNT,SW,W,H,&cal,&look,
                                      preset->id,&sink)==0);
    const uint8_t *out=nx_host420_published(host,&size,&meta);
    assert(out&&size==(size_t)DST*H*2u);
    assert(meta.width==W&&meta.height==H&&meta.stride==DST&&
           meta.image_ycc_type==1&&meta.scan_mode==1);
    assert(meta.y0==UINT32_C(0x10000000)&&meta.y1==meta.y0+DST);
    assert(meta.c0==meta.y0+DST*H&&meta.c1==meta.c0+DST);
    uint32_t native_bytes=0,native_end=0;
    assert(nx_cycc_footprint(&meta,&native_bytes,&native_end)==0);
    assert(native_bytes==size&&native_end==meta.y0+size);
    convert_expected((enum nx_host420_order)order);
    assert(!memcmp(out,expected_y,sizeof(expected_y)));
    assert(!memcmp(out+(size_t)DST*H,expected_c,sizeof(expected_c)));
    for(size_t i=(size_t)DST*H+(size_t)DST*(H/2u);i<size;i++)
     assert(out[i]==0xa5); /* Do not touch unproven unused half-region. */
    assert(!memcmp(raw,original,sizeof(raw)));
    nx_host420_destroy(host);
    cases++;
   }
  }
 }
 nx_host420_stage *host=nx_host420_create(W,H,DST,NX_HOST420_CBCR_EXPERIMENTAL);
 assert(host);
 nx_bayer_rgb8_sink sink=nx_host420_sink(host);
 assert(nx_bayer_prejpeg_emit_rows(raw,RAWCOUNT,SW,W,H,&cal,&look,0,&sink)==1);
 size_t n=0;nx_native_cycc m;
 assert(!nx_host420_published(host,&n,&m));
 assert(nx_bayer_prejpeg_emit_rows(raw,RAWCOUNT-1,SW,W,H,&cal,&look,101,
                                   &sink)==-1);
 assert(!nx_host420_published(host,&n,&m));
 /* Simulate aborted native/staging path: must not expose partial buffer. */
 assert(sink.begin(sink.user,W,H,103)==0);
 uint8_t row[W*3u]={0};
 assert(sink.write_row(sink.user,0,row,sizeof(row))==0);
 sink.abort(sink.user);
 assert(!nx_host420_published(host,&n,&m));
 assert(sink.begin(sink.user,W,H,103)==0);
 for(unsigned y=0;y<H;y++)assert(sink.write_row(sink.user,y,row,sizeof(row))==0);
 assert(sink.commit(sink.user)==0);
 assert(nx_host420_published(host,&n,&m));
 /* Duplicate commit is forbidden; no native DMA registration occurs. */
 assert(sink.commit(sink.user)==-1);
 sink.abort(sink.user);
 assert(!nx_host420_published(host,&n,&m));
 nx_host420_destroy(host);
 puts("PASS 288 HOST type1 YCC420 hypotheses: 4 CFA x 3 scenes x 12 looks x both CbCr orders; synthetic CYcc pointer offsets, Y/C pixels, full padding, RAW untouched, Original no-op, abort-unpublished");
 return 0;
}
