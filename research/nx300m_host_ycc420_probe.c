#include "nx300m_host_ycc420_probe.h"
#include <string.h>
#include <stdint.h>
#include <limits.h>

/* Full-range BT.601 is ONLY one host-side hypothesis. Arithmetic mirrors
 * nx300m_host_native420_bridge for reproducible offline fixtures. */
static uint8_t clamp8(int n){return (uint8_t)(n<0?0:n>255?255:n);}
static uint8_t expected_y(const uint8_t *p){
 return clamp8((19595*(int)p[0]+38470*(int)p[1]+7471*(int)p[2]+32768)>>16);
}
static uint8_t expected_cb(const uint8_t *p){
 return clamp8(128+((-11059*(int)p[0]-21709*(int)p[1]+32768*(int)p[2]+32768)>>16));
}
static uint8_t expected_cr(const uint8_t *p){
 return clamp8(128+((32768*(int)p[0]-27439*(int)p[1]-5329*(int)p[2]+32768)>>16));
}
static unsigned absdiff(unsigned a,unsigned b){return a>b?a-b:b-a;}
static uint32_t milli(uint64_t error,uint64_t components){
 return components?(uint32_t)((error*1000u+components/2u)/components):UINT32_MAX;
}
nx_ycc420_assessment nx_host_ycc420_probe(
 const uint8_t *y,size_t y_bytes,size_t y_stride,
 const uint8_t *c,size_t c_bytes,size_t c_stride,
 const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned width,unsigned height,nx_ycc420_evidence *out){
 if(out)memset(out,0,sizeof(*out));
 if(!out||!y||!c||!rgb||width<4||height<4||
    width>8192||height>8192||(width&1u)||(height&1u)||
    y_stride<width||c_stride<width||rgb_stride<(size_t)width*3u||
    y_stride>65536||c_stride>65536||rgb_stride>65536)return NX_YCC420_BAD_INPUT;
 /* Overflow-safe bounds check; prevents ever reading outside a copied plane.
  * The last row may end before trailing padding: that is permitted. */
 uint64_t req_y=(uint64_t)(height-1u)*y_stride+width;
 uint64_t req_c=(uint64_t)(height/2u-1u)*c_stride+width;
 uint64_t req_rgb=(uint64_t)(height-1u)*rgb_stride+3u*(uint64_t)width;
 if(req_y>y_bytes||req_c>c_bytes||req_rgb>rgb_bytes)
  return NX_YCC420_BAD_INPUT;
 uint64_t yerr=0,cbcr_err=0,crcb_err=0,informative=0;
 for(unsigned row=0;row<height;row++){
  const uint8_t *actual=y+(size_t)row*y_stride;
  const uint8_t *ref=rgb+(size_t)row*rgb_stride;
  for(unsigned x=0;x<width;x++){
   yerr+=absdiff(actual[x],expected_y(ref+(size_t)x*3u));
  }
 }
 for(unsigned row=0;row<height;row+=2u){
  const uint8_t *ref0=rgb+(size_t)row*rgb_stride;
  const uint8_t *ref1=ref0+rgb_stride;
  const uint8_t *actual=c+(size_t)(row/2u)*c_stride;
  for(unsigned x=0;x<width;x+=2u){
   unsigned cb=0,cr=0;
   for(unsigned col=0;col<2u;col++){
    cb+=expected_cb(ref0+(size_t)(x+col)*3u);
    cb+=expected_cb(ref1+(size_t)(x+col)*3u);
    cr+=expected_cr(ref0+(size_t)(x+col)*3u);
    cr+=expected_cr(ref1+(size_t)(x+col)*3u);
   }
   cb=(cb+2u)/4u;cr=(cr+2u)/4u;
   if(absdiff(cb,cr)>=18u)informative++;
   cbcr_err+=absdiff(actual[x],cb)+absdiff(actual[x+1],cr);
   crcb_err+=absdiff(actual[x],cr)+absdiff(actual[x+1],cb);
  }
 }
 uint64_t pixels=(uint64_t)width*height;
 uint64_t pairs=pixels/4u;
 out->width=width;out->height=height;out->pixels=pixels;
 out->chroma_pairs=pairs;out->informative_pairs=informative;
 out->y_mae_milli=milli(yerr,pixels);
 out->cbcr_mae_milli=milli(cbcr_err,2u*pairs);
 out->crcb_mae_milli=milli(crcb_err,2u*pairs);
 const uint32_t best=out->cbcr_mae_milli<out->crcb_mae_milli?
                        out->cbcr_mae_milli:out->crcb_mae_milli;
 const uint32_t other=out->cbcr_mae_milli>out->crcb_mae_milli?
                         out->cbcr_mae_milli:out->crcb_mae_milli;
 out->winning_gap_milli=other-best;
 /* Strict evidence gate: at least 10% strongly color-informative pairs,
  * close luminance/model agreement, convincing contrast between byte orders.
  * This is NOT proof of an NX300M 1.14 camera source or DMA ABI.
  */
 if(pairs>=16u&&informative>=8u&&informative*10u>=pairs&&
    out->y_mae_milli<=8000u&&best<=6000u&&
    out->winning_gap_milli>=6000u){
  out->result=out->cbcr_mae_milli<out->crcb_mae_milli?
        NX_YCC420_CBCR:NX_YCC420_CRCB;
 }else{
  out->result=NX_YCC420_INCONCLUSIVE;
 }
 return out->result;
}
